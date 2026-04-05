"""
IndiaVest Outcome Tracker + Beta Bot
=====================================
Two background loops running concurrently via asyncio.gather:

1. OUTCOME CHECKER (hourly): Checks 24h/7d outcomes for logged recommendations
2. BETA BOT (every 15 min): Scores crypto+stocks, logs signals to MongoDB

Both run inside start_outcome_tracker(db) which is called from server.py startup.
This function signature has existed since Day 6 and is imported by ALL versions
of server.py in git. No changes to server.py are needed.

Usage in server.py (UNCHANGED):
    from outcome_tracker import start_outcome_tracker
    
    @app.on_event("startup")
    async def startup():
        asyncio.create_task(start_outcome_tracker(db))
"""

import asyncio
import uuid
import httpx
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

OUTCOME_CHECK_INTERVAL = 3600  # 1 hour
BOT_CYCLE_INTERVAL = 900       # 15 minutes
BOT_PROFILES = ["conservative", "moderate", "aggressive"]


# ====================================================================
# PRICE FETCHER (used by outcome checker)
# ====================================================================

async def get_current_price(symbol: str) -> Optional[float]:
    """Fetch current price for a crypto or stock symbol."""
    crypto_to_id = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
        "LINK": "chainlink", "NEAR": "near", "APT": "aptos",
        "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
        "RENDER": "render-token", "SUI": "sui", "SEI": "sei-network",
        "TIA": "celestia", "FET": "fetch-ai",
    }
    stock_symbols = {
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN",
        "BHARTIARTL", "BAJFINANCE", "LT", "MARUTI", "SUNPHARMA",
        "TATAMOTORS", "NTPC", "TITAN", "ADANIENT", "ONGC",
        "JSWSTEEL", "WIPRO", "COALINDIA", "ITC",
        "HINDUNILVR", "AXISBANK", "KOTAKBANK", "HCLTECH", "TECHM",
        "NESTLEIND", "ULTRACEMCO", "POWERGRID", "TATASTEEL", "ADANIPORTS",
        "DRREDDY", "CIPLA", "DIVISLAB", "EICHERMOT", "GRASIM",
        "HEROMOTOCO", "HINDALCO", "INDUSINDBK", "M&M",
        "BAJAJ-AUTO", "BAJAJFINSV", "BPCL", "BRITANNIA", "HDFCLIFE",
        "SBILIFE", "SHREECEM", "TATACONSUM", "UPL", "VEDL",
        "ASIANPAINT",
    }
    upper = symbol.upper()

    coin_id = crypto_to_id.get(upper)
    if coin_id:
        try:
            headers = {}
            if COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{COINGECKO_BASE_URL}/simple/price",
                    params={"ids": coin_id, "vs_currencies": "inr"},
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get(coin_id, {}).get("inr")
        except Exception as e:
            logger.warning(f"Crypto price fetch failed for {symbol}: {e}")
        return None

    if upper in stock_symbols:
        try:
            import yfinance as yf
            loop = asyncio.get_event_loop()
            yf_sym = f"{upper}.NS"
            def _fetch():
                ticker = yf.Ticker(yf_sym)
                info = ticker.info
                return info.get("currentPrice") or info.get("regularMarketPrice")
            price = await loop.run_in_executor(None, _fetch)
            return float(price) if price else None
        except Exception as e:
            logger.warning(f"Stock price fetch failed for {symbol}: {e}")
        return None

    return None


# ====================================================================
# OUTCOME CHECKER
# ====================================================================

async def check_outcomes(db) -> Dict:
    """Check all pending recommendations for 24h and 7d outcomes."""
    stats = {"checked": 0, "updated_24h": 0, "updated_7d": 0, "errors": 0}
    now = datetime.now(timezone.utc)

    try:
        # 24h outcomes
        cutoff_24h_start = now - timedelta(hours=26)
        cutoff_24h_end = now - timedelta(hours=24)

        pending_24h = await db.recommendation_logs.find({
            "outcome_24h": None,
            "timestamp": {"$gte": cutoff_24h_start, "$lte": cutoff_24h_end}
        }).to_list(50)

        for rec in pending_24h:
            stats["checked"] += 1
            try:
                assets = rec.get("assets", [])
                if not assets and rec.get("symbol") and rec.get("price_at_recommendation"):
                    assets = [{"symbol": rec["symbol"], "price_at_recommendation": rec["price_at_recommendation"]}]
                if not assets:
                    continue

                total_return = 0
                valid_assets = 0
                for asset in assets:
                    symbol = asset.get("symbol", "")
                    price_at_rec = asset.get("price_at_recommendation", 0)
                    if not symbol or not price_at_rec:
                        continue
                    current_price = await get_current_price(symbol)
                    if current_price is None:
                        continue
                    ret_pct = ((current_price - price_at_rec) / price_at_rec) * 100
                    total_return += ret_pct
                    valid_assets += 1
                    await asyncio.sleep(0.5)

                if valid_assets > 0:
                    avg_return = total_return / valid_assets
                    was_profitable = avg_return > 0
                    await db.recommendation_logs.update_one(
                        {"_id": rec["_id"]},
                        {"$set": {"outcome_24h": {
                            "avg_return_pct": round(avg_return, 2),
                            "was_profitable": was_profitable,
                            "checked_at": now, "assets_checked": valid_assets,
                        }}}
                    )
                    stats["updated_24h"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"24h outcome error for {rec.get('log_id')}: {e}")

        # 7d outcomes
        cutoff_7d_start = now - timedelta(days=7, hours=2)
        cutoff_7d_end = now - timedelta(days=7)

        pending_7d = await db.recommendation_logs.find({
            "outcome_7d": None,
            "outcome_24h": {"$ne": None},
            "timestamp": {"$gte": cutoff_7d_start, "$lte": cutoff_7d_end}
        }).to_list(50)

        for rec in pending_7d:
            stats["checked"] += 1
            try:
                assets = rec.get("assets", [])
                if not assets and rec.get("symbol") and rec.get("price_at_recommendation"):
                    assets = [{"symbol": rec["symbol"], "price_at_recommendation": rec["price_at_recommendation"]}]
                if not assets:
                    continue

                total_return = 0
                valid_assets = 0
                for asset in assets:
                    symbol = asset.get("symbol", "")
                    price_at_rec = asset.get("price_at_recommendation", 0)
                    if not symbol or not price_at_rec:
                        continue
                    current_price = await get_current_price(symbol)
                    if current_price is None:
                        continue
                    ret_pct = ((current_price - price_at_rec) / price_at_rec) * 100
                    total_return += ret_pct
                    valid_assets += 1
                    await asyncio.sleep(0.5)

                if valid_assets > 0:
                    avg_return = total_return / valid_assets
                    was_profitable = avg_return > 0
                    await db.recommendation_logs.update_one(
                        {"_id": rec["_id"]},
                        {"$set": {
                            "outcome_7d": {
                                "avg_return_pct": round(avg_return, 2),
                                "was_profitable": was_profitable,
                                "checked_at": now, "assets_checked": valid_assets,
                            },
                            "was_profitable": was_profitable,
                        }}
                    )
                    stats["updated_7d"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"7d outcome error for {rec.get('log_id')}: {e}")

    except Exception as e:
        logger.error(f"Outcome checker batch error: {e}")
        stats["errors"] += 1

    return stats


async def _outcome_loop(db):
    """Outcome checking loop. Runs every hour."""
    while True:
        try:
            stats = await check_outcomes(db)
            if stats["checked"] > 0:
                logger.info(f"Outcomes: checked {stats['checked']}, 24h: {stats['updated_24h']}, 7d: {stats['updated_7d']}, errors: {stats['errors']}")
        except Exception as e:
            logger.error(f"Outcome loop error: {e}")
        await asyncio.sleep(OUTCOME_CHECK_INTERVAL)


# ====================================================================
# BETA BOT
# ====================================================================

async def _bot_loop(db):
    """Bot scoring loop. Runs every 15 minutes.
    Creates its own engine instances. No server.py imports needed."""
    
    # Lazy imports inside function to avoid startup ordering issues
    try:
        from scoring_engine import ScoringEngine
        from trade_plan_generator import TradePlanGenerator
        from stock_scoring_engine import StockScoringEngine, is_trading_window
        from stock_trade_plan_generator import StockTradePlanGenerator
    except ImportError as e:
        logger.error(f"Beta bot: cannot import scoring modules: {e}. Bot disabled.")
        return

    # Create dedicated engine instances for the bot
    scoring_engine = ScoringEngine(db)
    stock_engine = StockScoringEngine(db)
    stock_plan_gen = StockTradePlanGenerator(stock_engine)
    trade_plan_gen = TradePlanGenerator(scoring_engine, None)
    
    # Try to get crypto_service from server module
    try:
        import server
        trade_plan_gen.crypto = server.crypto_service
    except Exception:
        logger.warning("Beta bot: crypto_service not available, will use cached prices only")

    logger.info("Beta bot initialized. Scoring every 15 minutes.")

    while True:
        try:
            cycle_start = datetime.now(timezone.utc)
            crypto_count = 0
            stock_count = 0
            errors = []

            # CRYPTO: Score across all 3 risk profiles
            for profile in BOT_PROFILES:
                try:
                    plan = await trade_plan_gen.generate(budget=10000, risk_profile=profile, max_coins=5)
                    verdict = plan.get("verdict", "WAIT")

                    if verdict == "YES" and plan.get("positions"):
                        for pos in plan["positions"]:
                            recent = await db.recommendation_logs.find_one({
                                "symbol": pos["symbol"], "risk_profile": profile,
                                "asset_type": "crypto", "source": "bot",
                                "timestamp": {"$gte": cycle_start - timedelta(minutes=30)}
                            })
                            if recent:
                                continue
                            await db.recommendation_logs.insert_one({
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
                                "outcome_24h": None, "outcome_7d": None, "was_profitable": None,
                            })
                            crypto_count += 1
                except Exception as e:
                    errors.append(f"Crypto {profile}: {str(e)}")

            # STOCKS: Score only during market hours
            try:
                if is_trading_window():
                    for profile in BOT_PROFILES:
                        try:
                            plan = await stock_plan_gen.generate(budget=10000, risk_profile=profile, max_stocks=5)
                            verdict = plan.get("verdict", "WAIT")
                            if verdict == "YES" and plan.get("positions"):
                                for pos in plan["positions"]:
                                    recent = await db.recommendation_logs.find_one({
                                        "symbol": pos["symbol"], "risk_profile": profile,
                                        "asset_type": "stocks", "source": "bot",
                                        "timestamp": {"$gte": cycle_start - timedelta(minutes=30)}
                                    })
                                    if recent:
                                        continue
                                    await db.recommendation_logs.insert_one({
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
                                        "outcome_24h": None, "outcome_7d": None, "was_profitable": None,
                                    })
                                    stock_count += 1
                        except Exception as e:
                            errors.append(f"Stocks {profile}: {str(e)}")
            except Exception as e:
                errors.append(f"Stock module: {str(e)}")

            duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            logger.info(f"Bot cycle: {crypto_count} crypto, {stock_count} stock signals in {duration:.1f}s | Errors: {len(errors)}")
            if errors:
                for e in errors:
                    logger.warning(f"  {e}")

        except Exception as e:
            logger.error(f"Bot loop error: {e}")

        await asyncio.sleep(BOT_CYCLE_INTERVAL)


# ====================================================================
# MAIN ENTRY POINT (called from server.py startup)
# Function signature: start_outcome_tracker(db) - UNCHANGED since Day 6
# ====================================================================

async def start_outcome_tracker(db):
    """Called from server.py as: asyncio.create_task(start_outcome_tracker(db))
    
    Runs BOTH the outcome checker AND the beta bot concurrently.
    Function signature has not changed. server.py does not need updating.
    """
    logger.info("Starting outcome tracker + beta bot (asyncio.gather)...")
    
    # Wait for data preloader and cache warming to finish
    await asyncio.sleep(300)

    # Run both loops concurrently. return_exceptions=True means
    # if one crashes, the other keeps running.
    await asyncio.gather(
        _outcome_loop(db),
        _bot_loop(db),
        return_exceptions=True,
    )