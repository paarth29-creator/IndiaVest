"""
IndiaVest Beta Bot
==================
Background task that runs every 15 minutes INSIDE the server process.
Same architecture as outcome_tracker.py (which runs reliably).

Does NOT depend on any HTTP endpoint.
Does NOT need an external service to call it.
Runs automatically as long as the server is alive.

The external cron job (cron-job.org) only needs to ping the root URL
to keep the server awake. The bot handles everything else internally.

Usage in server.py:
    from beta_bot import start_beta_bot
    
    @app.on_event("startup")
    async def startup():
        asyncio.create_task(start_beta_bot(db, trade_plan_gen, stock_trade_plan_gen))
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)

BOT_CYCLE_SECONDS = 900  # 15 minutes
PROFILES = ["conservative", "moderate", "aggressive"]


async def run_one_cycle(db, trade_plan_gen, stock_trade_plan_gen) -> Dict:
    """Run a single scoring cycle for both crypto and stocks.
    
    Calls the EXISTING trade plan generators internally.
    No HTTP requests. No endpoints. Just function calls.
    """
    cycle_start = datetime.now(timezone.utc)
    ist_now = cycle_start + timedelta(hours=5, minutes=30)
    
    results = {
        "cycle_time": ist_now.isoformat(),
        "crypto_signals": [],
        "stock_signals": [],
        "errors": [],
    }

    # ---- CRYPTO: Score across all 3 risk profiles ----
    for profile in PROFILES:
        try:
            plan = await trade_plan_gen.generate(
                budget=10000, risk_profile=profile, max_coins=5
            )
            verdict = plan.get("verdict", "WAIT")

            if verdict == "YES" and plan.get("positions"):
                for pos in plan["positions"]:
                    # Dedup: skip if same symbol+profile logged in last 30 min
                    recent = await db.recommendation_logs.find_one({
                        "symbol": pos["symbol"],
                        "risk_profile": profile,
                        "asset_type": "crypto",
                        "source": "bot",
                        "timestamp": {"$gte": cycle_start - timedelta(minutes=30)}
                    })
                    if recent:
                        continue

                    log_entry = {
                        "log_id": str(uuid.uuid4()),
                        "timestamp": cycle_start,
                        "source": "bot",
                        "asset_type": "crypto",
                        "symbol": pos["symbol"],
                        "recommendation": "BUY",
                        "risk_profile": profile,
                        "price_at_recommendation": pos["current_price"],
                        "score": pos["score"],
                        "confidence": pos["confidence"],
                        "stop_loss": pos["stop_loss"]["price"],
                        "take_profit_1": pos["take_profit"]["tp1"]["price"],
                        "take_profit_2": pos["take_profit"]["tp2"]["price"],
                        "outcome_24h": None,
                        "outcome_7d": None,
                        "was_profitable": None,
                    }
                    await db.recommendation_logs.insert_one(log_entry)
                    results["crypto_signals"].append({
                        "symbol": pos["symbol"],
                        "action": "BUY",
                        "profile": profile,
                        "score": pos["score"],
                        "price": pos["current_price"],
                    })

        except Exception as e:
            results["errors"].append(f"Crypto {profile}: {str(e)}")
            logger.error(f"Beta bot crypto error ({profile}): {e}")

    # ---- STOCKS: Score only during market hours ----
    try:
        from stock_scoring_engine import is_trading_window
        if is_trading_window():
            for profile in PROFILES:
                try:
                    plan = await stock_trade_plan_gen.generate(
                        budget=10000, risk_profile=profile, max_stocks=5
                    )
                    verdict = plan.get("verdict", "WAIT")

                    if verdict == "YES" and plan.get("positions"):
                        for pos in plan["positions"]:
                            recent = await db.recommendation_logs.find_one({
                                "symbol": pos["symbol"],
                                "risk_profile": profile,
                                "asset_type": "stocks",
                                "source": "bot",
                                "timestamp": {"$gte": cycle_start - timedelta(minutes=30)}
                            })
                            if recent:
                                continue

                            log_entry = {
                                "log_id": str(uuid.uuid4()),
                                "timestamp": cycle_start,
                                "source": "bot",
                                "asset_type": "stocks",
                                "symbol": pos["symbol"],
                                "recommendation": "BUY",
                                "risk_profile": profile,
                                "price_at_recommendation": pos["current_price"],
                                "score": pos["score"],
                                "confidence": pos["confidence"],
                                "stop_loss": pos["stop_loss"]["price"],
                                "take_profit_1": pos["take_profit"]["tp1"]["price"],
                                "take_profit_2": pos["take_profit"]["tp2"]["price"],
                                "sector": pos.get("sector", ""),
                                "outcome_24h": None,
                                "outcome_7d": None,
                                "was_profitable": None,
                            }
                            await db.recommendation_logs.insert_one(log_entry)
                            results["stock_signals"].append({
                                "symbol": pos["symbol"],
                                "action": "BUY",
                                "profile": profile,
                                "score": pos["score"],
                                "price": pos["current_price"],
                            })

                except Exception as e:
                    results["errors"].append(f"Stocks {profile}: {str(e)}")
                    logger.error(f"Beta bot stock error ({profile}): {e}")
        else:
            results["stock_signals"].append({"status": "market_closed"})
    except Exception as e:
        results["errors"].append(f"Stock import error: {str(e)}")
        logger.error(f"Beta bot stock module error: {e}")

    cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    results["cycle_duration_seconds"] = round(cycle_duration, 1)
    results["crypto_signals_count"] = len([s for s in results["crypto_signals"] if isinstance(s, dict) and "action" in s])
    results["stock_signals_count"] = len([s for s in results["stock_signals"] if isinstance(s, dict) and "action" in s])

    return results


async def start_beta_bot(db, trade_plan_gen, stock_trade_plan_gen):
    """Background loop that runs scoring cycles every 15 minutes.
    
    Started as asyncio.create_task() at server boot.
    Same pattern as start_outcome_tracker() which runs reliably.
    Does NOT depend on any HTTP endpoint or external trigger.
    The cron job only keeps the server alive; this loop does the work.
    """
    logger.info("Beta bot started. Scoring every 15 minutes.")
    
    # Wait 3 minutes after startup for data preloader to finish
    await asyncio.sleep(180)

    while True:
        try:
            results = await run_one_cycle(db, trade_plan_gen, stock_trade_plan_gen)
            crypto_count = results.get("crypto_signals_count", 0)
            stock_count = results.get("stock_signals_count", 0)
            duration = results.get("cycle_duration_seconds", 0)
            errors = results.get("errors", [])
            
            logger.info(
                f"Beta bot cycle: {crypto_count} crypto, {stock_count} stock signals "
                f"in {duration:.1f}s | Errors: {len(errors)}"
            )
            if errors:
                for e in errors:
                    logger.warning(f"  Bot error: {e}")
                    
        except Exception as e:
            logger.error(f"Beta bot loop error: {e}")

        await asyncio.sleep(BOT_CYCLE_SECONDS)


async def get_bot_report(db) -> Dict:
    """Generate beta test report from all bot-logged recommendations.
    Called by the /api/bot/report endpoint."""
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

    all_signals = await db.recommendation_logs.find({"source": "bot"}).to_list(10000)

    if not all_signals:
        return {
            "status": "no_data",
            "message": "No bot signals logged yet. The bot needs to run for at least a few hours before a report is meaningful.",
            "report_time": ist_now.isoformat(),
        }

    crypto_buys = [s for s in all_signals if s.get("asset_type") == "crypto" and s.get("recommendation") == "BUY"]
    stock_buys = [s for s in all_signals if s.get("asset_type") == "stocks" and s.get("recommendation") == "BUY"]

    def analyze_group(signals, label, tax_rate):
        total = len(signals)
        with_24h = [s for s in signals if s.get("outcome_24h") is not None]
        with_7d = [s for s in signals if s.get("outcome_7d") is not None]

        wins_24h = [s for s in with_24h if s["outcome_24h"].get("was_profitable")]
        wins_7d = [s for s in with_7d if s["outcome_7d"].get("was_profitable")]

        returns_24h = [s["outcome_24h"]["avg_return_pct"] for s in with_24h if "avg_return_pct" in s.get("outcome_24h", {})]
        returns_7d = [s["outcome_7d"]["avg_return_pct"] for s in with_7d if "avg_return_pct" in s.get("outcome_7d", {})]

        profile_stats = {}
        for profile in PROFILES:
            p_signals = [s for s in signals if s.get("risk_profile") == profile]
            p_24h = [s for s in p_signals if s.get("outcome_24h") is not None]
            p_wins = [s for s in p_24h if s["outcome_24h"].get("was_profitable")]
            profile_stats[profile] = {
                "total_signals": len(p_signals),
                "checked_24h": len(p_24h),
                "wins_24h": len(p_wins),
                "win_rate_24h": round(len(p_wins) / len(p_24h) * 100, 1) if p_24h else None,
            }

        symbols = list(set(s.get("symbol", "?") for s in signals))

        return {
            "label": label,
            "total_signals": total,
            "unique_symbols": symbols,
            "outcomes_24h": {
                "checked": len(with_24h),
                "pending": total - len(with_24h),
                "wins": len(wins_24h),
                "losses": len(with_24h) - len(wins_24h),
                "win_rate": round(len(wins_24h) / len(with_24h) * 100, 1) if with_24h else None,
                "avg_return": round(sum(returns_24h) / len(returns_24h), 2) if returns_24h else None,
                "avg_return_after_tax": round(sum(max(0, r) * (1 - tax_rate) + min(0, r) for r in returns_24h) / len(returns_24h), 2) if returns_24h else None,
                "best_return": round(max(returns_24h), 2) if returns_24h else None,
                "worst_return": round(min(returns_24h), 2) if returns_24h else None,
            },
            "outcomes_7d": {
                "checked": len(with_7d),
                "pending": total - len(with_7d),
                "wins": len(wins_7d),
                "losses": len(with_7d) - len(wins_7d),
                "win_rate": round(len(wins_7d) / len(with_7d) * 100, 1) if with_7d else None,
                "avg_return": round(sum(returns_7d) / len(returns_7d), 2) if returns_7d else None,
                "best_return": round(max(returns_7d), 2) if returns_7d else None,
                "worst_return": round(min(returns_7d), 2) if returns_7d else None,
            },
            "by_risk_profile": profile_stats,
        }

    timestamps = [s.get("timestamp") for s in all_signals if s.get("timestamp")]
    first_signal = min(timestamps) if timestamps else None
    last_signal = max(timestamps) if timestamps else None
    days_running = (last_signal - first_signal).days + 1 if first_signal and last_signal else 0

    return {
        "report_time": ist_now.isoformat(),
        "beta_days_running": days_running,
        "first_signal": first_signal.isoformat() if first_signal else None,
        "last_signal": last_signal.isoformat() if last_signal else None,
        "total_signals": len(all_signals),
        "crypto": analyze_group(crypto_buys, "Crypto (4-factor engine)", 0.30),
        "stocks": analyze_group(stock_buys, "Stocks (5-factor engine)", 0.15),
        "success_criteria": {
            "crypto_win_rate_target": ">55%",
            "stock_win_rate_target": ">55%",
            "crypto_avg_return_target": "Positive after 30% tax",
            "stock_avg_return_target": "Positive after 15% tax",
            "max_single_loss_target": "<5% (crypto), <3% (stocks)",
        },
    }