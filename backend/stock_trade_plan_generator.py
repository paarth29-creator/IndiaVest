"""
IndiaVest Stock Trade Plan Generator
=====================================
Converts 5-factor stock scores into actionable trade plans.
Same architecture as crypto TradePlanGenerator but with:
  - NSE market hours awareness
  - Stock-specific tax (15% STCG vs 30% VDA)
  - Tighter stop losses (stocks move less than crypto)
  - Fundamental data in reasoning
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

from stock_scoring_engine import (
    StockScoringEngine, TRACKED_STOCKS, STOCK_THRESHOLDS, STOCK_STCG_RATE,
    is_market_open, is_trading_window, get_market_status, get_ist_now,
)

logger = logging.getLogger(__name__)

MAX_POSITIONS = 5
MIN_POSITION_INR = 500
MIN_BUDGET = 1000

ALLOCATION_TIERS = {
    1: [1.0],
    2: [0.60, 0.40],
    3: [0.45, 0.30, 0.25],
    4: [0.35, 0.25, 0.22, 0.18],
    5: [0.30, 0.25, 0.20, 0.15, 0.10],
}


class StockTradePlanGenerator:
    def __init__(self, stock_engine: StockScoringEngine):
        self.engine = stock_engine

    async def generate(
        self,
        budget: float,
        risk_profile: str = "moderate",
        max_stocks: int = 5,
    ) -> Dict:
        today_ist = get_ist_now()
        market_status = get_market_status()

        if budget < MIN_BUDGET:
            return self._no_plan("WAIT",
                f"Budget of Rs {budget:,.0f} is below Rs {MIN_BUDGET:,.0f} minimum. Brokerage fees will eat gains.",
                budget, risk_profile, market_status)

        # Market hours check
        if not is_trading_window():
            if market_status["status"] == "closed" or market_status["status"] == "pre_market":
                return self._no_plan("WAIT",
                    f"NSE is currently closed. {market_status['reason']} Next open: {market_status.get('next_open', 'next trading day')}.",
                    budget, risk_profile, market_status)
            elif market_status["status"] == "stabilizing":
                return self._no_plan("WAIT",
                    "Market just opened. Waiting for 15-minute stabilization. Verdict available at 9:30 AM IST.",
                    budget, risk_profile, market_status)
            elif market_status["status"] == "closing":
                return self._no_plan("WAIT",
                    "Market closing soon. No new entries recommended. Monitor existing positions.",
                    budget, risk_profile, market_status)

        thresholds = STOCK_THRESHOLDS.get(risk_profile, STOCK_THRESHOLDS["moderate"])
        max_stocks = max(1, min(MAX_POSITIONS, max_stocks))

        # Score all stocks
        scored = []
        all_results = await self.engine.score_all()
        for symbol, result in all_results.items():
            stock_info = TRACKED_STOCKS.get(symbol, {})
            scored.append({
                "symbol": symbol,
                "name": stock_info.get("name", symbol),
                "sector": stock_info.get("sector", "Unknown"),
                "score": result["final_score"],
                "action": result["action"],
                "confidence": result["confidence"],
                "factors": result.get("factors", []),
                "factor_details": result.get("factor_details", {}),
                "price_inr": result.get("current_price", 0),
                "change_24h": result.get("change_24h", 0),
            })

        if not scored:
            return self._no_plan("WAIT", "Scoring engine returned no results. Try again.", budget, risk_profile, market_status)

        scored.sort(key=lambda x: x["score"], reverse=True)
        buy_candidates = [s for s in scored if s["score"] >= thresholds["buy"]]
        sell_candidates = [s for s in scored if s["score"] <= thresholds["sell"]]

        avg_score = float(np.mean([s["score"] for s in scored[:20]]))

        if not buy_candidates:
            best = scored[0]
            gap = thresholds["buy"] - best["score"]
            return self._no_plan("WAIT",
                f"No stock reached the {risk_profile} threshold of +{thresholds['buy']}. "
                f"Best: {best['symbol']} ({best['sector']}) at +{best['score']:.1f} (needs +{gap:.1f} more). "
                f"Average score: {avg_score:+.1f}. Wait for stronger signals.",
                budget, risk_profile, market_status,
                market_summary=self._market_summary(scored),
                all_scores=[{"symbol": s["symbol"], "name": s["name"], "sector": s["sector"],
                             "score": round(s["score"], 1), "action": s["action"],
                             "change_24h": round(s["change_24h"], 2)} for s in scored[:20]])

        if sell_candidates and len(sell_candidates) > len(buy_candidates):
            return self._no_plan("NO",
                f"{len(sell_candidates)} stocks show sell signals. Market conditions unfavorable. Protect capital.",
                budget, risk_profile, market_status, market_summary=self._market_summary(scored))

        # Build positions
        selected = buy_candidates[:max_stocks]
        while len(selected) > 1 and budget / len(selected) < MIN_POSITION_INR:
            selected = selected[:-1]

        allocations = ALLOCATION_TIERS.get(len(selected), ALLOCATION_TIERS[5])[:len(selected)]

        positions = []
        total_best = 0
        total_expected = 0
        total_worst = 0

        for i, stock in enumerate(selected):
            alloc = allocations[i]
            amount = round(budget * alloc, 0)
            price = stock["price_inr"]
            if price <= 0:
                continue
            qty = amount / price

            # Get ATR from factor data (stocks have tighter stops)
            s1_data = stock.get("factor_details", {}).get("S1_technical_regime", {}).get("data", {})
            atr_pct = s1_data.get("atr_pct", 1.5)

            # Stock stops are tighter than crypto
            sl_pct = max(1.5, min(atr_pct * 1.5, 5.0))
            stop_loss = price * (1 - sl_pct / 100)

            tp1_pct = max(atr_pct, 1.0)
            tp1 = price * (1 + tp1_pct / 100)

            tp2_pct = atr_pct * 2
            tp2 = price * (1 + tp2_pct / 100)

            tp3_pct = atr_pct * 3
            tp3 = price * (1 + tp3_pct / 100)

            loss_if_sl = amount * (sl_pct / 100)
            gain_tp1 = amount * (tp1_pct / 100)
            gain_tp2 = amount * (tp2_pct / 100)

            # 15% STCG tax for stocks (vs 30% for crypto)
            gain_tp1_after_tax = gain_tp1 * (1 - STOCK_STCG_RATE)
            gain_tp2_after_tax = gain_tp2 * (1 - STOCK_STCG_RATE)

            backtest = s1_data.get("backtest", {})
            win_rate = backtest.get("win_rate_7d", 50)
            expected_value = (win_rate / 100) * gain_tp1_after_tax - ((100 - win_rate) / 100) * loss_if_sl

            total_best += gain_tp2_after_tax
            total_expected += expected_value
            total_worst -= loss_if_sl

            exit_steps = [
                {"step": 1, "condition": f"Price reaches Rs {tp1:,.0f} (+{tp1_pct:.1f}%)",
                 "action": "Sell 50% of position",
                 "detail": f"Lock in Rs {gain_tp1_after_tax * 0.5:,.0f} after 15% tax. Move stop loss to entry price."},
                {"step": 2, "condition": f"Price reaches Rs {tp2:,.0f} (+{tp2_pct:.1f}%)",
                 "action": "Sell another 30%",
                 "detail": f"Total locked: Rs {gain_tp1_after_tax * 0.5 + gain_tp2_after_tax * 0.3:,.0f} after tax."},
                {"step": 3, "condition": f"Price reaches Rs {tp3:,.0f} (+{tp3_pct:.1f}%) OR market close (3:15 PM)",
                 "action": "Sell remaining 20%",
                 "detail": "Close entire position before market close. Do not carry overnight unless the app says to."},
                {"step": "STOP LOSS", "condition": f"Price drops to Rs {stop_loss:,.0f} (-{sl_pct:.1f}%)",
                 "action": "Sell 100% immediately",
                 "detail": f"Max loss: Rs {loss_if_sl:,.0f}. No exceptions. No averaging down."},
            ]

            # Get fundamental summary
            s2_data = stock.get("factor_details", {}).get("S2_fundamental_filter", {}).get("data", {})
            pe = s2_data.get("pe_ratio", 0)
            sector = stock.get("sector", "Unknown")

            positions.append({
                "rank": i + 1,
                "symbol": stock["symbol"],
                "name": stock["name"],
                "sector": sector,
                "score": round(stock["score"], 1),
                "confidence": round(stock["confidence"], 1),
                "allocation_pct": round(alloc * 100, 0),
                "amount_inr": round(amount, 0),
                "current_price": round(price, 2),
                "change_24h": round(stock["change_24h"], 2),
                "quantity": round(qty, 2),
                "entry": {
                    "price": round(price, 2),
                    "range_low": round(price * 0.997, 2),
                    "range_high": round(price * 1.003, 2),
                    "instruction": f"Buy at market price (Rs {price:,.0f}). Place limit order within Rs {price * 0.997:,.0f} to Rs {price * 1.003:,.0f}.",
                },
                "stop_loss": {"price": round(stop_loss, 2), "pct": round(sl_pct, 1), "loss_inr": round(loss_if_sl, 0),
                              "based_on": f"1.5x ATR ({atr_pct:.1f}%), capped at 5%"},
                "take_profit": {
                    "tp1": {"price": round(tp1, 2), "pct": round(tp1_pct, 1), "action": "Sell 50%",
                            "gross_gain": round(gain_tp1, 0), "after_tax": round(gain_tp1_after_tax, 0)},
                    "tp2": {"price": round(tp2, 2), "pct": round(tp2_pct, 1), "action": "Sell 30%",
                            "gross_gain": round(gain_tp2, 0), "after_tax": round(gain_tp2_after_tax, 0)},
                    "tp3": {"price": round(tp3, 2), "pct": round(tp3_pct, 1), "action": "Sell remaining 20%"},
                },
                "expected_outcome": {
                    "best_case_inr": round(gain_tp2_after_tax, 0),
                    "expected_inr": round(expected_value, 0),
                    "worst_case_inr": round(-loss_if_sl, 0),
                    "win_probability": round(win_rate, 0),
                    "note": f"Based on {backtest.get('sample_count', 0)} backtest samples. PE: {pe:.1f}.",
                },
                "exit_instructions": exit_steps,
                "reasoning_summary": f"{stock['symbol']} ({sector}) scored +{stock['score']:.1f}. " +
                    (f"PE {pe:.1f}. " if pe > 0 else "") +
                    f"All 5 factors considered: technicals, fundamentals, sector momentum, news, institutional flows.",
            })

        return {
            "verdict": "YES",
            "verdict_reason": f"{len(selected)} stock(s) passed the {risk_profile} threshold (+{thresholds['buy']}). "
                              f"Market is open and trading window is active.",
            "asset_type": "stocks",
            "date": today_ist.strftime("%Y-%m-%d"),
            "time_ist": today_ist.strftime("%H:%M IST"),
            "budget": round(budget, 0),
            "risk_profile": risk_profile,
            "risk_profile_detail": thresholds,
            "market_status": market_status,
            "summary": {
                "total_deployed": round(sum(p["amount_inr"] for p in positions), 0),
                "positions_count": len(positions),
                "best_case_total": round(total_best, 0),
                "expected_total": round(total_expected, 0),
                "worst_case_total": round(total_worst, 0),
                "tax_note": "All profits shown after 15% STCG tax. Losses cannot offset crypto gains. No TDS on stocks.",
            },
            "positions": positions,
            "market_summary": self._market_summary(scored),
            "all_scores": [{"symbol": s["symbol"], "name": s["name"], "sector": s["sector"],
                            "score": round(s["score"], 1), "action": s["action"],
                            "change_24h": round(s["change_24h"], 2)} for s in scored[:20]],
            "disclaimer": "NOT financial advice. Past performance does not guarantee future results. Consult a SEBI-registered advisor. STCG taxed at 15% for holdings <1 year.",
        }

    def _no_plan(self, verdict, reason, budget, risk_profile, market_status, market_summary=None, all_scores=None):
        today_ist = get_ist_now()
        thresholds = STOCK_THRESHOLDS.get(risk_profile, STOCK_THRESHOLDS["moderate"])
        alternatives = []
        if verdict == "NO":
            alternatives = [
                {"action": "Hold cash", "detail": f"Keep Rs {budget:,.0f} safe. Market is unfavorable."},
                {"action": "Review portfolio", "detail": "Tighten stop losses on existing positions."},
            ]
        elif verdict == "WAIT":
            if market_status.get("status") in ("closed", "pre_market"):
                alternatives = [
                    {"action": market_status.get("reason", "Market closed"), "detail": f"Next open: {market_status.get('next_open', 'next trading day')}"},
                    {"action": "Check crypto", "detail": "Crypto markets are 24/7. Switch to the Crypto tab for live signals."},
                ]
            else:
                alternatives = [
                    {"action": "Check back in 1 hour", "detail": "Stock scores update as the trading day progresses."},
                    {"action": "Try crypto", "detail": "Crypto markets are always open. Switch to the Crypto tab."},
                ]

        return {
            "verdict": verdict, "verdict_reason": reason, "asset_type": "stocks",
            "date": today_ist.strftime("%Y-%m-%d"), "time_ist": today_ist.strftime("%H:%M IST"),
            "budget": round(budget, 0), "risk_profile": risk_profile,
            "risk_profile_detail": thresholds, "market_status": market_status,
            "summary": {"total_deployed": 0, "positions_count": 0, "best_case_total": 0, "expected_total": 0, "worst_case_total": 0},
            "positions": [], "alternatives": alternatives,
            "market_summary": market_summary, "all_scores": all_scores,
            "disclaimer": "NOT financial advice. Consult a SEBI-registered advisor.",
        }

    def _market_summary(self, scored):
        bullish = sum(1 for s in scored[:20] if s["score"] > 15)
        bearish = sum(1 for s in scored[:20] if s["score"] < -15)
        if bullish > bearish + 2:
            mood, detail = "Bullish", f"{bullish}/10 stocks positive"
        elif bearish > bullish + 2:
            mood, detail = "Bearish", f"{bearish}/10 stocks negative"
        else:
            mood, detail = "Mixed", f"{bullish} bullish, {bearish} bearish"
        return {"mood": mood, "mood_detail": detail}