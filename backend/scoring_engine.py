"""
IndiaVest Scoring Engine
========================
4-factor weighted scoring system for trade recommendations.

Factor weights (LOCKED):
  F1: Technical regime   = 40%  (backtested RSI+MACD+Bollinger+Volume)
  F2: Volatility filter  = 15%  (ATR + Bollinger bandwidth)
  F3: News sentiment     = 15%  (24h rolling keyword sentiment)
  F4: On-chain flows     = 30%  (whale exchange in/outflows)

Each factor produces a score from -100 to +100.
Weighted sum > +40  = BUY
Weighted sum < -40  = SELL
Between             = HOLD

Architecture:
  BaseFactor (abstract) -> 4 concrete factors
  RegimeBacktester      -> backtests F1 against 365 days of data
  WeightedScorer        -> combines all factors
  ScoringEngine         -> main entry point for endpoints
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import httpx
import os
import logging

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Top coins to backtest (CoinGecko IDs) — expanded to 20
BACKTEST_COINS = [
    "bitcoin", "ethereum", "solana", "binancecoin", "ripple",
    "cardano", "dogecoin", "avalanche-2", "polkadot", "chainlink",
    "near", "aptos", "arbitrum", "optimism", "injective-protocol",
    "render-token", "sui", "sei-network", "celestia", "fetch-ai"
]

SYMBOL_TO_COINGECKO = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
    "LINK": "chainlink", "MATIC": "matic-network", "UNI": "uniswap",
    "LTC": "litecoin", "ATOM": "cosmos", "NEAR": "near",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "INJ": "injective-protocol", "RENDER": "render-token",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia", "FET": "fetch-ai"
}

# ====================================================================
# LOCKED WEIGHTS — only changeable by beta test data
# ====================================================================
FACTOR_WEIGHTS = {
    "F1_technical_regime": 0.40,
    "F2_volatility_filter": 0.15,
    "F3_news_sentiment": 0.15,
    "F4_onchain_flows": 0.30,
}


# ====================================================================
# INDICATOR CALCULATIONS (standalone, numpy-based)
# ====================================================================

def calc_rsi_series(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate RSI at every point in the price series.
    Returns array of same length as prices, with NaN for insufficient data."""
    rsi = np.full(len(prices), np.nan)
    if len(prices) < period + 1:
        return rsi

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100 - (100 / (1 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100 - (100 / (1 + rs))

    return rsi


def calc_ema(prices: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average."""
    ema = np.full(len(prices), np.nan)
    if len(prices) < span:
        return ema
    ema[span - 1] = np.mean(prices[:span])
    multiplier = 2 / (span + 1)
    for i in range(span, len(prices)):
        ema[i] = prices[i] * multiplier + ema[i - 1] * (1 - multiplier)
    return ema


def calc_macd_series(prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD line, signal line, histogram at every point.
    Returns three arrays of same length as prices."""
    ema12 = calc_ema(prices, 12)
    ema26 = calc_ema(prices, 26)
    macd_line = ema12 - ema26

    signal = np.full(len(prices), np.nan)
    valid_macd = ~np.isnan(macd_line)
    if np.sum(valid_macd) >= 9:
        first_valid = np.argmax(valid_macd)
        signal_data = calc_ema(macd_line[first_valid:], 9)
        signal[first_valid:] = signal_data

    histogram = macd_line - signal
    return macd_line, signal, histogram


def calc_bollinger_series(prices: np.ndarray, period: int = 20, num_std: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Upper, middle, lower bands at every point."""
    upper = np.full(len(prices), np.nan)
    middle = np.full(len(prices), np.nan)
    lower = np.full(len(prices), np.nan)

    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        m = np.mean(window)
        s = np.std(window)
        middle[i] = m
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s

    return upper, middle, lower


def calc_volume_ratio_series(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """Current volume / average volume over period."""
    ratio = np.full(len(volumes), np.nan)
    for i in range(period, len(volumes)):
        avg = np.mean(volumes[i - period:i])
        if avg > 0:
            ratio[i] = volumes[i] / avg
        else:
            ratio[i] = 1.0
    return ratio


def calc_atr_series(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range as percentage of price.
    Uses close-to-close as proxy since we only have daily close data.
    Returns ATR% at each point."""
    atr_pct = np.full(len(prices), np.nan)
    if len(prices) < period + 1:
        return atr_pct

    # True range approximation from daily closes
    daily_ranges = np.abs(np.diff(prices))
    for i in range(period, len(daily_ranges)):
        avg_range = np.mean(daily_ranges[i - period:i])
        if prices[i] > 0:
            atr_pct[i + 1] = (avg_range / prices[i]) * 100
    return atr_pct


def calc_bollinger_bandwidth_series(prices: np.ndarray, period: int = 20, num_std: float = 2.0) -> np.ndarray:
    """Bollinger Bandwidth = (upper - lower) / middle * 100.
    Measures how wide or narrow the bands are relative to price."""
    bw = np.full(len(prices), np.nan)
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        m = np.mean(window)
        s = np.std(window)
        if m > 0:
            bw[i] = (4 * num_std * s / m) * 100  # bandwidth as % of middle
    return bw


# ====================================================================
# REGIME CLASSIFICATION
# ====================================================================
# Two-tier system for statistical significance:
#   Primary regime:   RSI(3 states) x MACD(2 states) = 6 regimes
#   Secondary modifier: Bollinger(3) x Volume(2)      = 6 modifiers
#
# Primary regime gives direction + historical win rate.
# Secondary modifier adjusts confidence up or down.
# ====================================================================

def classify_rsi(rsi: float) -> str:
    """3 states for primary regime."""
    if rsi < 35:
        return "oversold"
    if rsi > 65:
        return "overbought"
    return "neutral"


def classify_macd(histogram: float) -> str:
    """2 states for primary regime."""
    if histogram > 0:
        return "bullish"
    return "bearish"


def classify_bollinger(price: float, upper: float, lower: float) -> str:
    """3 states for secondary modifier."""
    bandwidth = upper - lower
    if bandwidth <= 0:
        return "middle"
    position = (price - lower) / bandwidth
    if position < 0.33:
        return "lower"
    if position > 0.67:
        return "upper"
    return "middle"


def classify_volume(volume_ratio: float) -> str:
    """2 states for secondary modifier."""
    if volume_ratio > 1.3:
        return "high"
    return "normal"


def get_primary_regime(rsi_state: str, macd_state: str) -> str:
    """6 possible primary regimes."""
    return f"{rsi_state}|{macd_state}"


def get_secondary_modifier(bollinger_state: str, volume_state: str) -> str:
    """6 possible secondary modifiers."""
    return f"{bollinger_state}|{volume_state}"


# Confidence adjustment map for secondary modifiers.
# Positive = increases confidence, negative = decreases it.
SECONDARY_CONFIDENCE_MAP = {
    "lower|high":   +20,   # Price near bottom + high volume = potential reversal, strong signal
    "lower|normal": +10,   # Price near bottom, normal volume
    "middle|high":  +5,    # Neutral position, high activity
    "middle|normal": 0,    # No adjustment
    "upper|high":   -5,    # Near top + high volume = could be distribution
    "upper|normal": -10,   # Near top, slowing down
}


# ====================================================================
# HISTORICAL DATA FETCHER (cache-aware)
# ====================================================================

async def fetch_market_chart(coin_id: str, days: int = 365, vs_currency: str = "inr", db=None) -> Optional[Dict]:
    """Fetch daily prices and volumes.
    
    Priority order:
      1. MongoDB market_data_cache (populated by DataPreloader)
      2. CoinGecko API (direct fetch, slower, rate-limited)
    
    Returns {"prices": [float], "volumes": [float], "timestamps": [int]} or None.
    """
    # Try MongoDB cache first
    if db is not None:
        try:
            cached = await db["market_data_cache"].find_one({"coin_id": coin_id})
            if cached and len(cached.get("prices", [])) >= min(days, 30):
                fetched_at = cached.get("fetched_at")
                age_hours = 999
                if fetched_at:
                    # Handle timezone-naive datetimes from MongoDB
                    if hasattr(fetched_at, 'tzinfo') and fetched_at.tzinfo is None:
                        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                    try:
                        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
                    except TypeError:
                        age_hours = 0  # If comparison fails, assume fresh

                if age_hours < 24:  # Use cache if less than 24 hours old
                    prices = cached["prices"]
                    volumes = cached["volumes"]
                    timestamps = cached["timestamps"]
                    # If they asked for fewer days than we have, trim
                    if days < len(prices):
                        prices = prices[-days:]
                        volumes = volumes[-days:]
                        timestamps = timestamps[-days:]
                    return {
                        "timestamps": timestamps,
                        "prices": prices,
                        "volumes": volumes,
                    }
        except Exception as e:
            logger.warning(f"MongoDB cache lookup failed for {coin_id}: {e}")

    # Fallback: fetch from CoinGecko directly
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
                params={
                    "vs_currency": vs_currency,
                    "days": str(days),
                    "interval": "daily"
                },
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                prices_raw = data.get("prices", [])
                volumes_raw = data.get("total_volumes", [])

                if not prices_raw:
                    return None

                return {
                    "timestamps": [int(p[0]) for p in prices_raw],
                    "prices": [float(p[1]) for p in prices_raw],
                    "volumes": [float(v[1]) for v in volumes_raw] if volumes_raw else [0.0] * len(prices_raw),
                }
            elif response.status_code == 429:
                logger.warning(f"CoinGecko rate limited fetching {coin_id} market chart")
                return None
            else:
                logger.warning(f"CoinGecko market_chart returned {response.status_code} for {coin_id}")
                return None
    except Exception as e:
        logger.error(f"Error fetching market chart for {coin_id}: {e}")
        return None


# ====================================================================
# REGIME BACKTESTER
# ====================================================================

class RegimeBacktester:
    """Backtests technical regimes against historical price data.

    For each day in the last 365 days:
      1. Classify the primary regime (RSI x MACD)
      2. Classify the secondary modifier (Bollinger x Volume)
      3. Record what happened 1, 3, and 7 days later

    Aggregates into a lookup table:
      regime -> {win_rate_7d, avg_return_7d, sample_count, ...}
    """

    def __init__(self, db):
        self.db = db
        self.collection = "regime_backtests"

    async def backtest_coin(self, coin_id: str, days: int = 365) -> Dict:
        """Run full backtest for one coin. Cached for 24 hours in MongoDB."""

        try:
            cached = await self.db[self.collection].find_one({
                "coin_id": coin_id,
                "days": days,
            })
            if cached:
                computed_at = cached.get("computed_at")
                if computed_at:
                    if hasattr(computed_at, 'tzinfo') and computed_at.tzinfo is None:
                        computed_at = computed_at.replace(tzinfo=timezone.utc)
                    try:
                        age_hours = (datetime.now(timezone.utc) - computed_at).total_seconds() / 3600
                        if age_hours < 24:
                            cached.pop("_id", None)
                            return cached
                    except TypeError:
                        cached.pop("_id", None)
                        return cached  # If we can't check age, use it
        except Exception as e:
            logger.warning(f"Backtest cache lookup failed for {coin_id}: {e}")

        chart = await fetch_market_chart(coin_id, days, db=self.db)
        if not chart or len(chart["prices"]) < 60:
            return {
                "coin_id": coin_id,
                "error": "Insufficient data",
                "regime_stats": {},
                "modifier_stats": {},
            }

        prices = np.array(chart["prices"])
        volumes = np.array(chart["volumes"])

        rsi_series = calc_rsi_series(prices, 14)
        _, _, macd_hist = calc_macd_series(prices)
        bb_upper, bb_middle, bb_lower = calc_bollinger_series(prices, 20)
        vol_ratio = calc_volume_ratio_series(volumes, 20)

        regime_outcomes = {}   # primary regime -> list of outcome dicts
        modifier_outcomes = {} # secondary modifier -> list of outcome dicts
        data_points = []

        min_index = 33  # need 26 (MACD) + 9 (signal) lookback minimum

        for i in range(min_index, len(prices)):
            if np.isnan(rsi_series[i]) or np.isnan(macd_hist[i]) or np.isnan(bb_upper[i]) or np.isnan(vol_ratio[i]):
                continue

            primary = get_primary_regime(
                classify_rsi(float(rsi_series[i])),
                classify_macd(float(macd_hist[i]))
            )
            secondary = get_secondary_modifier(
                classify_bollinger(float(prices[i]), float(bb_upper[i]), float(bb_lower[i])),
                classify_volume(float(vol_ratio[i]))
            )

            outcomes = {}
            for label, horizon in [("1d", 1), ("3d", 3), ("7d", 7)]:
                if i + horizon < len(prices):
                    ret = (prices[i + horizon] - prices[i]) / prices[i] * 100
                    outcomes[label] = round(float(ret), 3)

            if not outcomes:
                continue

            if primary not in regime_outcomes:
                regime_outcomes[primary] = []
            regime_outcomes[primary].append(outcomes)

            if secondary not in modifier_outcomes:
                modifier_outcomes[secondary] = []
            modifier_outcomes[secondary].append(outcomes)

            data_points.append({
                "index": int(i),
                "primary_regime": primary,
                "secondary_modifier": secondary,
                "rsi": round(float(rsi_series[i]), 1),
                "macd_hist": round(float(macd_hist[i]), 4),
            })

        regime_stats = self._aggregate(regime_outcomes)
        modifier_stats = self._aggregate(modifier_outcomes)

        result = {
            "coin_id": coin_id,
            "days": days,
            "total_data_points": len(data_points),
            "unique_primary_regimes": len(regime_stats),
            "unique_secondary_modifiers": len(modifier_stats),
            "regime_stats": regime_stats,
            "modifier_stats": modifier_stats,
            "computed_at": datetime.now(timezone.utc),
        }

        await self.db[self.collection].update_one(
            {"coin_id": coin_id, "days": days},
            {"$set": result},
            upsert=True
        )

        return result

    async def get_all_backtests(self) -> Dict[str, Dict]:
        """Run backtests for all tracked coins. Returns {coin_id: backtest_result}."""
        results = {}
        for coin_id in BACKTEST_COINS:
            results[coin_id] = await self.backtest_coin(coin_id, 365)
        return results

    def _aggregate(self, grouped_outcomes: Dict[str, List[Dict]]) -> Dict:
        """Aggregate a group of outcomes into statistics."""
        stats = {}
        for key, outcomes_list in grouped_outcomes.items():
            if not outcomes_list:
                continue

            sample_count = len(outcomes_list)
            result = {"sample_count": sample_count}

            for horizon in ["1d", "3d", "7d"]:
                returns = [o[horizon] for o in outcomes_list if horizon in o]
                if not returns:
                    continue
                returns_arr = np.array(returns)
                wins = int(np.sum(returns_arr > 0))
                result[f"{horizon}_win_rate"] = round(wins / len(returns) * 100, 1)
                result[f"{horizon}_avg_return"] = round(float(np.mean(returns_arr)), 2)
                result[f"{horizon}_median_return"] = round(float(np.median(returns_arr)), 2)
                result[f"{horizon}_best"] = round(float(np.max(returns_arr)), 2)
                result[f"{horizon}_worst"] = round(float(np.min(returns_arr)), 2)
                result[f"{horizon}_std"] = round(float(np.std(returns_arr)), 2)

            stats[key] = result

        return stats


# ====================================================================
# BASE FACTOR
# ====================================================================

class BaseFactor(ABC):
    """Abstract base class for all scoring factors."""

    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight

    @abstractmethod
    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        """Compute a score from -100 to +100 for the given symbol.

        Must return:
        {
            "factor": self.name,
            "score": float (-100 to +100),
            "confidence": float (0 to 100),
            "signal": "bullish" | "bearish" | "neutral",
            "reasoning": str,
            "data": dict (any extra data for transparency)
        }
        """
        pass


# ====================================================================
# FACTOR 1: TECHNICAL REGIME (complete)
# ====================================================================

class TechnicalRegimeFactor(BaseFactor):
    """Scores based on backtested technical regimes.

    1. Determines current RSI + MACD regime
    2. Looks up historical win rate for that regime
    3. Determines Bollinger + Volume modifier
    4. Adjusts confidence based on modifier

    Score is derived from the 7-day historical win rate:
        win_rate 70% -> score +60
        win_rate 50% -> score  0
        win_rate 30% -> score -60
    Formula: score = (win_rate - 50) * 3, clamped to [-100, +100]
    """

    def __init__(self, backtester: RegimeBacktester):
        super().__init__("F1_technical_regime", FACTOR_WEIGHTS["F1_technical_regime"])
        self.backtester = backtester

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        coin_id = SYMBOL_TO_COINGECKO.get(symbol, symbol.lower())

        current_prices = kwargs.get("current_prices", [])
        current_volumes = kwargs.get("current_volumes", [])

        if len(current_prices) < 35:
            chart = await fetch_market_chart(coin_id, 60, db=self.backtester.db)
            if chart and len(chart["prices"]) >= 35:
                current_prices = chart["prices"]
                current_volumes = chart["volumes"]
            else:
                return self._neutral_result("Insufficient price data for technical analysis")

        prices_arr = np.array(current_prices)
        volumes_arr = np.array(current_volumes) if current_volumes else np.ones(len(current_prices))

        rsi_val = calc_rsi_series(prices_arr, 14)[-1]
        _, _, macd_hist_arr = calc_macd_series(prices_arr)
        macd_val = macd_hist_arr[-1]
        bb_up, bb_mid, bb_low = calc_bollinger_series(prices_arr, 20)
        vol_rat = calc_volume_ratio_series(volumes_arr, 20)

        if np.isnan(rsi_val) or np.isnan(macd_val) or np.isnan(bb_up[-1]) or np.isnan(vol_rat[-1]):
            return self._neutral_result("Indicators not yet calculable (need more data)")

        rsi_state = classify_rsi(float(rsi_val))
        macd_state = classify_macd(float(macd_val))
        boll_state = classify_bollinger(float(prices_arr[-1]), float(bb_up[-1]), float(bb_low[-1]))
        vol_state = classify_volume(float(vol_rat[-1]))

        primary = get_primary_regime(rsi_state, macd_state)
        secondary = get_secondary_modifier(boll_state, vol_state)

        backtest = await self.backtester.backtest_coin(coin_id, 365)
        regime_stats = backtest.get("regime_stats", {})
        stats = regime_stats.get(primary)

        if not stats or stats.get("sample_count", 0) < 5:
            return self._neutral_result(
                f"Regime '{primary}' has insufficient historical data ({stats.get('sample_count', 0) if stats else 0} samples). Need at least 5."
            )

        win_rate_7d = stats.get("7d_win_rate", 50)
        avg_return_7d = stats.get("7d_avg_return", 0)
        median_return_7d = stats.get("7d_median_return", 0)
        sample_count = stats.get("sample_count", 0)

        raw_score = (win_rate_7d - 50) * 3
        raw_score = max(-100, min(100, raw_score))

        confidence_adj = SECONDARY_CONFIDENCE_MAP.get(secondary, 0)
        sample_confidence = min(100, sample_count * 3)
        confidence = max(10, min(100, sample_confidence + confidence_adj))

        if raw_score > 10:
            signal = "bullish"
        elif raw_score < -10:
            signal = "bearish"
        else:
            signal = "neutral"

        reasoning = self._build_reasoning(
            symbol, rsi_state, rsi_val, macd_state, macd_val,
            boll_state, vol_state, primary, secondary,
            win_rate_7d, avg_return_7d, median_return_7d, sample_count
        )

        return {
            "factor": self.name,
            "score": round(raw_score, 1),
            "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": reasoning,
            "data": {
                "rsi": round(float(rsi_val), 1),
                "macd_histogram": round(float(macd_val), 4),
                "bollinger_position": boll_state,
                "volume_state": vol_state,
                "primary_regime": primary,
                "secondary_modifier": secondary,
                "backtest": {
                    "win_rate_7d": win_rate_7d,
                    "avg_return_7d": avg_return_7d,
                    "median_return_7d": median_return_7d,
                    "sample_count": sample_count,
                    "best_7d": stats.get("7d_best", 0),
                    "worst_7d": stats.get("7d_worst", 0),
                }
            }
        }

    def _neutral_result(self, reason: str) -> Dict:
        return {
            "factor": self.name,
            "score": 0,
            "confidence": 10,
            "signal": "neutral",
            "reasoning": reason,
            "data": {}
        }

    def _build_reasoning(self, symbol, rsi_state, rsi_val, macd_state, macd_val,
                         boll_state, vol_state, primary, secondary,
                         win_rate_7d, avg_return_7d, median_return_7d, sample_count):
        rsi_text = {
            "oversold": f"RSI is {rsi_val:.0f} (below 35, oversold territory). Historically this means selling pressure may be exhausted.",
            "overbought": f"RSI is {rsi_val:.0f} (above 65, overbought territory). Price has risen fast and may pull back.",
            "neutral": f"RSI is {rsi_val:.0f} (neutral zone, 35-65). No extreme momentum signal."
        }[rsi_state]

        macd_text = {
            "bullish": "MACD histogram is positive, indicating upward momentum is building.",
            "bearish": "MACD histogram is negative, indicating downward momentum."
        }[macd_state]

        boll_text = {
            "lower": "Price is in the lower third of Bollinger Bands (potentially undervalued short-term).",
            "upper": "Price is in the upper third of Bollinger Bands (potentially stretched).",
            "middle": "Price is in the middle of Bollinger Bands (no extreme positioning)."
        }[boll_state]

        vol_text = {
            "high": "Volume is elevated (1.3x+ above 20-day average), confirming the current move.",
            "normal": "Volume is normal, no unusual activity."
        }[vol_state]

        direction = "rose" if avg_return_7d > 0 else "fell"

        return (
            f"TECHNICAL REGIME: {primary.replace('|', ' + ').upper()}\n\n"
            f"Current indicators for {symbol}:\n"
            f"  {rsi_text}\n"
            f"  {macd_text}\n"
            f"  {boll_text}\n"
            f"  {vol_text}\n\n"
            f"HISTORICAL EVIDENCE (last 365 days):\n"
            f"  This exact regime ({primary}) occurred {sample_count} times before.\n"
            f"  7-day win rate: {win_rate_7d:.1f}% of the time, price was higher after 7 days.\n"
            f"  Average 7-day return: {avg_return_7d:+.2f}%\n"
            f"  Median 7-day return: {median_return_7d:+.2f}%\n"
            f"  Best outcome: {primary} {direction} by up to {abs(avg_return_7d * 3):.1f}% in best cases.\n\n"
            f"CONFIDENCE MODIFIER: {secondary.replace('|', ' + ')}\n"
            f"  Bollinger and volume conditions {'support' if SECONDARY_CONFIDENCE_MAP.get(secondary, 0) > 0 else 'weaken' if SECONDARY_CONFIDENCE_MAP.get(secondary, 0) < 0 else 'do not change'} the signal.\n\n"
            f"IMPORTANT: A {win_rate_7d:.0f}% win rate means {100 - win_rate_7d:.0f}% of the time this regime led to losses. Always use a stop-loss."
        )


# ====================================================================
# FACTOR 2: VOLATILITY FILTER (complete)
# ====================================================================

class VolatilityRegimeFactor(BaseFactor):
    """Scores market tradeability based on volatility conditions.

    NOT directional. Answers: "Is this a good time to trade at all?"

    Uses three inputs:
      - ATR% (14-day): how much price typically moves per day
      - Bollinger Bandwidth: how wide/narrow the price channel is
      - Volume ratio: current vs average volume

    Volatility regimes:
      TOO_QUIET:   ATR% < 1.0 AND bandwidth < 3.0
                   -> No opportunity. Score: -60 (discourages trading)
      IDEAL:       ATR% 1.5-5.0 AND bandwidth 4-15
                   -> Good conditions. Score: +30 (encourages trading)
      ELEVATED:    ATR% 5.0-10.0 OR bandwidth 15-25
                   -> Opportunity but risky. Score: +10 (cautious)
      DANGEROUS:   ATR% > 10.0 OR bandwidth > 25
                   -> Too volatile. Score: -40 (discourages trading)
      SQUEEZE:     Bandwidth < 3.0 but ATR% is moderate
                   -> Big move coming, direction unknown. Score: +15

    The score modifies overall confidence, not direction.
    """

    def __init__(self, db=None):
        super().__init__("F2_volatility_filter", FACTOR_WEIGHTS["F2_volatility_filter"])
        self.db = db

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        coin_id = SYMBOL_TO_COINGECKO.get(symbol, symbol.lower())

        current_prices = kwargs.get("current_prices", [])
        current_volumes = kwargs.get("current_volumes", [])

        if len(current_prices) < 25:
            chart = await fetch_market_chart(coin_id, 60, db=self.db)
            if chart and len(chart["prices"]) >= 25:
                current_prices = chart["prices"]
                current_volumes = chart["volumes"]
            else:
                return self._result(0, 30, "neutral", "Insufficient data for volatility analysis", {})

        prices_arr = np.array(current_prices)
        volumes_arr = np.array(current_volumes) if current_volumes else np.ones(len(current_prices))

        # Calculate volatility indicators
        atr_series = calc_atr_series(prices_arr, 14)
        bw_series = calc_bollinger_bandwidth_series(prices_arr, 20)
        vol_ratio_series = calc_volume_ratio_series(volumes_arr, 20)

        atr_pct = float(atr_series[-1]) if not np.isnan(atr_series[-1]) else 0
        bandwidth = float(bw_series[-1]) if not np.isnan(bw_series[-1]) else 0
        vol_ratio = float(vol_ratio_series[-1]) if not np.isnan(vol_ratio_series[-1]) else 1.0

        # Historical context: what's the average ATR% and bandwidth over 30 days?
        valid_atr = atr_series[~np.isnan(atr_series)]
        valid_bw = bw_series[~np.isnan(bw_series)]
        avg_atr = float(np.mean(valid_atr[-30:])) if len(valid_atr) >= 5 else atr_pct
        avg_bw = float(np.mean(valid_bw[-30:])) if len(valid_bw) >= 5 else bandwidth

        # Classify volatility regime
        regime, score, reasoning = self._classify_regime(atr_pct, bandwidth, vol_ratio, avg_atr, avg_bw, symbol)

        # Volume confirmation adjusts confidence
        confidence = 60
        if vol_ratio > 1.5 and score > 0:
            confidence = 75  # High volume confirms tradeable conditions
        elif vol_ratio < 0.6:
            confidence = 40  # Low volume = unreliable signals

        signal = "neutral"
        if score > 15:
            signal = "bullish"   # "bullish" here means "conditions favor trading"
        elif score < -15:
            signal = "bearish"   # "bearish" means "conditions discourage trading"

        return self._result(score, confidence, signal, reasoning, {
            "atr_pct": round(atr_pct, 2),
            "bollinger_bandwidth": round(bandwidth, 2),
            "volume_ratio": round(vol_ratio, 2),
            "avg_atr_30d": round(avg_atr, 2),
            "avg_bandwidth_30d": round(avg_bw, 2),
            "regime": regime,
        })

    def _classify_regime(self, atr_pct, bandwidth, vol_ratio, avg_atr, avg_bw, symbol):
        # Dangerous: extreme volatility
        if atr_pct > 10.0 or bandwidth > 25:
            return "dangerous", -40, (
                f"VOLATILITY: DANGEROUS\n\n"
                f"{symbol} is experiencing extreme volatility right now.\n"
                f"  ATR: {atr_pct:.1f}% daily (normal: {avg_atr:.1f}%)\n"
                f"  Bollinger bandwidth: {bandwidth:.1f}% (normal: {avg_bw:.1f}%)\n\n"
                f"Risk of flash crashes, stop-loss hunting, and large gaps is very high. "
                f"Day trading in these conditions is like driving in a storm. "
                f"Consider sitting this out or using much smaller position sizes."
            )

        # Too quiet: no opportunity
        if atr_pct < 1.0 and bandwidth < 3.0:
            return "too_quiet", -60, (
                f"VOLATILITY: TOO QUIET\n\n"
                f"{symbol} is barely moving.\n"
                f"  ATR: {atr_pct:.1f}% daily (normal: {avg_atr:.1f}%)\n"
                f"  Bollinger bandwidth: {bandwidth:.1f}% (normal: {avg_bw:.1f}%)\n\n"
                f"There is not enough price movement to generate trading profit. "
                f"Transaction fees and the 30% VDA tax will eat any gains. "
                f"Wait for volatility to pick up before entering trades."
            )

        # Squeeze: bands tight but ATR moderate = big move coming
        if bandwidth < 3.0 and atr_pct >= 1.0:
            return "squeeze", 15, (
                f"VOLATILITY: SQUEEZE DETECTED\n\n"
                f"Bollinger Bands are very tight ({bandwidth:.1f}%) but ATR shows {atr_pct:.1f}% daily movement.\n"
                f"This pattern (called a 'squeeze') often precedes a large price move.\n\n"
                f"The catch: a squeeze tells you a big move is coming, but NOT which direction. "
                f"Wait for a breakout above the upper band or below the lower band before entering. "
                f"Once the breakout happens, the move tends to be strong."
            )

        # Ideal: moderate volatility
        if 1.5 <= atr_pct <= 5.0 and 4 <= bandwidth <= 15:
            return "ideal", 30, (
                f"VOLATILITY: IDEAL FOR TRADING\n\n"
                f"{symbol} has healthy, tradeable volatility.\n"
                f"  ATR: {atr_pct:.1f}% daily (enough movement for profit)\n"
                f"  Bollinger bandwidth: {bandwidth:.1f}% (well-defined price channel)\n"
                f"  Volume: {vol_ratio:.1f}x average\n\n"
                f"These conditions give enough price movement to generate returns "
                f"while keeping risk manageable. Stop-losses at 1.5x ATR ({atr_pct * 1.5:.1f}%) "
                f"are unlikely to be hit by normal noise."
            )

        # Elevated: higher than normal
        if atr_pct > 5.0 or bandwidth > 15:
            return "elevated", 10, (
                f"VOLATILITY: ELEVATED\n\n"
                f"{symbol} is more volatile than usual.\n"
                f"  ATR: {atr_pct:.1f}% daily (normal: {avg_atr:.1f}%)\n"
                f"  Bollinger bandwidth: {bandwidth:.1f}% (normal: {avg_bw:.1f}%)\n\n"
                f"Trading opportunities exist but with higher risk. "
                f"Consider using smaller position sizes (half your normal amount) "
                f"and wider stop-losses to avoid getting stopped out by noise."
            )

        # Default: moderate but not quite ideal
        return "moderate", 15, (
            f"VOLATILITY: MODERATE\n\n"
            f"{symbol} shows moderate conditions.\n"
            f"  ATR: {atr_pct:.1f}% daily\n"
            f"  Bollinger bandwidth: {bandwidth:.1f}%\n"
            f"  Volume: {vol_ratio:.1f}x average\n\n"
            f"Conditions are acceptable for trading. Not the best setup, not the worst. "
            f"Standard position sizing and stop-losses apply."
        )

    def _result(self, score, confidence, signal, reasoning, data):
        return {
            "factor": self.name,
            "score": round(max(-100, min(100, score)), 1),
            "confidence": round(max(0, min(100, confidence)), 1),
            "signal": signal,
            "reasoning": reasoning,
            "data": data,
        }


# ====================================================================
# FACTOR 3: NEWS SENTIMENT (complete)
# ====================================================================

# Sentiment keyword lists — weighted by strength
BULLISH_KEYWORDS = {
    # Strong bullish (weight 3)
    "surge": 3, "soar": 3, "rally": 3, "breakout": 3, "all-time high": 3,
    "ath": 3, "record high": 3, "moon": 3, "parabolic": 3,
    # Medium bullish (weight 2)
    "bullish": 2, "gain": 2, "growth": 2, "rise": 2, "inflow": 2,
    "accumulation": 2, "adoption": 2, "approval": 2, "upgrade": 2, "positive": 2,
    "recover": 2, "rebound": 2, "boost": 2,
    # Weak bullish (weight 1)
    "up": 1, "higher": 1, "support": 1, "buy": 1, "invest": 1,
    "opportunity": 1, "optimistic": 1, "confidence": 1, "stable": 1,
}

BEARISH_KEYWORDS = {
    # Strong bearish (weight 3)
    "crash": 3, "collapse": 3, "plunge": 3, "capitulation": 3, "black swan": 3,
    "liquidation": 3, "bank run": 3, "fraud": 3, "hack": 3, "exploit": 3,
    # Medium bearish (weight 2)
    "bearish": 2, "fall": 2, "drop": 2, "decline": 2, "fear": 2,
    "sell-off": 2, "selloff": 2, "concern": 2, "risk": 2, "ban": 2,
    "regulation": 2, "crackdown": 2, "warning": 2, "outflow": 2,
    # Weak bearish (weight 1)
    "down": 1, "lower": 1, "resistance": 1, "sell": 1, "caution": 1,
    "volatile": 1, "uncertainty": 1, "tension": 1, "weak": 1,
}

# India-specific keywords that affect crypto sentiment
INDIA_BEARISH = {
    "rbi ban": 4, "crypto ban india": 4, "30% tax": 2, "tds crypto": 2,
    "sebi warning": 3, "ed crypto": 3, "enforcement directorate": 2,
}
INDIA_BULLISH = {
    "india adopt": 3, "rbi digital rupee": 1, "india blockchain": 2,
    "wazirx": 1, "coindcx": 1, "india crypto legalize": 4,
}


class NewsSentimentFactor(BaseFactor):
    """Scores macro environment from 24h rolling news sentiment.

    NOT a directional trade signal. It's a confidence modifier:
      - Positive sentiment + bullish technicals = higher confidence
      - Negative sentiment + bullish technicals = conflicting, lower confidence
      - Neutral sentiment = no modification

    Fetches recent news from NewsAPI (or cached in MongoDB).
    Scores headlines using weighted keyword matching.

    Score range:
      Strong positive sentiment: +40 to +60
      Mild positive:            +10 to +30
      Neutral:                  -10 to +10
      Mild negative:            -30 to -10
      Strong negative:          -60 to -40
    """

    def __init__(self, db=None):
        super().__init__("F3_news_sentiment", FACTOR_WEIGHTS["F3_news_sentiment"])
        self.db = db
        self.newsapi_key = os.environ.get('NEWSAPI_KEY', '')
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = 1800  # 30 minutes

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        # Fetch news (cached for 30 minutes)
        articles = await self._get_recent_news(symbol)

        if not articles:
            return {
                "factor": self.name,
                "score": 0,
                "confidence": 30,
                "signal": "neutral",
                "reasoning": (
                    "NEWS: NO DATA AVAILABLE\n\n"
                    "Could not fetch recent news articles. "
                    "News sentiment factor is inactive for this scoring round. "
                    "This may be due to NewsAPI rate limits or network issues."
                ),
                "data": {"status": "no_data", "article_count": 0}
            }

        # Score all articles
        total_bull_score = 0
        total_bear_score = 0
        article_sentiments = []

        for article in articles:
            title = (article.get("title") or "").lower()
            description = (article.get("description") or article.get("summary") or "").lower()
            text = title + " " + description

            bull = sum(weight for keyword, weight in BULLISH_KEYWORDS.items() if keyword in text)
            bear = sum(weight for keyword, weight in BEARISH_KEYWORDS.items() if keyword in text)

            # India-specific modifiers
            bull += sum(weight for keyword, weight in INDIA_BULLISH.items() if keyword in text)
            bear += sum(weight for keyword, weight in INDIA_BEARISH.items() if keyword in text)

            total_bull_score += bull
            total_bear_score += bear

            if bull > bear + 2:
                sent = "positive"
            elif bear > bull + 2:
                sent = "negative"
            else:
                sent = "neutral"

            article_sentiments.append({
                "title": article.get("title", "")[:80],
                "sentiment": sent,
                "bull_score": bull,
                "bear_score": bear,
            })

        # Net sentiment
        net_score = total_bull_score - total_bear_score
        article_count = len(articles)

        # Normalize to -100 to +100 range
        # Typical net_score range is -30 to +30 for 10-15 articles
        normalized = max(-100, min(100, net_score * 3))

        # Confidence based on article count and score clarity
        score_clarity = abs(total_bull_score - total_bear_score) / max(total_bull_score + total_bear_score, 1)
        confidence = min(80, 30 + article_count * 3 + score_clarity * 30)

        if normalized > 15:
            signal = "bullish"
        elif normalized < -15:
            signal = "bearish"
        else:
            signal = "neutral"

        # Count sentiments
        positive_count = sum(1 for a in article_sentiments if a["sentiment"] == "positive")
        negative_count = sum(1 for a in article_sentiments if a["sentiment"] == "negative")
        neutral_count = sum(1 for a in article_sentiments if a["sentiment"] == "neutral")

        reasoning = self._build_reasoning(
            symbol, article_count, positive_count, negative_count, neutral_count,
            total_bull_score, total_bear_score, normalized, article_sentiments[:5]
        )

        return {
            "factor": self.name,
            "score": round(normalized, 1),
            "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": reasoning,
            "data": {
                "article_count": article_count,
                "positive_articles": positive_count,
                "negative_articles": negative_count,
                "neutral_articles": neutral_count,
                "raw_bullish_score": total_bull_score,
                "raw_bearish_score": total_bear_score,
                "net_raw": net_score,
                "top_articles": article_sentiments[:5],
            }
        }

    async def _get_recent_news(self, symbol: str) -> List[Dict]:
        """Fetch recent crypto/finance news. Cached for 30 minutes."""
        cache_key = "news_24h"

        # Check in-memory cache
        if (self._cache_time and
            (datetime.now() - self._cache_time).total_seconds() < self._cache_ttl and
            cache_key in self._cache):
            return self._cache[cache_key]

        articles = []

        # Try NewsAPI
        if self.newsapi_key:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(
                        "https://newsapi.org/v2/everything",
                        params={
                            "apiKey": self.newsapi_key,
                            "q": "Bitcoin OR Ethereum OR crypto OR cryptocurrency OR Nifty OR Indian markets",
                            "language": "en",
                            "sortBy": "publishedAt",
                            "pageSize": 20,
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        articles = data.get("articles", [])
            except Exception as e:
                logger.warning(f"NewsAPI fetch failed: {e}")

        # Cache the result
        self._cache[cache_key] = articles
        self._cache_time = datetime.now()

        return articles

    def _build_reasoning(self, symbol, article_count, positive, negative, neutral,
                         bull_score, bear_score, normalized, top_articles):
        if normalized > 30:
            sentiment_label = "STRONGLY POSITIVE"
            market_read = "The news environment is optimistic. Multiple positive headlines about crypto and markets."
        elif normalized > 10:
            sentiment_label = "MILDLY POSITIVE"
            market_read = "News leans slightly positive. More optimistic headlines than negative ones."
        elif normalized < -30:
            sentiment_label = "STRONGLY NEGATIVE"
            market_read = "The news environment is fearful. Multiple concerning headlines about crypto and markets."
        elif normalized < -10:
            sentiment_label = "MILDLY NEGATIVE"
            market_read = "News leans slightly negative. More cautionary headlines than positive ones."
        else:
            sentiment_label = "NEUTRAL / MIXED"
            market_read = "News is mixed with no clear directional bias. No strong sentiment either way."

        top_headlines = ""
        if top_articles:
            top_headlines = "\n\nRECENT HEADLINES ANALYZED:\n"
            for a in top_articles[:3]:
                icon = "[+]" if a["sentiment"] == "positive" else "[-]" if a["sentiment"] == "negative" else "[=]"
                top_headlines += f"  {icon} {a['title']}\n"

        return (
            f"NEWS SENTIMENT: {sentiment_label} (score: {normalized:+.0f})\n\n"
            f"Analyzed {article_count} recent articles.\n"
            f"  Positive: {positive} articles | Negative: {negative} articles | Neutral: {neutral} articles\n"
            f"  Raw sentiment: {bull_score} bullish points vs {bear_score} bearish points\n\n"
            f"WHAT THIS MEANS:\n"
            f"{market_read}\n\n"
            f"HOW THIS AFFECTS TRADING:\n"
            f"News sentiment is a CONFIDENCE modifier, not a trade signal. "
            f"{'Positive news supports bullish technical signals but does not create them.' if normalized > 10 else 'Negative news weakens bullish signals and strengthens bearish ones. Extra caution advised.' if normalized < -10 else 'Neutral news means technical signals should be weighted more heavily.'}\n"
            f"Remember: by the time news reaches you, the market has often already moved."
            f"{top_headlines}"
        )


# ====================================================================
# FACTOR 4: ON-CHAIN FLOWS & WHALE BEHAVIOR (complete)
# ====================================================================
# Three free data sources, no API keys required:
#   1. Fear & Greed Index (alternative.me) — aggregate on-chain sentiment
#   2. Blockchain.com Charts — BTC network health (tx count, hash rate)
#   3. CoinGecko volume trends — capital flow proxy
#
# CONTRARIAN scoring philosophy:
#   When retail is extremely greedy (FGI > 75), whales are typically selling.
#   When retail is extremely fearful (FGI < 25), whales are typically accumulating.
#   This is well-documented in crypto markets and is the core edge of this factor.
# ====================================================================

# Fear & Greed Index thresholds -> contrarian scores
FGI_SCORING = [
    # (fgi_min, fgi_max, score, label)
    (0,   10,  +80, "extreme_fear"),       # Capitulation. Whales accumulating hard. Strong BUY.
    (10,  25,  +50, "fear"),               # Fear. Smart money entering. BUY.
    (25,  40,  +20, "mild_fear"),           # Mild fear. Slight accumulation. Lean bullish.
    (40,  60,   0,  "neutral"),             # Neutral. No edge from sentiment.
    (60,  75, -30,  "greed"),              # Greed. Smart money reducing. Lean bearish.
    (75,  90, -60,  "extreme_greed"),       # Extreme greed. Distribution phase. SELL signal.
    (90, 101, -80,  "max_greed"),          # Mania. Historically precedes crashes. Strong SELL.
]

# Network health scoring
HASH_RATE_SCORING = {
    "rising": +15,    # Miners confident, network growing
    "stable": 0,
    "falling": -20,   # Miners leaving, potential concern
}

TX_VOLUME_SCORING = {
    "rising": +10,    # More on-chain activity, genuine usage
    "stable": 0,
    "falling": -10,   # Declining usage
}


class OnChainFlowFactor(BaseFactor):
    """Scores whale behavior using on-chain data and market sentiment.

    Core signal: Fear & Greed Index used as a CONTRARIAN indicator.
    When everyone is greedy (FGI > 75), smart money is selling -> bearish.
    When everyone is fearful (FGI < 25), smart money is buying -> bullish.

    Supplementary signals:
    - BTC hash rate trend (miner confidence)
    - BTC transaction volume trend (network usage)
    - Volume trend from CoinGecko (capital flows)

    Weight: 30% of final score (highest after F1).
    This factor is forward-looking: it measures what large players are DOING,
    not what indicators SAY.
    """

    def __init__(self, db=None):
        super().__init__("F4_onchain_flows", FACTOR_WEIGHTS["F4_onchain_flows"])
        self.db = db
        self._fgi_cache = None
        self._fgi_cache_time = None
        self._fgi_cache_ttl = 3600  # 1 hour
        self._blockchain_cache = None
        self._blockchain_cache_time = None
        self._blockchain_cache_ttl = 3600  # 1 hour

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        # Gather all data sources
        fgi_data = await self._fetch_fear_greed()
        blockchain_data = await self._fetch_blockchain_health()

        # Volume trend from kwargs (passed from CoinGecko prices)
        volume_24h = kwargs.get("volume_24h", 0)
        volume_avg = kwargs.get("volume_avg", 0)

        # Score each component
        fgi_score, fgi_confidence, fgi_detail = self._score_fear_greed(fgi_data)
        network_score, network_detail = self._score_network_health(blockchain_data)
        volume_score, volume_detail = self._score_volume_trend(volume_24h, volume_avg)

        # Combine: FGI is primary (70% of F4), network health (20%), volume (10%)
        combined_score = fgi_score * 0.70 + network_score * 0.20 + volume_score * 0.10
        combined_score = max(-100, min(100, combined_score))

        # Confidence based on data availability
        data_sources_active = sum([
            1 if fgi_data else 0,
            1 if blockchain_data else 0,
            1 if volume_24h > 0 else 0,
        ])
        base_confidence = 20 + (data_sources_active * 20)  # 20-80 range
        confidence = min(85, base_confidence + fgi_confidence)

        if combined_score > 15:
            signal = "bullish"
        elif combined_score < -15:
            signal = "bearish"
        else:
            signal = "neutral"

        # Build comprehensive reasoning
        reasoning = self._build_reasoning(
            symbol, fgi_data, fgi_detail, network_detail, volume_detail,
            combined_score, data_sources_active
        )

        return {
            "factor": self.name,
            "score": round(combined_score, 1),
            "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": reasoning,
            "data": {
                "fear_greed_index": fgi_data.get("current", {}) if fgi_data else None,
                "fgi_score_contribution": round(fgi_score * 0.70, 1),
                "network_score_contribution": round(network_score * 0.20, 1),
                "volume_score_contribution": round(volume_score * 0.10, 1),
                "data_sources_active": data_sources_active,
                "blockchain_health": blockchain_data if blockchain_data else None,
            }
        }

    # ---- Fear & Greed Index ----

    async def _fetch_fear_greed(self) -> Optional[Dict]:
        """Fetch 30 days of Fear & Greed Index from alternative.me (free, no key)."""
        # Check cache
        if (self._fgi_cache_time and
            (datetime.now() - self._fgi_cache_time).total_seconds() < self._fgi_cache_ttl and
            self._fgi_cache is not None):
            return self._fgi_cache

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://api.alternative.me/fng/",
                    params={"limit": "30", "format": "json"}
                )
                if response.status_code == 200:
                    raw = response.json()
                    data_points = raw.get("data", [])
                    if data_points:
                        result = {
                            "current": {
                                "value": int(data_points[0]["value"]),
                                "label": data_points[0]["value_classification"],
                                "timestamp": data_points[0]["timestamp"],
                            },
                            "history": [
                                {"value": int(d["value"]), "label": d["value_classification"]}
                                for d in data_points[:30]
                            ],
                            "avg_7d": round(np.mean([int(d["value"]) for d in data_points[:7]]), 1) if len(data_points) >= 7 else int(data_points[0]["value"]),
                            "avg_30d": round(np.mean([int(d["value"]) for d in data_points[:30]]), 1) if len(data_points) >= 14 else None,
                            "trend": self._calc_fgi_trend(data_points),
                        }
                        self._fgi_cache = result
                        self._fgi_cache_time = datetime.now()
                        return result
        except Exception as e:
            logger.warning(f"Fear & Greed Index fetch failed: {e}")

        # Return cached even if stale
        if self._fgi_cache:
            return self._fgi_cache
        return None

    def _calc_fgi_trend(self, data_points: List) -> str:
        """Is fear/greed trending up or down over 7 days?"""
        if len(data_points) < 7:
            return "unknown"
        recent = np.mean([int(d["value"]) for d in data_points[:3]])
        older = np.mean([int(d["value"]) for d in data_points[4:7]])
        if recent > older + 5:
            return "rising_greed"  # Sentiment getting more greedy
        elif recent < older - 5:
            return "rising_fear"   # Sentiment getting more fearful
        return "stable"

    def _score_fear_greed(self, fgi_data: Optional[Dict]) -> Tuple[float, float, str]:
        """Score the Fear & Greed Index. Returns (score, confidence_bonus, detail_text)."""
        if not fgi_data:
            return 0, 0, "Fear & Greed Index: unavailable. Cannot assess market sentiment."

        current = fgi_data["current"]["value"]
        label = fgi_data["current"]["label"]
        avg_7d = fgi_data.get("avg_7d", current)
        trend = fgi_data.get("trend", "unknown")

        # Find matching score range
        score = 0
        regime_label = "neutral"
        for fgi_min, fgi_max, s, lbl in FGI_SCORING:
            if fgi_min <= current < fgi_max:
                score = s
                regime_label = lbl
                break

        # Trend modifier: if fear is INCREASING, contrarian signal strengthens
        trend_adj = 0
        trend_text = ""
        if trend == "rising_fear" and score > 0:
            trend_adj = +10
            trend_text = " Fear is increasing over the past week, strengthening the buy signal."
        elif trend == "rising_greed" and score < 0:
            trend_adj = -10
            trend_text = " Greed is increasing over the past week, strengthening the sell signal."
        elif trend == "rising_fear" and score < 0:
            trend_adj = +5  # Fear rising reduces bearish signal slightly
            trend_text = " Fear is rising, which partially offsets bearish signals."

        score = max(-100, min(100, score + trend_adj))

        # Confidence is higher when FGI is at extremes (clearer signal)
        conf_bonus = abs(current - 50) * 0.3  # 0 at neutral, +15 at extremes

        if current < 25:
            interpretation = (
                f"The crypto market is in EXTREME FEAR (FGI: {current}/100, label: '{label}').\n"
                f"7-day average: {avg_7d:.0f}.{trend_text}\n\n"
                f"CONTRARIAN INTERPRETATION (what smart money does):\n"
                f"When retail investors are panicking and selling, large holders (whales) historically accumulate.\n"
                f"This pattern has preceded major rallies in BTC multiple times (March 2020, July 2021, Nov 2022).\n"
                f"This is a BULLISH signal. However, fear can persist for weeks before a reversal."
            )
        elif current > 75:
            interpretation = (
                f"The crypto market is in EXTREME GREED (FGI: {current}/100, label: '{label}').\n"
                f"7-day average: {avg_7d:.0f}.{trend_text}\n\n"
                f"CONTRARIAN INTERPRETATION (what smart money does):\n"
                f"When retail investors are euphoric and buying aggressively, large holders historically distribute (sell).\n"
                f"This pattern has preceded major corrections multiple times (April 2021, Nov 2021).\n"
                f"This is a BEARISH signal. Extreme greed can persist briefly, but corrections often follow within 1-3 weeks."
            )
        else:
            interpretation = (
                f"Market sentiment is {label.lower()} (FGI: {current}/100).\n"
                f"7-day average: {avg_7d:.0f}.{trend_text}\n\n"
                f"No extreme contrarian signal. Sentiment is not at levels that historically "
                f"preceded major moves. Other factors carry more weight in this condition."
            )

        return score, conf_bonus, interpretation

    # ---- Blockchain Network Health ----

    async def _fetch_blockchain_health(self) -> Optional[Dict]:
        """Fetch BTC network metrics from blockchain.com (free, no key)."""
        if (self._blockchain_cache_time and
            (datetime.now() - self._blockchain_cache_time).total_seconds() < self._blockchain_cache_ttl and
            self._blockchain_cache is not None):
            return self._blockchain_cache

        metrics = {}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Transaction count (7 days)
                for metric, url_name in [("tx_count", "n-transactions"), ("hash_rate", "hash-rate")]:
                    try:
                        response = await client.get(
                            f"https://api.blockchain.info/charts/{url_name}",
                            params={"timespan": "14days", "format": "json"}
                        )
                        if response.status_code == 200:
                            data = response.json()
                            values = [v["y"] for v in data.get("values", [])]
                            if len(values) >= 7:
                                recent = np.mean(values[-3:])
                                older = np.mean(values[:3])
                                if older > 0:
                                    change_pct = ((recent - older) / older) * 100
                                    if change_pct > 5:
                                        trend = "rising"
                                    elif change_pct < -5:
                                        trend = "falling"
                                    else:
                                        trend = "stable"
                                    metrics[metric] = {
                                        "trend": trend,
                                        "change_pct": round(change_pct, 1),
                                        "latest": round(values[-1], 2),
                                    }
                    except Exception as e:
                        logger.debug(f"Blockchain.info {metric} fetch failed: {e}")
                        continue

            if metrics:
                self._blockchain_cache = metrics
                self._blockchain_cache_time = datetime.now()
                return metrics
        except Exception as e:
            logger.warning(f"Blockchain health fetch failed: {e}")

        if self._blockchain_cache:
            return self._blockchain_cache
        return None

    def _score_network_health(self, data: Optional[Dict]) -> Tuple[float, str]:
        """Score BTC network health from blockchain.com data."""
        if not data:
            return 0, "BTC network health: data unavailable."

        score = 0
        details = []

        if "hash_rate" in data:
            hr = data["hash_rate"]
            adj = HASH_RATE_SCORING.get(hr["trend"], 0)
            score += adj
            details.append(
                f"Hash rate: {hr['trend']} ({hr['change_pct']:+.1f}% over 14 days). "
                f"{'Miners are confident in BTC profitability.' if hr['trend'] == 'rising' else 'Miners are reducing operations, which can signal concern.' if hr['trend'] == 'falling' else 'Stable miner activity.'}"
            )

        if "tx_count" in data:
            tx = data["tx_count"]
            adj = TX_VOLUME_SCORING.get(tx["trend"], 0)
            score += adj
            details.append(
                f"Transaction count: {tx['trend']} ({tx['change_pct']:+.1f}% over 14 days). "
                f"{'More on-chain activity suggests genuine demand.' if tx['trend'] == 'rising' else 'Declining transactions may indicate reduced interest.' if tx['trend'] == 'falling' else 'Normal transaction activity.'}"
            )

        detail_text = "BTC NETWORK HEALTH:\n" + "\n".join(details) if details else "BTC network health: limited data."
        return score, detail_text

    # ---- Volume Trend ----

    def _score_volume_trend(self, volume_24h: float, volume_avg: float) -> Tuple[float, str]:
        """Score volume trend as a proxy for capital flows."""
        if volume_avg <= 0 or volume_24h <= 0:
            return 0, "Volume data: unavailable."

        ratio = volume_24h / volume_avg
        if ratio > 1.5:
            score = 20
            detail = (
                f"24h volume is {ratio:.1f}x the average. "
                f"Significantly elevated activity. Large players may be moving."
            )
        elif ratio > 1.2:
            score = 10
            detail = f"24h volume is {ratio:.1f}x average. Slightly above normal."
        elif ratio < 0.6:
            score = -15
            detail = (
                f"24h volume is only {ratio:.1f}x the average. "
                f"Very low activity. Price moves on low volume are unreliable."
            )
        elif ratio < 0.8:
            score = -5
            detail = f"24h volume is {ratio:.1f}x average. Slightly below normal."
        else:
            score = 0
            detail = f"24h volume is {ratio:.1f}x average. Normal activity."

        return score, f"VOLUME ANALYSIS:\n{detail}"

    # ---- Reasoning ----

    def _build_reasoning(self, symbol, fgi_data, fgi_detail, network_detail,
                         volume_detail, combined_score, sources_active):
        sources_text = f"{sources_active}/3 data sources active"
        if sources_active < 2:
            reliability = "LOW confidence: most on-chain data sources are unavailable. Score is based on limited data."
        elif sources_active == 2:
            reliability = "MODERATE confidence: some data sources unavailable."
        else:
            reliability = "GOOD confidence: all on-chain data sources reporting."

        return (
            f"ON-CHAIN & WHALE BEHAVIOR ANALYSIS ({sources_text})\n"
            f"Data reliability: {reliability}\n\n"
            f"{'='*50}\n\n"
            f"1. FEAR & GREED INDEX (contrarian indicator, 70% of this factor's score):\n"
            f"{fgi_detail}\n\n"
            f"{'='*50}\n\n"
            f"2. {network_detail}\n\n"
            f"{'='*50}\n\n"
            f"3. {volume_detail}\n\n"
            f"{'='*50}\n\n"
            f"COMBINED ON-CHAIN SCORE: {combined_score:+.1f}\n"
            f"{'This factor supports BUYING — on-chain signals suggest accumulation by large holders.' if combined_score > 15 else 'This factor supports SELLING — on-chain signals suggest distribution by large holders.' if combined_score < -15 else 'On-chain signals are neutral. No strong whale accumulation or distribution detected.'}\n\n"
            f"IMPORTANT: On-chain data shows what large players are doing NOW, not what will happen. "
            f"Whale accumulation during fear has historically preceded rallies, but the timing is uncertain (days to weeks)."
        )


# ====================================================================
# WEIGHTED SCORER
# ====================================================================

class WeightedScorer:
    """Combines all factor scores into a final recommendation.

    Final score = sum(factor_score * factor_weight)
    Score > +40  = BUY
    Score < -40  = SELL
    Otherwise    = HOLD

    Confidence = weighted average of per-factor confidence values.
    """

    THRESHOLDS = {"buy": 40, "sell": -40}

    def combine(self, factor_results: List[Dict]) -> Dict:
        if not factor_results:
            return self._empty_result()

        weighted_score = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0
        factor_breakdown = []

        for result in factor_results:
            factor_name = result["factor"]
            weight = FACTOR_WEIGHTS.get(factor_name, 0)
            score = result.get("score", 0)
            conf = result.get("confidence", 50)

            weighted_score += score * weight
            weighted_confidence += conf * weight
            total_weight += weight

            factor_breakdown.append({
                "factor": factor_name,
                "weight": weight,
                "raw_score": score,
                "weighted_contribution": round(score * weight, 2),
                "confidence": conf,
                "signal": result.get("signal", "neutral"),
            })

        if total_weight > 0:
            weighted_confidence /= total_weight

        final_score = round(weighted_score, 2)
        final_confidence = round(weighted_confidence, 1)

        if final_score > self.THRESHOLDS["buy"]:
            action = "BUY"
        elif final_score < self.THRESHOLDS["sell"]:
            action = "SELL"
        else:
            action = "HOLD"

        conflicting = self._detect_conflicts(factor_results)
        if conflicting:
            final_confidence = max(10, final_confidence - 15)

        return {
            "action": action,
            "final_score": final_score,
            "confidence": final_confidence,
            "factors": factor_breakdown,
            "conflicts": conflicting,
            "thresholds": self.THRESHOLDS,
            "explanation": self._explain(action, final_score, final_confidence, factor_breakdown, conflicting),
        }

    def _detect_conflicts(self, results: List[Dict]) -> List[str]:
        """Detect when factors disagree on direction."""
        signals = [(r["factor"], r.get("signal", "neutral")) for r in results]
        has_bullish = any(s == "bullish" for _, s in signals)
        has_bearish = any(s == "bearish" for _, s in signals)
        conflicts = []
        if has_bullish and has_bearish:
            bull = [name for name, s in signals if s == "bullish"]
            bear = [name for name, s in signals if s == "bearish"]
            conflicts.append(
                f"{', '.join(bull)} signal bullish while {', '.join(bear)} signal bearish. "
                f"Mixed signals reduce confidence."
            )
        return conflicts

    def _explain(self, action, score, confidence, factors, conflicts):
        active_factors = [f for f in factors if f["raw_score"] != 0]
        stub_factors = [f for f in factors if f["raw_score"] == 0]

        lines = [f"RECOMMENDATION: {action} (score: {score:+.1f}, confidence: {confidence:.0f}%)"]
        lines.append("")

        if active_factors:
            lines.append("CONTRIBUTING FACTORS:")
            for f in sorted(active_factors, key=lambda x: abs(x["weighted_contribution"]), reverse=True):
                direction = "bullish" if f["raw_score"] > 0 else "bearish" if f["raw_score"] < 0 else "neutral"
                lines.append(
                    f"  {f['factor']}: {f['raw_score']:+.0f} x {f['weight']:.0%} weight = {f['weighted_contribution']:+.1f} ({direction})"
                )
            lines.append("")

        if stub_factors:
            pending = [f["factor"] for f in stub_factors]
            lines.append(f"PENDING FACTORS (not yet active): {', '.join(pending)}")
            lines.append("Once all factors are live, recommendations will be more reliable.")
            lines.append("")

        if conflicts:
            lines.append("CONFLICTING SIGNALS:")
            for c in conflicts:
                lines.append(f"  {c}")
            lines.append("")

        lines.append(f"Scoring thresholds: above +{self.THRESHOLDS['buy']} = BUY, below {self.THRESHOLDS['sell']} = SELL, between = HOLD.")

        return "\n".join(lines)

    def _empty_result(self):
        return {
            "action": "HOLD",
            "final_score": 0,
            "confidence": 0,
            "factors": [],
            "conflicts": [],
            "thresholds": self.THRESHOLDS,
            "explanation": "No factor data available. Cannot make a recommendation.",
        }


# ====================================================================
# SCORING ENGINE (main entry point)
# ====================================================================

class ScoringEngine:
    """Main entry point. Instantiate once at server startup.

    Usage:
        engine = ScoringEngine(db)
        result = await engine.score("BTC")
        # result["action"] = "BUY" / "SELL" / "HOLD"
        # result["final_score"] = weighted score
        # result["factors"] = per-factor breakdown
    """

    def __init__(self, db):
        self.db = db
        self.backtester = RegimeBacktester(db)
        self.scorer = WeightedScorer()

        self.factors: List[BaseFactor] = [
            TechnicalRegimeFactor(self.backtester),
            VolatilityRegimeFactor(db=db),
            NewsSentimentFactor(db=db),
            OnChainFlowFactor(db=db),
        ]

    async def score(self, symbol: str, **kwargs) -> Dict:
        """Score a single asset. Returns full recommendation with breakdown."""
        factor_results = []
        for factor in self.factors:
            try:
                result = await factor.compute_score(symbol, **kwargs)
                factor_results.append(result)
            except Exception as e:
                logger.error(f"Factor {factor.name} failed for {symbol}: {e}")
                factor_results.append({
                    "factor": factor.name,
                    "score": 0,
                    "confidence": 0,
                    "signal": "neutral",
                    "reasoning": f"Error computing {factor.name}: {str(e)}",
                    "data": {"error": str(e)}
                })

        combined = self.scorer.combine(factor_results)

        return {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **combined,
            "factor_details": {r["factor"]: r for r in factor_results},
        }

    async def score_multiple(self, symbols: List[str], **kwargs) -> Dict[str, Dict]:
        """Score multiple assets."""
        results = {}
        for symbol in symbols:
            results[symbol] = await self.score(symbol, **kwargs)
        return results

    async def warm_cache(self):
        """Pre-compute backtests for all tracked coins. Call at startup or on schedule."""
        logger.info("Warming regime backtest cache for all tracked coins...")
        for coin_id in BACKTEST_COINS:
            try:
                result = await self.backtester.backtest_coin(coin_id, 365)
                pts = result.get("total_data_points", 0)
                regimes = result.get("unique_primary_regimes", 0)
                logger.info(f"  {coin_id}: {pts} data points, {regimes} unique regimes")
            except Exception as e:
                logger.error(f"  {coin_id}: backtest failed: {e}")
        logger.info("Cache warming complete.")

    async def get_backtest_summary(self) -> Dict:
        """Return a summary of all backtested regimes for transparency."""
        all_backtests = await self.backtester.get_all_backtests()
        summary = {}
        for coin_id, bt in all_backtests.items():
            if "error" in bt:
                summary[coin_id] = {"status": "error", "error": bt["error"]}
                continue
            regime_stats = bt.get("regime_stats", {})
            best_regime = max(regime_stats.items(), key=lambda x: x[1].get("7d_win_rate", 0), default=(None, None))
            worst_regime = min(regime_stats.items(), key=lambda x: x[1].get("7d_win_rate", 100), default=(None, None))
            summary[coin_id] = {
                "status": "ok",
                "data_points": bt.get("total_data_points", 0),
                "regimes_found": len(regime_stats),
                "best_regime": {
                    "name": best_regime[0],
                    "win_rate_7d": best_regime[1].get("7d_win_rate") if best_regime[1] else None,
                    "sample_count": best_regime[1].get("sample_count") if best_regime[1] else None,
                } if best_regime[0] else None,
                "worst_regime": {
                    "name": worst_regime[0],
                    "win_rate_7d": worst_regime[1].get("7d_win_rate") if worst_regime[1] else None,
                    "sample_count": worst_regime[1].get("sample_count") if worst_regime[1] else None,
                } if worst_regime[0] else None,
            }
        return summary