"""
IndiaVest Outcome Tracker + Beta Bot (DIAGNOSTIC VERSION)
==========================================================
Two background loops running concurrently via asyncio.gather:

1. OUTCOME CHECKER (hourly): Checks 24h/7d outcomes for logged recommendations
2. BETA BOT (every 15 min): Scores crypto+stocks, logs signals to MongoDB

DIAGNOSTIC: Every bot cycle writes to 'bot_diagnostics' collection in MongoDB.
Check: db.bot_diagnostics.find().sort({timestamp:-1}).limit(5)
Or via Emergent: python3 -c "..." to read diagnostics

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
# PRICE FETCHER (used by outcome checker AND bot)
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
# BOT PRICE FETCHER: Gets prices for all 20 coins directly from CoinGecko
# This replaces the broken crypto_service dependency
# ====================================================================

async def get_bot_crypto_prices() -> Dict:
    """Fetch prices for all tracked coins directly from CoinGecko.
    Returns dict like: {"BTC": {"price_inr": 6300000, "name": "Bitcoin", ...}}
    This does NOT depend on crypto_service or server.py."""
    
    symbol_to_id = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
        "LINK": "chainlink", "NEAR": "near", "APT": "aptos",
        "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
        "RENDER": "render-token", "SUI": "sui", "SEI": "sei-network",
        "TIA": "celestia", "FET": "fetch-ai",
    }
    
    coin_ids = ",".join(symbol_to_id.values())
    
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{COINGECKO_BASE_URL}/simple/price",
                params={"ids": coin_ids, "vs_currencies": "inr", "include_24hr_change": "true", "include_24hr_vol": "true"},
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                result = {}
                for symbol, coin_id in symbol_to_id.items():
                    if coin_id in data:
                        result[symbol] = {
                            "price_inr": data[coin_id].get("inr", 0),
                            "name": symbol,
                            "change_24h": data[coin_id].get("inr_24h_change", 0),
                            "volume_24h": data[coin_id].get("inr_24h_vol", 0),
                        }
                return result
            else:
                logger.warning(f"Bot price fetch: CoinGecko returned {response.status_code}")
    except Exception as e:
        logger.warning(f"Bot price fetch failed: {e}")
    
    # Fallback: try to get prices from MongoDB cache
    return {}


# ====================================================================
# CUSTOM BOT CRYPTO SERVICE: Wraps get_bot_crypto_prices so
# TradePlanGenerator can call self.crypto.get_prices()
# ====================================================================

class BotCryptoService:
    """Minimal crypto service that fetches prices directly from CoinGecko.
    Passed to TradePlanGenerator as crypto_service replacement."""
    
    async def get_prices(self):
        return await get_bot_crypto_prices()


# ====================================================================
# OUTCOME CHECKER
# ====================================================================

async def check_outcomes(db) -> Dict:
    """Check all pending recommendations for 24h and 7d outcomes."""
    stats = {"checked": 0, "updated_24h": 0, "updated_7d": 0, "errors": 0}
    now = datetime.now(timezone.utc)

    try:
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
# BETA BOT (with diagnostic logging + direct price fetching)
# ====================================================================

async def _bot_loop(db):
    """Bot scoring loop. Runs every 15 minutes.
    FIXED: Uses BotCryptoService to fetch prices directly from CoinGecko.
    DIAGNOSTIC: Writes every cycle result to bot_diagnostics collection."""
    
    try:
        from scoring_engine import ScoringEngine
        from trade_plan_generator import TradePlanGenerator
        from stock_scoring_engine import StockScoringEngine, is_trading_window
        from stock_trade_plan_generator import StockTradePlanGenerator
    except ImportError as e:
        logger.error(f"Beta bot: cannot import scoring modules: {e}. Bot disabled.")
        # Write import failure to diagnostics
        try:
            await db.bot_diagnostics.insert_one({
                "timestamp": datetime.now(timezone.utc),
                "event": "IMPORT_FAILURE",
                "error": str(e),
            })
        except:
            pass
        return

    # Create engine instances
    scoring_engine = ScoringEngine(db)
    stock_engine = StockScoringEngine(db)
    stock_plan_gen = StockTradePlanGenerator(stock_engine)
    
    # THE FIX: Use BotCryptoService instead of server.crypto_service
    # This fetches prices directly from CoinGecko, no dependency on server.py
    bot_crypto = BotCryptoService()
    trade_plan_gen = TradePlanGenerator(scoring_engine, bot_crypto)

    logger.info("Beta bot initialized with BotCryptoService. Scoring every 15 minutes.")

    # Write startup diagnostic
    try:
        await db.bot_diagnostics.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "event": "BOT_STARTED",
            "crypto_service": "BotCryptoService (direct CoinGecko)",
        })
    except:
        pass

    while True:
        cycle_start = datetime.now(timezone.utc)
        diag = {
            "timestamp": cycle_start,
            "event": "CYCLE",
            "crypto_verdicts": {},
            "stock_verdicts": {},
            "crypto_signals_logged": 0,
            "stock_signals_logged": 0,
            "errors": [],
        }

        try:
            crypto_count = 0
            stock_count = 0

            # CRYPTO: Score across all 3 risk profiles
            for profile in BOT_PROFILES:
                try:
                    plan = await trade_plan_gen.generate(budget=10000, risk_profile=profile, max_coins=5)
                    verdict = plan.get("verdict", "WAIT")
                    reason = plan.get("verdict_reason", "no reason")
                    positions_count = len(plan.get("positions", []))
                    all_scores_count = len(plan.get("all_scores", []))
                    
                    # DIAGNOSTIC: Record what generate() returned
                    diag["crypto_verdicts"][profile] = {
                        "verdict": verdict,
                        "reason": reason[:200],
                        "positions": positions_count,
                        "all_scores": all_scores_count,
                    }

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
                    diag["errors"].append(f"Crypto {profile}: {str(e)}")

            # STOCKS: Score only during market hours
            try:
                trading = is_trading_window()
                diag["stock_market_open"] = trading
                if trading:
                    for profile in BOT_PROFILES:
                        try:
                            plan = await stock_plan_gen.generate(budget=10000, risk_profile=profile, max_stocks=5)
                            verdict = plan.get("verdict", "WAIT")
                            reason = plan.get("verdict_reason", "no reason")
                            
                            diag["stock_verdicts"][profile] = {
                                "verdict": verdict,
                                "reason": reason[:200],
                                "positions": len(plan.get("positions", [])),
                            }
                            
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
                            diag["errors"].append(f"Stocks {profile}: {str(e)}")
            except Exception as e:
                diag["errors"].append(f"Stock module: {str(e)}")

            diag["crypto_signals_logged"] = crypto_count
            diag["stock_signals_logged"] = stock_count
            diag["duration_seconds"] = round((datetime.now(timezone.utc) - cycle_start).total_seconds(), 1)

            logger.info(f"Bot cycle: {crypto_count} crypto, {stock_count} stock signals in {diag['duration_seconds']}s | Errors: {len(diag['errors'])}")

        except Exception as e:
            diag["errors"].append(f"Loop error: {str(e)}")
            logger.error(f"Bot loop error: {e}")

        # DIAGNOSTIC: Write this cycle's results to MongoDB NO MATTER WHAT
        try:
            await db.bot_diagnostics.insert_one(diag)
        except Exception as e:
            logger.error(f"Failed to write diagnostic: {e}")

        await asyncio.sleep(BOT_CYCLE_INTERVAL)


# ====================================================================
# MAIN ENTRY POINT
# Function signature: start_outcome_tracker(db) - UNCHANGED since Day 6
# ====================================================================

async def start_outcome_tracker(db):
    """Called from server.py as: asyncio.create_task(start_outcome_tracker(db))"""
    logger.info("Starting outcome tracker + beta bot (asyncio.gather)...")
    
    # Wait for data preloader to finish
    await asyncio.sleep(300)

    await asyncio.gather(
        _outcome_loop(db),
        _bot_loop(db),
        return_exceptions=True,
    )