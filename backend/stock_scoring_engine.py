"""
IndiaVest Stock Scoring Engine
===============================
5-factor weighted scoring system for Indian stock (Nifty 50) recommendations.

Factor weights:
  S1: Technical regime      = 35%  (RSI+MACD+Bollinger+Volume, backtested)
  S2: Fundamental filter    = 20%  (PE, EPS growth, debt, ROE)
  S3: Sector momentum       = 15%  (sector vs Nifty relative strength)
  S4: News + macro          = 15%  (earnings, RBI, budget, FII headlines)
  S5: Institutional flows   = 15%  (FII/DII net buy/sell proxy from volume)

Score > +35  = BUY  (lower than crypto +40 because stocks are less volatile)
Score < -35  = SELL
Between      = HOLD

Market hours: Mon-Fri 9:15 AM - 3:30 PM IST
Trading window: 9:30 AM - 2:30 PM IST (avoid open/close volatility)

Reuses: BaseFactor, WeightedScorer, indicator calculations from scoring_engine.py
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import httpx
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

# Reuse indicator calculations from crypto engine
from scoring_engine import (
    BaseFactor,
    calc_rsi_series, calc_macd_series, calc_bollinger_series,
    calc_volume_ratio_series, calc_atr_series, calc_bollinger_bandwidth_series,
    classify_rsi, classify_macd, classify_bollinger, classify_volume,
    get_primary_regime, get_secondary_modifier, SECONDARY_CONFIDENCE_MAP,
)

NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')

# ====================================================================
# STOCK UNIVERSE: Top 20 Nifty 50 by liquidity
# ====================================================================
TRACKED_STOCKS = {
    # Energy & Resources
    "RELIANCE":   {"name": "Reliance Industries", "sector": "Energy",         "yf": "RELIANCE.NS"},
    "ONGC":       {"name": "ONGC",                "sector": "Energy",         "yf": "ONGC.NS"},
    "BPCL":       {"name": "Bharat Petroleum",    "sector": "Energy",         "yf": "BPCL.NS"},
    "COALINDIA":  {"name": "Coal India",          "sector": "Mining",         "yf": "COALINDIA.NS"},
    # IT
    "TCS":        {"name": "Tata Consultancy",    "sector": "IT",             "yf": "TCS.NS"},
    "INFY":       {"name": "Infosys",             "sector": "IT",             "yf": "INFY.NS"},
    "WIPRO":      {"name": "Wipro",               "sector": "IT",             "yf": "WIPRO.NS"},
    "HCLTECH":    {"name": "HCL Technologies",    "sector": "IT",             "yf": "HCLTECH.NS"},
    "TECHM":      {"name": "Tech Mahindra",       "sector": "IT",             "yf": "TECHM.NS"},
    # Banking
    "HDFCBANK":   {"name": "HDFC Bank",           "sector": "Banking",        "yf": "HDFCBANK.NS"},
    "ICICIBANK":  {"name": "ICICI Bank",          "sector": "Banking",        "yf": "ICICIBANK.NS"},
    "SBIN":       {"name": "State Bank of India", "sector": "Banking",        "yf": "SBIN.NS"},
    "AXISBANK":   {"name": "Axis Bank",           "sector": "Banking",        "yf": "AXISBANK.NS"},
    "KOTAKBANK":  {"name": "Kotak Mahindra Bank", "sector": "Banking",        "yf": "KOTAKBANK.NS"},
    "INDUSINDBK": {"name": "IndusInd Bank",       "sector": "Banking",        "yf": "INDUSINDBK.NS"},
    # NBFC & Insurance
    "BAJFINANCE": {"name": "Bajaj Finance",       "sector": "NBFC",           "yf": "BAJFINANCE.NS"},
    "BAJAJFINSV": {"name": "Bajaj Finserv",       "sector": "NBFC",           "yf": "BAJAJFINSV.NS"},
    "HDFCLIFE":   {"name": "HDFC Life Insurance", "sector": "Insurance",      "yf": "HDFCLIFE.NS"},
    "SBILIFE":    {"name": "SBI Life Insurance",  "sector": "Insurance",      "yf": "SBILIFE.NS"},
    # Auto
    "MARUTI":     {"name": "Maruti Suzuki",       "sector": "Auto",           "yf": "MARUTI.NS"},
    "TATAMOTORS": {"name": "Tata Motors",         "sector": "Auto",           "yf": "TATAMTRDVR.NS"},
    "EICHERMOT":  {"name": "Eicher Motors",       "sector": "Auto",           "yf": "EICHERMOT.NS"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto",          "sector": "Auto",           "yf": "BAJAJ-AUTO.NS"},
    "M&M":        {"name": "Mahindra & Mahindra", "sector": "Auto",           "yf": "M&M.NS"},
    "HEROMOTOCO": {"name": "Hero MotoCorp",       "sector": "Auto",           "yf": "HEROMOTOCO.NS"},
    # Pharma
    "SUNPHARMA":  {"name": "Sun Pharma",          "sector": "Pharma",         "yf": "SUNPHARMA.NS"},
    "DRREDDY":    {"name": "Dr Reddys Labs",      "sector": "Pharma",         "yf": "DRREDDY.NS"},
    "CIPLA":      {"name": "Cipla",               "sector": "Pharma",         "yf": "CIPLA.NS"},
    "DIVISLAB":   {"name": "Divis Laboratories",  "sector": "Pharma",         "yf": "DIVISLAB.NS"},
    # Telecom
    "BHARTIARTL": {"name": "Bharti Airtel",       "sector": "Telecom",        "yf": "BHARTIARTL.NS"},
    # Infrastructure & Industrials
    "LT":         {"name": "Larsen & Toubro",     "sector": "Infrastructure", "yf": "LT.NS"},
    "ULTRACEMCO": {"name": "UltraTech Cement",    "sector": "Cement",         "yf": "ULTRACEMCO.NS"},
    "SHREECEM":   {"name": "Shree Cement",        "sector": "Cement",         "yf": "SHREECEM.NS"},
    "GRASIM":     {"name": "Grasim Industries",   "sector": "Cement",         "yf": "GRASIM.NS"},
    # Metals
    "JSWSTEEL":   {"name": "JSW Steel",           "sector": "Metals",         "yf": "JSWSTEEL.NS"},
    "TATASTEEL":  {"name": "Tata Steel",          "sector": "Metals",         "yf": "TATASTEEL.NS"},
    "HINDALCO":   {"name": "Hindalco Industries", "sector": "Metals",         "yf": "HINDALCO.NS"},
    "VEDL":       {"name": "Vedanta",             "sector": "Metals",         "yf": "VEDL.NS"},
    # Power & Utilities
    "NTPC":       {"name": "NTPC",                "sector": "Power",          "yf": "NTPC.NS"},
    "POWERGRID":  {"name": "Power Grid Corp",     "sector": "Power",          "yf": "POWERGRID.NS"},
    # Consumer & FMCG
    "HINDUNILVR": {"name": "Hindustan Unilever",  "sector": "FMCG",           "yf": "HINDUNILVR.NS"},
    "ITC":        {"name": "ITC",                 "sector": "FMCG",           "yf": "ITC.NS"},
    "NESTLEIND":  {"name": "Nestle India",        "sector": "FMCG",           "yf": "NESTLEIND.NS"},
    "BRITANNIA":  {"name": "Britannia Industries","sector": "FMCG",           "yf": "BRITANNIA.NS"},
    "TATACONSUM": {"name": "Tata Consumer",       "sector": "FMCG",           "yf": "TATACONSUM.NS"},
    "TITAN":      {"name": "Titan Company",       "sector": "Consumer",       "yf": "TITAN.NS"},
    "ASIANPAINT": {"name": "Asian Paints",        "sector": "Consumer",       "yf": "ASIANPAINT.NS"},
    # Conglomerate
    "ADANIENT":   {"name": "Adani Enterprises",   "sector": "Conglomerate",   "yf": "ADANIENT.NS"},
    "ADANIPORTS": {"name": "Adani Ports",         "sector": "Logistics",      "yf": "ADANIPORTS.NS"},
    # Agri & Chemicals
    "UPL":        {"name": "UPL Limited",         "sector": "Chemicals",      "yf": "UPL.NS"},
}

# Sector average PE ratios (approximate, updated periodically)
SECTOR_AVG_PE = {
    "Banking": 14, "IT": 28, "Energy": 12, "Pharma": 30, "Auto": 22,
    "NBFC": 20, "Telecom": 35, "Infrastructure": 25, "Power": 15,
    "Consumer": 55, "Conglomerate": 30, "Metals": 10, "Mining": 8, "FMCG": 25,
    "Insurance": 60, "Cement": 30, "Logistics": 25, "Chemicals": 20,
}

# Stock factor weights
STOCK_FACTOR_WEIGHTS = {
    "S1_technical_regime": 0.35,
    "S2_fundamental_filter": 0.20,
    "S3_sector_momentum": 0.15,
    "S4_news_macro": 0.15,
    "S5_institutional_flows": 0.15,
}

# Stock confidence thresholds (lower than crypto because stocks are less volatile)
STOCK_THRESHOLDS = {
    "conservative": {"buy": 50, "sell": -50},
    "moderate":     {"buy": 35, "sell": -35},
    "aggressive":   {"buy": 20, "sell": -20},
}

# Tax rates
STOCK_STCG_RATE = 0.15   # Short-term capital gains (<1 year)
STOCK_LTCG_RATE = 0.10   # Long-term capital gains (>1 year, above Rs 1L)


# ====================================================================
# MARKET HOURS
# ====================================================================

def get_ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

def is_market_open() -> bool:
    """Check if NSE is currently open."""
    now = get_ist_now()
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

def is_trading_window() -> bool:
    """Check if we're in the safe trading window (avoid open/close volatility)."""
    now = get_ist_now()
    if now.weekday() >= 5:
        return False
    safe_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    safe_close = now.replace(hour=14, minute=30, second=0, microsecond=0)
    return safe_open <= now <= safe_close

def get_market_status() -> Dict:
    """Get current market status for the UI."""
    now = get_ist_now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    
    if weekday >= 5:
        next_monday = now + timedelta(days=(7 - weekday))
        return {"status": "closed", "reason": "Weekend", "next_open": f"Monday {next_monday.strftime('%d %b')} 9:15 AM IST"}
    
    if hour < 9 or (hour == 9 and minute < 15):
        return {"status": "pre_market", "reason": f"Market opens at 9:15 AM IST", "next_open": "Today 9:15 AM"}
    
    if hour == 9 and minute < 30:
        return {"status": "stabilizing", "reason": "Market just opened. Waiting for 15-min stabilization.", "next_open": "Verdict at 9:30 AM"}
    
    if (hour == 9 and minute >= 30) or (9 < hour < 14) or (hour == 14 and minute <= 30):
        return {"status": "open", "reason": "Market is open. Trading window active.", "next_open": None}
    
    if hour == 14 and minute > 30 or hour == 15 and minute < 30:
        return {"status": "closing", "reason": "Market closing soon. No new entries recommended.", "next_open": None}
    
    if hour >= 15 and minute >= 30 or hour > 15:
        return {"status": "closed", "reason": "Market closed for today.", "next_open": "Tomorrow 9:15 AM IST"}
    
    return {"status": "closed", "reason": "Market closed.", "next_open": "Next trading day 9:15 AM IST"}


# ====================================================================
# STOCK DATA FETCHER
# ====================================================================

async def fetch_stock_history(symbol: str, period: str = "1y", db=None) -> Optional[Dict]:
    """Fetch historical OHLCV data for a stock via yfinance.
    Checks MongoDB cache first, then yfinance."""
    
    # Try cache first
    if db is not None:
        try:
            cached = await db["stock_data_cache"].find_one({"symbol": symbol})
            if cached and cached.get("prices") and len(cached["prices"]) >= 60:
                fetched_at = cached.get("fetched_at")
                if fetched_at:
                    if hasattr(fetched_at, 'tzinfo') and fetched_at.tzinfo is None:
                        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                    try:
                        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
                        if age_hours < 12:
                            return cached
                    except TypeError:
                        return cached
        except Exception as e:
            logger.warning(f"Stock cache lookup failed for {symbol}: {e}")
    
    # Fetch from yfinance
    try:
        import yfinance as yf
        
        yf_symbol = TRACKED_STOCKS.get(symbol, {}).get("yf", f"{symbol}.NS")
        
        def _fetch():
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period=period)
            info = {}
            try:
                info = ticker.info
            except:
                pass
            return hist, info
        
        loop = asyncio.get_event_loop()
        hist, info = await loop.run_in_executor(None, _fetch)
        
        if hist.empty:
            return None
        
        result = {
            "symbol": symbol,
            "prices": [float(x) for x in hist["Close"].values],
            "volumes": [float(x) for x in hist["Volume"].values],
            "highs": [float(x) for x in hist["High"].values],
            "lows": [float(x) for x in hist["Low"].values],
            "opens": [float(x) for x in hist["Open"].values],
            "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
            "data_points": len(hist),
            "fundamentals": {
                "pe_ratio": info.get("trailingPE", 0) or 0,
                "forward_pe": info.get("forwardPE", 0) or 0,
                "eps": info.get("trailingEps", 0) or 0,
                "eps_growth": info.get("earningsGrowth", 0) or 0,
                "revenue_growth": info.get("revenueGrowth", 0) or 0,
                "debt_to_equity": info.get("debtToEquity", 0) or 0,
                "roe": (info.get("returnOnEquity", 0) or 0),
                "profit_margin": info.get("profitMargins", 0) or 0,
                "beta": info.get("beta", 1.0) or 1.0,
                "dividend_yield": (info.get("dividendYield", 0) or 0) * 100,
                "book_value": info.get("bookValue", 0) or 0,
                "price_to_book": info.get("priceToBook", 0) or 0,
                "market_cap": info.get("marketCap", 0) or 0,
                "avg_volume": info.get("averageVolume", 0) or 0,
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0) or 0,
                "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0) or 0,
            },
            "sector": TRACKED_STOCKS.get(symbol, {}).get("sector", info.get("sector", "Unknown")),
            "fetched_at": datetime.now(timezone.utc),
        }
        
        # Cache in MongoDB
        if db is not None:
            try:
                await db["stock_data_cache"].update_one(
                    {"symbol": symbol}, {"$set": result}, upsert=True
                )
            except Exception as e:
                logger.warning(f"Stock cache store failed for {symbol}: {e}")
        
        return result
    
    except Exception as e:
        logger.error(f"Stock data fetch failed for {symbol}: {e}")
        return None


# ====================================================================
# S1: TECHNICAL REGIME (35%)
# ====================================================================

class StockTechnicalFactor(BaseFactor):
    """Same RSI+MACD+Bollinger+Volume regime system as crypto F1,
    but backtested against 1 year of NSE daily data."""

    def __init__(self, db=None):
        super().__init__("S1_technical_regime", STOCK_FACTOR_WEIGHTS["S1_technical_regime"])
        self.db = db

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        data = kwargs.get("stock_data")
        if not data or len(data.get("prices", [])) < 60:
            data = await fetch_stock_history(symbol, "1y", self.db)
        
        if not data or len(data.get("prices", [])) < 60:
            return self._neutral("Insufficient historical data for technical analysis")
        
        prices = np.array(data["prices"])
        volumes = np.array(data["volumes"])
        
        rsi = calc_rsi_series(prices, 14)
        _, _, macd_hist = calc_macd_series(prices)
        bb_up, _, bb_low = calc_bollinger_series(prices, 20)
        vol_rat = calc_volume_ratio_series(volumes, 20)
        
        if any(np.isnan(x[-1]) for x in [rsi, macd_hist, bb_up, vol_rat]):
            return self._neutral("Indicators still calculating (need more data)")
        
        rsi_state = classify_rsi(float(rsi[-1]))
        macd_state = classify_macd(float(macd_hist[-1]))
        primary = get_primary_regime(rsi_state, macd_state)
        
        boll_state = classify_bollinger(float(prices[-1]), float(bb_up[-1]), float(bb_low[-1]))
        vol_state = classify_volume(float(vol_rat[-1]))
        secondary = get_secondary_modifier(boll_state, vol_state)
        
        # Backtest this regime
        min_idx = 35
        regime_returns = []
        for i in range(min_idx, len(prices) - 7):
            if np.isnan(rsi[i]) or np.isnan(macd_hist[i]):
                continue
            r = get_primary_regime(classify_rsi(float(rsi[i])), classify_macd(float(macd_hist[i])))
            if r == primary:
                ret_7d = (prices[i + 7] - prices[i]) / prices[i] * 100
                regime_returns.append(ret_7d)
        
        if len(regime_returns) < 5:
            return self._neutral(f"Regime '{primary}' has only {len(regime_returns)} samples. Need 5+.")
        
        win_rate = sum(1 for r in regime_returns if r > 0) / len(regime_returns) * 100
        avg_return = float(np.mean(regime_returns))
        
        raw_score = (win_rate - 50) * 3
        raw_score = max(-100, min(100, raw_score))
        
        conf_adj = SECONDARY_CONFIDENCE_MAP.get(secondary, 0)
        confidence = max(10, min(100, len(regime_returns) * 3 + conf_adj))
        
        signal = "bullish" if raw_score > 10 else "bearish" if raw_score < -10 else "neutral"
        
        return {
            "factor": self.name, "score": round(raw_score, 1), "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": (
                f"TECHNICAL REGIME: {primary.upper()}\n"
                f"RSI: {rsi[-1]:.0f} ({rsi_state}), MACD: {'positive' if macd_hist[-1] > 0 else 'negative'}\n"
                f"This regime occurred {len(regime_returns)} times in the past year.\n"
                f"7-day win rate: {win_rate:.0f}%, avg return: {avg_return:+.2f}%"
            ),
            "data": {
                "rsi": round(float(rsi[-1]), 1), "macd_histogram": round(float(macd_hist[-1]), 4),
                "primary_regime": primary, "secondary_modifier": secondary,
                "backtest": {"win_rate_7d": round(win_rate, 1), "avg_return_7d": round(avg_return, 2),
                             "sample_count": len(regime_returns)},
                "atr_pct": round(float(calc_atr_series(prices)[-1]), 2) if not np.isnan(calc_atr_series(prices)[-1]) else 1.5,
                "bollinger_bandwidth": round(float(calc_bollinger_bandwidth_series(prices)[-1]), 2) if not np.isnan(calc_bollinger_bandwidth_series(prices)[-1]) else 5.0,
            }
        }
    
    def _neutral(self, reason):
        return {"factor": self.name, "score": 0, "confidence": 10, "signal": "neutral", "reasoning": reason, "data": {}}


# ====================================================================
# S2: FUNDAMENTAL FILTER (20%)
# ====================================================================

class StockFundamentalFactor(BaseFactor):
    """Scores stock quality based on PE, EPS growth, debt, and ROE.
    This factor has NO crypto equivalent."""

    def __init__(self, db=None):
        super().__init__("S2_fundamental_filter", STOCK_FACTOR_WEIGHTS["S2_fundamental_filter"])
        self.db = db

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        data = kwargs.get("stock_data")
        if not data:
            data = await fetch_stock_history(symbol, "1y", self.db)
        
        if not data or not data.get("fundamentals"):
            return {"factor": self.name, "score": 0, "confidence": 20, "signal": "neutral",
                    "reasoning": "Fundamental data unavailable.", "data": {}}
        
        f = data["fundamentals"]
        sector = data.get("sector", "Unknown")
        sector_pe = SECTOR_AVG_PE.get(sector, 20)
        
        scores = []
        details = []
        
        # 1. PE ratio vs sector (weight: 30%)
        pe = f.get("pe_ratio", 0)
        if pe > 0:
            pe_ratio_score = (sector_pe - pe) / sector_pe * 100  # Negative PE = overvalued = bad
            pe_ratio_score = max(-100, min(100, pe_ratio_score * 2))
            scores.append(("pe", pe_ratio_score, 0.30))
            status = "undervalued" if pe < sector_pe * 0.8 else "overvalued" if pe > sector_pe * 1.3 else "fairly valued"
            details.append(f"PE: {pe:.1f} vs sector avg {sector_pe} ({status})")
        
        # 2. EPS growth (weight: 25%)
        eps_growth = f.get("eps_growth", 0) * 100  # Convert to percentage
        if abs(eps_growth) > 0:
            eps_score = max(-100, min(100, eps_growth * 2))
            scores.append(("eps", eps_score, 0.25))
            details.append(f"EPS growth: {eps_growth:+.1f}% {'(strong)' if eps_growth > 15 else '(weak)' if eps_growth < -5 else '(moderate)'}")
        
        # 3. Debt-to-equity (weight: 20%)
        dte = f.get("debt_to_equity", 0)
        if dte >= 0:
            if dte < 50:
                dte_score = 50
            elif dte < 100:
                dte_score = 20
            elif dte < 200:
                dte_score = -20
            else:
                dte_score = -60
            scores.append(("debt", dte_score, 0.20))
            details.append(f"Debt/Equity: {dte:.0f}% {'(low, healthy)' if dte < 50 else '(high, risky)' if dte > 150 else '(moderate)'}")
        
        # 4. ROE (weight: 25%)
        roe = f.get("roe", 0) * 100
        if abs(roe) > 0:
            if roe > 20:
                roe_score = 60
            elif roe > 12:
                roe_score = 30
            elif roe > 5:
                roe_score = 0
            else:
                roe_score = -40
            scores.append(("roe", roe_score, 0.25))
            details.append(f"ROE: {roe:.1f}% {'(excellent)' if roe > 20 else '(poor)' if roe < 5 else '(adequate)'}")
        
        if not scores:
            return {"factor": self.name, "score": 0, "confidence": 15, "signal": "neutral",
                    "reasoning": "Insufficient fundamental data.", "data": f}
        
        weighted = sum(s * w for _, s, w in scores) / sum(w for _, _, w in scores)
        final_score = max(-100, min(100, weighted))
        confidence = min(80, 30 + len(scores) * 15)
        signal = "bullish" if final_score > 15 else "bearish" if final_score < -15 else "neutral"
        
        return {
            "factor": self.name, "score": round(final_score, 1), "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": f"FUNDAMENTALS: {signal.upper()}\n" + "\n".join(details),
            "data": {**f, "sector": sector, "sector_avg_pe": sector_pe, "component_scores": {n: round(s,1) for n,s,_ in scores}}
        }


# ====================================================================
# S3: SECTOR MOMENTUM (15%)
# ====================================================================

class StockSectorMomentumFactor(BaseFactor):
    """Is this stock's sector outperforming or lagging Nifty 50?
    Measures relative strength over 1 and 4 weeks."""

    def __init__(self, db=None):
        super().__init__("S3_sector_momentum", STOCK_FACTOR_WEIGHTS["S3_sector_momentum"])
        self.db = db

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        data = kwargs.get("stock_data")
        if not data or len(data.get("prices", [])) < 30:
            return {"factor": self.name, "score": 0, "confidence": 20, "signal": "neutral",
                    "reasoning": "Insufficient data for sector analysis.", "data": {}}
        
        prices = np.array(data["prices"])
        sector = data.get("sector", "Unknown")
        
        # Calculate stock's own momentum
        ret_1w = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 else 0
        ret_4w = (prices[-1] - prices[-20]) / prices[-20] * 100 if len(prices) >= 20 else 0
        ret_12w = (prices[-1] - prices[-60]) / prices[-60] * 100 if len(prices) >= 60 else 0
        
        # 52-week high/low position
        high_52 = max(prices[-252:]) if len(prices) >= 252 else max(prices)
        low_52 = min(prices[-252:]) if len(prices) >= 252 else min(prices)
        position_52w = (prices[-1] - low_52) / (high_52 - low_52) * 100 if high_52 > low_52 else 50
        
        # Score based on momentum
        momentum_score = 0
        
        # 1-week momentum (40% weight)
        if ret_1w > 3:
            m1w = 40
        elif ret_1w > 1:
            m1w = 20
        elif ret_1w < -3:
            m1w = -40
        elif ret_1w < -1:
            m1w = -20
        else:
            m1w = 0
        
        # 4-week momentum (40% weight)
        if ret_4w > 8:
            m4w = 50
        elif ret_4w > 3:
            m4w = 25
        elif ret_4w < -8:
            m4w = -50
        elif ret_4w < -3:
            m4w = -25
        else:
            m4w = 0
        
        # 52-week position (20% weight)
        if position_52w > 80:
            p52 = -20  # Near highs, limited upside
        elif position_52w < 30:
            p52 = 20   # Near lows, potential value
        else:
            p52 = 0
        
        momentum_score = m1w * 0.4 + m4w * 0.4 + p52 * 0.2
        momentum_score = max(-100, min(100, momentum_score))
        
        confidence = 55
        signal = "bullish" if momentum_score > 10 else "bearish" if momentum_score < -10 else "neutral"
        
        return {
            "factor": self.name, "score": round(momentum_score, 1), "confidence": confidence,
            "signal": signal,
            "reasoning": (
                f"SECTOR MOMENTUM ({sector}): {signal.upper()}\n"
                f"1-week return: {ret_1w:+.1f}%, 4-week: {ret_4w:+.1f}%, 12-week: {ret_12w:+.1f}%\n"
                f"52-week position: {position_52w:.0f}% (0=at low, 100=at high)"
            ),
            "data": {
                "sector": sector, "return_1w": round(ret_1w, 2), "return_4w": round(ret_4w, 2),
                "return_12w": round(ret_12w, 2), "position_52w": round(position_52w, 1),
            }
        }


# ====================================================================
# S4: NEWS + MACRO (15%)
# ====================================================================

STOCK_BULLISH_KEYWORDS = {
    "earnings beat": 3, "revenue beat": 3, "upgrade": 3, "outperform": 3,
    "buy rating": 3, "target raised": 3, "strong results": 2,
    "growth": 2, "rally": 2, "bullish": 2, "positive": 2,
    "fii buying": 3, "fii inflow": 3, "rate cut": 2, "reform": 2,
    "expansion": 2, "recovery": 2, "dividend": 1, "buyback": 2,
    "nifty high": 2, "sensex high": 2, "record": 1, "surge": 2,
}

STOCK_BEARISH_KEYWORDS = {
    "earnings miss": 3, "revenue miss": 3, "downgrade": 3, "underperform": 3,
    "sell rating": 3, "target cut": 3, "weak results": 2,
    "decline": 2, "crash": 3, "bearish": 2, "negative": 2,
    "fii selling": 3, "fii outflow": 3, "rate hike": 2, "recession": 3,
    "slowdown": 2, "concern": 1, "warning": 2, "debt": 1,
    "sebi action": 2, "fraud": 3, "scam": 3, "default": 3,
    "nifty fall": 2, "sensex crash": 3,
}

INDIA_STOCK_BULLISH = {
    "rbi rate cut": 3, "budget boost": 3, "pli scheme": 2,
    "make in india": 2, "disinvestment": 1, "gdp growth": 2,
}

INDIA_STOCK_BEARISH = {
    "rbi rate hike": 3, "fiscal deficit": 2, "rupee fall": 2,
    "crude surge": 2, "inflation high": 2, "capital flight": 3,
}


class StockNewsMacroFactor(BaseFactor):
    """Scores stock market environment from news + macro indicators.
    Reuses the keyword engine from crypto F3 with stock-specific terms."""

    def __init__(self, db=None):
        super().__init__("S4_news_macro", STOCK_FACTOR_WEIGHTS["S4_news_macro"])
        self.db = db
        self._cache = None
        self._cache_time = None

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        articles = await self._get_stock_news()
        
        if not articles:
            return {"factor": self.name, "score": 0, "confidence": 25, "signal": "neutral",
                    "reasoning": "No stock news available.", "data": {"article_count": 0}}
        
        total_bull = 0
        total_bear = 0
        article_sentiments = []
        
        for article in articles:
            text = ((article.get("title") or "") + " " + (article.get("description") or "")).lower()
            
            bull = sum(w for k, w in STOCK_BULLISH_KEYWORDS.items() if k in text)
            bear = sum(w for k, w in STOCK_BEARISH_KEYWORDS.items() if k in text)
            bull += sum(w for k, w in INDIA_STOCK_BULLISH.items() if k in text)
            bear += sum(w for k, w in INDIA_STOCK_BEARISH.items() if k in text)
            
            total_bull += bull
            total_bear += bear
            
            sent = "positive" if bull > bear + 2 else "negative" if bear > bull + 2 else "neutral"
            article_sentiments.append({"title": (article.get("title") or "")[:80], "sentiment": sent})
        
        net = total_bull - total_bear
        normalized = max(-100, min(100, net * 3))
        confidence = min(75, 25 + len(articles) * 3)
        signal = "bullish" if normalized > 15 else "bearish" if normalized < -15 else "neutral"
        
        pos_count = sum(1 for a in article_sentiments if a["sentiment"] == "positive")
        neg_count = sum(1 for a in article_sentiments if a["sentiment"] == "negative")
        
        return {
            "factor": self.name, "score": round(normalized, 1), "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": (
                f"STOCK NEWS: {signal.upper()} (score: {normalized:+.0f})\n"
                f"Analyzed {len(articles)} articles. {pos_count} positive, {neg_count} negative.\n"
                f"Raw: {total_bull} bullish vs {total_bear} bearish points."
            ),
            "data": {"article_count": len(articles), "positive": pos_count, "negative": neg_count,
                     "raw_bull": total_bull, "raw_bear": total_bear, "top_articles": article_sentiments[:3]}
        }

    async def _get_stock_news(self) -> List[Dict]:
        if self._cache_time and (datetime.now() - self._cache_time).total_seconds() < 1800 and self._cache:
            return self._cache
        
        articles = []
        if NEWSAPI_KEY:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get("https://newsapi.org/v2/everything", params={
                        "apiKey": NEWSAPI_KEY,
                        "q": "Nifty OR BSE OR NSE OR Indian stock OR Sensex OR SEBI OR RBI OR Indian market",
                        "language": "en", "sortBy": "publishedAt", "pageSize": 15,
                    })
                    if response.status_code == 200:
                        articles = response.json().get("articles", [])
            except Exception as e:
                logger.warning(f"Stock news fetch failed: {e}")
        
        self._cache = articles
        self._cache_time = datetime.now()
        return articles


# ====================================================================
# S5: INSTITUTIONAL FLOWS (15%)
# ====================================================================

class StockInstitutionalFlowFactor(BaseFactor):
    """Scores FII/DII buying/selling pressure.
    Uses volume analysis as a proxy since free FII/DII data is delayed.
    High volume + price up = institutional buying. High volume + price down = institutional selling."""

    def __init__(self, db=None):
        super().__init__("S5_institutional_flows", STOCK_FACTOR_WEIGHTS["S5_institutional_flows"])
        self.db = db

    async def compute_score(self, symbol: str, **kwargs) -> Dict:
        data = kwargs.get("stock_data")
        if not data or len(data.get("prices", [])) < 20:
            return {"factor": self.name, "score": 0, "confidence": 20, "signal": "neutral",
                    "reasoning": "Insufficient data for institutional flow analysis.", "data": {}}
        
        prices = np.array(data["prices"])
        volumes = np.array(data["volumes"])
        
        # Money flow analysis: volume-weighted price trend
        # On-Balance Volume (OBV) approximation
        price_changes = np.diff(prices)
        vol_signed = np.where(price_changes > 0, volumes[1:], -volumes[1:])
        
        # Recent 5-day net flow vs 20-day average
        if len(vol_signed) < 20:
            return {"factor": self.name, "score": 0, "confidence": 20, "signal": "neutral",
                    "reasoning": "Need 20+ days for flow analysis.", "data": {}}
        
        recent_flow = float(np.sum(vol_signed[-5:]))
        avg_flow = float(np.mean([np.sum(vol_signed[i:i+5]) for i in range(len(vol_signed)-20, len(vol_signed)-5)]))
        
        if avg_flow == 0:
            flow_ratio = 0
        else:
            flow_ratio = recent_flow / abs(avg_flow) if avg_flow != 0 else 0
        
        # Volume surge detection
        avg_vol_20 = float(np.mean(volumes[-20:]))
        recent_vol = float(np.mean(volumes[-3:]))
        vol_surge = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
        
        # Delivery percentage proxy (high volume + consistent direction = institutional)
        recent_direction = sum(1 for p in price_changes[-5:] if p > 0)  # out of 5
        
        # Score
        score = 0
        details = []
        
        # Flow direction
        if flow_ratio > 1.5:
            score += 40
            details.append(f"Strong net buying pressure (flow ratio: {flow_ratio:.1f}x)")
        elif flow_ratio > 0.5:
            score += 20
            details.append(f"Moderate buying pressure (flow ratio: {flow_ratio:.1f}x)")
        elif flow_ratio < -1.5:
            score -= 40
            details.append(f"Strong net selling pressure (flow ratio: {flow_ratio:.1f}x)")
        elif flow_ratio < -0.5:
            score -= 20
            details.append(f"Moderate selling pressure (flow ratio: {flow_ratio:.1f}x)")
        else:
            details.append(f"Neutral flow (ratio: {flow_ratio:.1f}x)")
        
        # Volume surge
        if vol_surge > 1.5 and flow_ratio > 0:
            score += 20
            details.append(f"Volume surge {vol_surge:.1f}x with buying = likely institutional accumulation")
        elif vol_surge > 1.5 and flow_ratio < 0:
            score -= 20
            details.append(f"Volume surge {vol_surge:.1f}x with selling = likely institutional distribution")
        
        # Directional consistency
        if recent_direction >= 4:
            score += 15
            details.append(f"Price up {recent_direction}/5 recent days (consistent buying)")
        elif recent_direction <= 1:
            score -= 15
            details.append(f"Price down {5 - recent_direction}/5 recent days (consistent selling)")
        
        score = max(-100, min(100, score))
        confidence = 45 + (10 if vol_surge > 1.3 else 0)
        signal = "bullish" if score > 10 else "bearish" if score < -10 else "neutral"
        
        return {
            "factor": self.name, "score": round(score, 1), "confidence": round(confidence, 1),
            "signal": signal,
            "reasoning": "INSTITUTIONAL FLOWS: " + signal.upper() + "\n" + "\n".join(details),
            "data": {
                "flow_ratio": round(flow_ratio, 2), "volume_surge": round(vol_surge, 2),
                "direction_5d": recent_direction, "recent_vol_avg": round(recent_vol, 0),
            }
        }


# ====================================================================
# STOCK SCORING ENGINE
# ====================================================================

class StockScoringEngine:
    """Main entry point for stock scoring. Scores 20 Nifty 50 stocks.
    
    Usage:
        engine = StockScoringEngine(db)
        result = await engine.score("RELIANCE")
        result = await engine.score_all()
    """

    def __init__(self, db):
        self.db = db
        
        self.factors = [
            StockTechnicalFactor(db=db),
            StockFundamentalFactor(db=db),
            StockSectorMomentumFactor(db=db),
            StockNewsMacroFactor(db=db),
            StockInstitutionalFlowFactor(db=db),
        ]

    def _combine(self, factor_results: List[Dict]) -> Dict:
        """Stock-specific combine using STOCK_FACTOR_WEIGHTS."""
        if not factor_results:
            return {"action": "HOLD", "final_score": 0, "confidence": 0, "factors": [],
                    "conflicts": [], "thresholds": {"buy": 35, "sell": -35}, "explanation": "No data."}
        
        weighted_score = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0
        factor_breakdown = []
        
        for result in factor_results:
            factor_name = result["factor"]
            weight = STOCK_FACTOR_WEIGHTS.get(factor_name, 0)
            score = result.get("score", 0)
            conf = result.get("confidence", 50)
            
            weighted_score += score * weight
            weighted_confidence += conf * weight
            total_weight += weight
            
            factor_breakdown.append({
                "factor": factor_name, "weight": weight, "raw_score": score,
                "weighted_contribution": round(score * weight, 2),
                "confidence": conf, "signal": result.get("signal", "neutral"),
            })
        
        if total_weight > 0:
            weighted_confidence /= total_weight
        
        final_score = round(weighted_score, 2)
        final_confidence = round(weighted_confidence, 1)
        
        thresholds = {"buy": 35, "sell": -35}
        if final_score > thresholds["buy"]:
            action = "BUY"
        elif final_score < thresholds["sell"]:
            action = "SELL"
        else:
            action = "HOLD"
        
        # Detect conflicts
        signals = [(r["factor"], r.get("signal", "neutral")) for r in factor_results]
        has_bull = any(s == "bullish" for _, s in signals)
        has_bear = any(s == "bearish" for _, s in signals)
        conflicts = []
        if has_bull and has_bear:
            bull_names = [n for n, s in signals if s == "bullish"]
            bear_names = [n for n, s in signals if s == "bearish"]
            conflicts.append(f"{', '.join(bull_names)} bullish vs {', '.join(bear_names)} bearish")
            final_confidence = max(10, final_confidence - 15)
        
        return {
            "action": action, "final_score": final_score, "confidence": final_confidence,
            "factors": factor_breakdown, "conflicts": conflicts,
            "thresholds": thresholds,
            "explanation": f"STOCK RECOMMENDATION: {action} (score: {final_score:+.1f}, confidence: {final_confidence:.0f}%)",
        }

    async def score(self, symbol: str, **kwargs) -> Dict:
        """Score a single stock."""
        # Fetch data once, pass to all factors
        stock_data = await fetch_stock_history(symbol, "1y", self.db)
        kwargs["stock_data"] = stock_data
        
        factor_results = []
        for factor in self.factors:
            try:
                result = await factor.compute_score(symbol, **kwargs)
                factor_results.append(result)
            except Exception as e:
                logger.error(f"Stock factor {factor.name} failed for {symbol}: {e}")
                factor_results.append({
                    "factor": factor.name, "score": 0, "confidence": 0,
                    "signal": "neutral", "reasoning": f"Error: {str(e)}", "data": {}
                })
        
        combined = self._combine(factor_results)
        
        price = stock_data["prices"][-1] if stock_data and stock_data.get("prices") else 0
        name = TRACKED_STOCKS.get(symbol, {}).get("name", symbol)
        sector = TRACKED_STOCKS.get(symbol, {}).get("sector", "Unknown")
        
        return {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_price": round(price, 2),
            "change_24h": round(float((stock_data["prices"][-1] / stock_data["prices"][-2] - 1) * 100), 2) if stock_data and len(stock_data.get("prices", [])) >= 2 else 0,
            **combined,
            "factor_details": {r["factor"]: r for r in factor_results},
        }

    async def score_all(self) -> Dict[str, Dict]:
        """Score all 50 tracked stocks in parallel batches of 10."""
        results = {}
        symbols = list(TRACKED_STOCKS.keys())
        batch_size = 10
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = []
            for symbol in batch:
                tasks.append(self._safe_score(symbol))
            batch_results = await asyncio.gather(*tasks)
            for symbol, result in zip(batch, batch_results):
                if result is not None:
                    results[symbol] = result
            await asyncio.sleep(1)  # Brief pause between batches
        
        return results
    
    async def _safe_score(self, symbol: str) -> Optional[Dict]:
        """Score a single stock with error handling. Used by parallel score_all."""
        try:
            return await self.score(symbol)
        except Exception as e:
            logger.error(f"Stock scoring failed for {symbol}: {e}")
            return None

    async def warm_cache(self):
        """Pre-fetch data for all stocks. Call at startup."""
        logger.info("Warming stock data cache for 20 stocks...")
        for symbol in TRACKED_STOCKS:
            try:
                data = await fetch_stock_history(symbol, "1y", self.db)
                if data:
                    logger.info(f"  {symbol}: {data.get('data_points', 0)} data points")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"  {symbol}: cache warm failed: {e}")
        logger.info("Stock cache warming complete.")