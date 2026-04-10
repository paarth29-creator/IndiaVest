"""
IndiaVest Trade Plan Generator
===============================
The "steering wheel" for the scoring engine.

Converts raw 4-factor scores into a clear, actionable trade plan:
  1. YES / NO / WAIT verdict
  2. Which coins to trade (top 3-5 by score)
  3. How much to put in each (budget-aware)
  4. Exact entry, stop-loss, take-profit prices (ATR-based)
  5. Expected profit/loss after 30% VDA tax
  6. Step-by-step exit instructions

Usage:
    generator = TradePlanGenerator(scoring_engine, crypto_service)
    plan = await generator.generate(budget=25000, risk_profile="moderate")
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Confidence thresholds per risk profile
CONFIDENCE_THRESHOLDS = {
    "conservative": {"buy": 55, "sell": -55, "label": "Conservative", "desc": "Fewer signals, higher conviction. Only trades when most factors strongly agree."},
    "moderate":     {"buy": 40, "sell": -40, "label": "Moderate",     "desc": "Balanced approach. Default setting. Trades when factors show reasonable agreement."},
    "aggressive":   {"buy": 5, "sell": -25, "label": "Aggressive",   "desc": "More frequent signals, lower conviction threshold. Higher risk of false signals."},
}

# Position sizing rules
MAX_POSITIONS = 5
MIN_POSITIONS = 1
MIN_POSITION_INR = 500         # Don't split below Rs 500 per coin
MAX_SINGLE_POSITION_PCT = 0.40 # No more than 40% in one coin
MIN_BUDGET = 1000              # Minimum Rs 1,000 to generate a plan

# Allocation tiers based on score ranking
ALLOCATION_TIERS = {
    1: [1.0],                           # 1 coin: 100%
    2: [0.60, 0.40],                    # 2 coins: 60/40
    3: [0.45, 0.30, 0.25],             # 3 coins: 45/30/25
    4: [0.35, 0.25, 0.22, 0.18],       # 4 coins: 35/25/22/18
    5: [0.30, 0.25, 0.20, 0.15, 0.10], # 5 coins: 30/25/20/15/10
}

# Indian VDA tax
VDA_TAX_RATE = 0.30
VDA_TDS_RATE = 0.01


class TradePlanGenerator:
    def __init__(self, scoring_engine, crypto_service):
        self.engine = scoring_engine
        self.crypto = crypto_service

    async def generate(
        self,
        budget: float,
        risk_profile: str = "moderate",
        max_coins: int = 5,
    ) -> Dict:
        """Generate a complete trade plan.
        
        Args:
            budget: Amount in INR the user wants to deploy
            risk_profile: "conservative", "moderate", or "aggressive"
            max_coins: Maximum number of coins in the plan (1-5)
        
        Returns:
            Complete trade plan with verdict, positions, and exit instructions
        """
        if budget < MIN_BUDGET:
            return self._no_trade_plan(
                "WAIT",
                f"Budget of Rs {budget:,.0f} is below the minimum Rs {MIN_BUDGET:,.0f}. "
                f"With amounts this small, transaction fees and 1% TDS will eat most gains. "
                f"Consider saving up to at least Rs 2,000 before trading.",
                budget, risk_profile
            )

        thresholds = CONFIDENCE_THRESHOLDS.get(risk_profile, CONFIDENCE_THRESHOLDS["moderate"])
        max_coins = max(MIN_POSITIONS, min(MAX_POSITIONS, max_coins))

        # Step 1: Get market prices (top coins by market cap)
        crypto_prices = {}
        try:
            crypto_prices = await self.crypto.get_prices() or {}
        except Exception as e:
            logger.warning(f"get_prices failed: {e}")

        # Step 2: Score ALL 20 curated coins (not just what get_prices returns)
        from scoring_engine import SYMBOL_TO_COINGECKO
        from data_preloader import DataPreloader

        scored_coins = []
        for symbol, coin_id in SYMBOL_TO_COINGECKO.items():
            try:
                # Get price: prefer live data from get_prices, fall back to cached data
                price_data = crypto_prices.get(symbol, {})
                price_inr = price_data.get("price_inr", 0)
                
                # If this coin isn't in the top 20 market cap list, get price from cache
                if not price_inr and self.engine.db is not None:
                    try:
                        cached = await self.engine.db["market_data_cache"].find_one({"coin_id": coin_id})
                        if cached and cached.get("prices"):
                            price_inr = cached["prices"][-1]  # Most recent cached price
                    except Exception:
                        pass

                if not price_inr:
                    continue  # Can't trade without a price

                score_result = await self.engine.score(
                    symbol,
                    volume_24h=price_data.get("volume_24h", 0),
                    volume_avg=price_data.get("volume_24h", 0) * 0.8 if price_data.get("volume_24h") else 0,
                )
                scored_coins.append({
                    "symbol": symbol,
                    "name": price_data.get("name", symbol),
                    "score": score_result["final_score"],
                    "action": score_result["action"],
                    "confidence": score_result["confidence"],
                    "factors": score_result.get("factors", []),
                    "factor_details": score_result.get("factor_details", {}),
                    "price_inr": price_inr,
                    "change_24h": price_data.get("change_24h", 0),
                    "volume_24h": price_data.get("volume_24h", 0),
                    "high_24h": price_data.get("high_24h", 0),
                    "low_24h": price_data.get("low_24h", 0),
                })
            except Exception as e:
                logger.warning(f"Scoring failed for {symbol}: {e}")
                continue

        if not scored_coins:
            return self._no_trade_plan(
                "WAIT", "Scoring engine returned no results. Try again shortly.",
                budget, risk_profile
            )

        # Step 3: Rank by score, filter by threshold
        scored_coins.sort(key=lambda x: x["score"], reverse=True)
        buy_candidates = [c for c in scored_coins if c["score"] >= thresholds["buy"]]
        sell_candidates = [c for c in scored_coins if c["score"] <= thresholds["sell"]]

        # Step 4: Determine verdict
        avg_score = np.mean([c["score"] for c in scored_coins[:5]])
        buy_count = len(buy_candidates)
        sell_count = len(sell_candidates)

        # Compute 7-day verdict history placeholder (will be populated from DB)
        today_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

        if buy_count == 0 and sell_count == 0:
            # WAIT: no coins cross the threshold
            verdict = "WAIT"
            verdict_reason = self._build_wait_reason(scored_coins[:3], thresholds, avg_score)
            return self._no_trade_plan(verdict, verdict_reason, budget, risk_profile, 
                                       market_summary=self._market_summary(scored_coins, crypto_prices))
        
        if sell_count > buy_count and sell_count >= 2:
            # Overall bearish: suggest not trading
            verdict = "NO"
            verdict_reason = (
                f"{sell_count} out of {len(scored_coins[:20])} analyzed coins show sell signals. "
                f"Market conditions are unfavorable. Protect your capital today."
            )
            return self._no_trade_plan(verdict, verdict_reason, budget, risk_profile,
                                       market_summary=self._market_summary(scored_coins, crypto_prices))

        # YES: we have buy candidates
        verdict = "YES"
        
        # Step 5: Pick top coins (up to max_coins)
        selected = buy_candidates[:max_coins]
        
        # If budget is too small for multiple coins, reduce
        while len(selected) > 1 and budget / len(selected) < MIN_POSITION_INR:
            selected = selected[:-1]

        # Step 6: Allocate budget
        allocations = ALLOCATION_TIERS.get(len(selected), ALLOCATION_TIERS[MAX_POSITIONS])[:len(selected)]
        
        # Step 7: Build position details with ATR-based exits
        positions = []
        total_best_case = 0
        total_expected = 0
        total_worst_case = 0

        for i, coin in enumerate(selected):
            alloc_pct = allocations[i]
            position_inr = round(budget * alloc_pct, 0)
            
            price = coin["price_inr"]
            if price <= 0:
                continue
            
            quantity = position_inr / price

            # ATR-based exits
            f1_data = coin.get("factor_details", {}).get("F1_technical_regime", {}).get("data", {})
            f2_data = coin.get("factor_details", {}).get("F2_volatility_filter", {}).get("data", {})
            
            atr_pct = f2_data.get("atr_pct", 2.5)  # Default 2.5% if not available
            bollinger_bw = f2_data.get("bollinger_bandwidth", 10.0)
            
            # Stop loss: 1.5x ATR below entry (or minimum 2%)
            sl_pct = max(2.0, atr_pct * 1.5)
            stop_loss = price * (1 - sl_pct / 100)
            
            # Take profit 1: 1x ATR above entry (1:1 risk/reward)
            tp1_pct = atr_pct
            tp1 = price * (1 + tp1_pct / 100)
            
            # Take profit 2: 2x ATR above entry (1:2 risk/reward)  
            tp2_pct = atr_pct * 2
            tp2 = price * (1 + tp2_pct / 100)
            
            # Take profit 3: 3x ATR or upper Bollinger, whichever is closer
            tp3_pct = min(atr_pct * 3, bollinger_bw / 2)
            tp3 = price * (1 + tp3_pct / 100)

            # Expected outcomes
            loss_if_sl = position_inr * (sl_pct / 100)
            gain_at_tp1 = position_inr * (tp1_pct / 100)
            gain_at_tp2 = position_inr * (tp2_pct / 100)
            gain_at_tp3 = position_inr * (tp3_pct / 100)

            # After 30% VDA tax (only on gains, losses don't offset)
            gain_at_tp1_after_tax = gain_at_tp1 * (1 - VDA_TAX_RATE)
            gain_at_tp2_after_tax = gain_at_tp2 * (1 - VDA_TAX_RATE)

            # Win probability from backtest
            backtest = f1_data.get("backtest", {})
            win_rate = backtest.get("win_rate_7d", 50)
            
            # Expected value: (win_rate * avg_gain) - ((1-win_rate) * avg_loss)
            expected_gain = (win_rate / 100) * gain_at_tp1_after_tax
            expected_loss = ((100 - win_rate) / 100) * loss_if_sl
            expected_value = expected_gain - expected_loss

            total_best_case += gain_at_tp2_after_tax
            total_expected += expected_value
            total_worst_case -= loss_if_sl

            # Build exit instructions
            exit_steps = [
                {
                    "step": 1,
                    "condition": f"Price reaches Rs {tp1:,.0f} (+{tp1_pct:.1f}%)",
                    "action": "Sell 50% of your position",
                    "detail": f"Sell {quantity * 0.5:.6f} {coin['symbol']}. Lock in Rs {gain_at_tp1_after_tax * 0.5:,.0f} profit after tax. Move stop loss to your entry price (Rs {price:,.0f}) for the remaining 50%. This way you cannot lose money on this trade anymore.",
                },
                {
                    "step": 2,
                    "condition": f"Price reaches Rs {tp2:,.0f} (+{tp2_pct:.1f}%)",
                    "action": "Sell another 30%",
                    "detail": f"Sell {quantity * 0.3:.6f} {coin['symbol']}. Total locked profit now Rs {gain_at_tp1_after_tax * 0.5 + gain_at_tp2_after_tax * 0.3:,.0f} after tax. Let the remaining 20% ride with stop loss at TP1 price.",
                },
                {
                    "step": 3,
                    "condition": f"Price reaches Rs {tp3:,.0f} (+{tp3_pct:.1f}%) OR 4 hours pass",
                    "action": "Sell remaining 20%",
                    "detail": f"Close the entire position. Whether it hit TP3 or time ran out, exit completely. Do not hold overnight unless the app specifically says to.",
                },
                {
                    "step": "STOP LOSS",
                    "condition": f"Price drops to Rs {stop_loss:,.0f} (-{sl_pct:.1f}%)",
                    "action": "Sell 100% immediately",
                    "detail": f"Maximum loss: Rs {loss_if_sl:,.0f}. Do NOT wait for recovery. Do NOT average down. The stop loss exists to protect you. Accept the loss and wait for the next signal.",
                },
            ]

            positions.append({
                "rank": i + 1,
                "symbol": coin["symbol"],
                "name": coin["name"],
                "score": round(coin["score"], 1),
                "confidence": round(coin["confidence"], 1),
                "allocation_pct": round(alloc_pct * 100, 0),
                "amount_inr": round(position_inr, 0),
                "current_price": round(price, 2),
                "change_24h": round(coin["change_24h"], 2),
                "quantity": round(quantity, 6),
                "entry": {
                    "price": round(price, 2),
                    "range_low": round(price * 0.995, 2),
                    "range_high": round(price * 1.005, 2),
                    "instruction": f"Buy at current market price (Rs {price:,.0f}). Acceptable range: Rs {price * 0.995:,.0f} to Rs {price * 1.005:,.0f}. If price moves outside this range, wait for it to return or skip this coin.",
                },
                "stop_loss": {
                    "price": round(stop_loss, 2),
                    "pct": round(sl_pct, 1),
                    "loss_inr": round(loss_if_sl, 0),
                    "based_on": f"1.5x ATR ({atr_pct:.1f}% daily volatility)",
                },
                "take_profit": {
                    "tp1": {"price": round(tp1, 2), "pct": round(tp1_pct, 1), "action": "Sell 50%", "gross_gain": round(gain_at_tp1, 0), "after_tax": round(gain_at_tp1_after_tax, 0)},
                    "tp2": {"price": round(tp2, 2), "pct": round(tp2_pct, 1), "action": "Sell 30%", "gross_gain": round(gain_at_tp2, 0), "after_tax": round(gain_at_tp2_after_tax, 0)},
                    "tp3": {"price": round(tp3, 2), "pct": round(tp3_pct, 1), "action": "Sell remaining 20%", "gross_gain": round(gain_at_tp3, 0)},
                },
                "expected_outcome": {
                    "best_case_inr": round(gain_at_tp2_after_tax, 0),
                    "expected_inr": round(expected_value, 0),
                    "worst_case_inr": round(-loss_if_sl, 0),
                    "win_probability": round(win_rate, 0),
                    "note": f"Based on {backtest.get('sample_count', 0)} historical samples of this technical regime.",
                },
                "exit_instructions": exit_steps,
                "reasoning_summary": self._coin_reasoning(coin),
            })

        # Step 8: Build overall summary
        verdict_reason = self._build_yes_reason(selected, thresholds, avg_score, budget)

        return {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "date": today_ist.strftime("%Y-%m-%d"),
            "time_ist": today_ist.strftime("%H:%M IST"),
            "budget": round(budget, 0),
            "risk_profile": risk_profile,
            "risk_profile_detail": thresholds,
            "summary": {
                "total_deployed": round(sum(p["amount_inr"] for p in positions), 0),
                "deployment_pct": round(sum(p["amount_inr"] for p in positions) / budget * 100, 0),
                "positions_count": len(positions),
                "best_case_total": round(total_best_case, 0),
                "expected_total": round(total_expected, 0),
                "worst_case_total": round(total_worst_case, 0),
                "best_case_after_tax": round(total_best_case, 0),
                "worst_case_note": f"Maximum loss if ALL stop-losses hit: Rs {abs(total_worst_case):,.0f} ({abs(total_worst_case)/budget*100:.1f}% of budget)",
                "tax_note": f"All profit figures are AFTER 30% VDA tax. Losses cannot be offset. 1% TDS applies on each transaction above Rs 10,000.",
            },
            "positions": positions,
            "market_summary": self._market_summary(scored_coins, crypto_prices),
            "all_scores": [
                {"symbol": c["symbol"], "name": c["name"], "score": round(c["score"], 1), 
                 "action": c["action"], "change_24h": round(c["change_24h"], 2)}
                for c in scored_coins[:20]
            ],
            "disclaimer": "This is NOT financial advice. Past performance does not guarantee future results. High risk of capital loss. Virtual/educational use only. Crypto taxed at 30% (VDA) + 1% TDS in India.",
        }

    def _no_trade_plan(self, verdict, reason, budget, risk_profile, market_summary=None):
        today_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        thresholds = CONFIDENCE_THRESHOLDS.get(risk_profile, CONFIDENCE_THRESHOLDS["moderate"])
        
        alternatives = []
        if verdict == "NO":
            alternatives = [
                {"action": "Hold cash", "detail": f"Keep your Rs {budget:,.0f} safe. Missing one day costs nothing. Losing money costs everything."},
                {"action": "Learn", "detail": "Use the app's glossary and news section to understand what's happening in the market today."},
                {"action": "Review portfolio", "detail": "Check your existing holdings. Tighten stop-losses if the market is turning bearish."},
            ]
        elif verdict == "WAIT":
            alternatives = [
                {"action": "Check back in 4 hours", "detail": "Market conditions may change. The app updates every few minutes."},
                {"action": "Paper trade", "detail": "If you want to practice, note what you WOULD have traded and check the result tomorrow."},
            ]

        return {
            "verdict": verdict,
            "verdict_reason": reason,
            "date": today_ist.strftime("%Y-%m-%d"),
            "time_ist": today_ist.strftime("%H:%M IST"),
            "budget": round(budget, 0),
            "risk_profile": risk_profile,
            "risk_profile_detail": thresholds,
            "summary": {
                "total_deployed": 0,
                "deployment_pct": 0,
                "positions_count": 0,
                "best_case_total": 0,
                "expected_total": 0,
                "worst_case_total": 0,
            },
            "positions": [],
            "alternatives": alternatives,
            "market_summary": market_summary,
            "disclaimer": "This is NOT financial advice. Past performance does not guarantee future results. High risk of capital loss. Virtual/educational use only. Crypto taxed at 30% (VDA) + 1% TDS in India.",
        }

    def _build_yes_reason(self, selected, thresholds, avg_score, budget):
        coins_str = ", ".join([f"{c['symbol']} ({c['score']:+.0f})" for c in selected])
        return (
            f"{len(selected)} coin(s) passed the {thresholds['label'].lower()} threshold (score above +{thresholds['buy']}): {coins_str}. "
            f"The 4-factor analysis shows favorable conditions across technical patterns, volatility, news sentiment, and whale behavior. "
            f"Your Rs {budget:,.0f} budget has been split across {len(selected)} positions with ATR-based stop losses to limit risk."
        )

    def _build_wait_reason(self, top_coins, thresholds, avg_score):
        best = top_coins[0] if top_coins else None
        if best:
            gap = thresholds["buy"] - best["score"]
            return (
                f"No coin reached the {thresholds['label'].lower()} buy threshold of +{thresholds['buy']}. "
                f"Best candidate: {best['symbol']} at +{best['score']:.1f} (needs +{gap:.1f} more). "
                f"Average market score: {avg_score:+.1f}. "
                f"Conditions are not clearly favorable. Waiting protects your capital."
            )
        return "Unable to analyze market conditions. Please try again."

    def _coin_reasoning(self, coin):
        f1 = coin.get("factor_details", {}).get("F1_technical_regime", {})
        f4 = coin.get("factor_details", {}).get("F4_onchain_flows", {})
        
        f1_signal = f1.get("signal", "neutral")
        f4_signal = f4.get("signal", "neutral")
        f1_score = f1.get("score", 0)
        f4_score = f4.get("score", 0)
        
        parts = [f"{coin['symbol']} scored +{coin['score']:.1f} across all 4 factors."]
        
        if f1_signal == "bullish":
            parts.append(f"Technical patterns are bullish (score: {f1_score:+.0f}). Historical data supports upward movement from this regime.")
        elif f1_signal == "neutral":
            parts.append(f"Technical patterns are neutral (score: {f1_score:+.0f}). No strong directional signal from indicators alone.")
        
        if f4_signal == "bullish":
            parts.append(f"On-chain data is bullish (score: {f4_score:+.0f}). Whale behavior suggests accumulation.")
        
        return " ".join(parts)

    def _market_summary(self, scored_coins, crypto_prices):
        btc = crypto_prices.get("BTC", {})
        eth = crypto_prices.get("ETH", {})
        
        bullish_count = sum(1 for c in scored_coins[:20] if c["score"] > 20)
        bearish_count = sum(1 for c in scored_coins[:20] if c["score"] < -20)
        
        if bullish_count > bearish_count + 2:
            mood = "Bullish"
            mood_detail = f"{bullish_count} out of top 10 coins show positive signals."
        elif bearish_count > bullish_count + 2:
            mood = "Bearish"
            mood_detail = f"{bearish_count} out of top 10 coins show negative signals."
        else:
            mood = "Mixed"
            mood_detail = f"No clear direction. {bullish_count} bullish, {bearish_count} bearish signals."

        return {
            "mood": mood,
            "mood_detail": mood_detail,
            "btc_price": btc.get("price_inr", 0),
            "btc_change": btc.get("change_24h", 0),
            "eth_price": eth.get("price_inr", 0),
            "eth_change": eth.get("change_24h", 0),
        }