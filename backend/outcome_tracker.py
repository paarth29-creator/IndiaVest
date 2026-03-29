"""
IndiaVest Outcome Tracker
=========================
Background job that runs hourly. Checks all logged recommendations
that are 24h or 7d old and records whether they were profitable.

This is the accountability system. After 30 days of beta testing,
/api/recommendations/track-record shows real win rates.

Usage in server.py:
    from outcome_tracker import start_outcome_tracker
    
    @app.on_event("startup")
    async def startup():
        asyncio.create_task(start_outcome_tracker(db))
"""

import asyncio
import httpx
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

CHECK_INTERVAL_SECONDS = 3600  # Run every hour


async def get_current_price(symbol: str) -> Optional[float]:
    """Fetch current price for a crypto or stock symbol."""
    # Crypto symbols -> CoinGecko
    crypto_to_id = {
        "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
        "LINK": "chainlink", "NEAR": "near", "APT": "aptos",
        "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol",
        "RENDER": "render-token", "SUI": "sui", "SEI": "sei-network",
        "TIA": "celestia", "FET": "fetch-ai",
    }
    
    # Stock symbols -> yfinance (all 50 Nifty stocks)
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

    # Try crypto first
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

    # Try stock
    if upper in stock_symbols:
        try:
            import yfinance as yf
            import asyncio
            loop = asyncio.get_event_loop()
            def _fetch():
                ticker = yf.Ticker(f"{upper}.NS")
                info = ticker.info
                return info.get("currentPrice") or info.get("regularMarketPrice")
            price = await loop.run_in_executor(None, _fetch)
            return float(price) if price else None
        except Exception as e:
            logger.warning(f"Stock price fetch failed for {symbol}: {e}")
        return None

    return None


async def check_outcomes(db) -> Dict:
    """Check all pending recommendations for 24h and 7d outcomes."""
    stats = {"checked": 0, "updated_24h": 0, "updated_7d": 0, "errors": 0}
    now = datetime.now(timezone.utc)

    try:
        # Find recommendations that need 24h check
        # (logged 24-26 hours ago, outcome_24h is still None)
        cutoff_24h_start = now - timedelta(hours=26)
        cutoff_24h_end = now - timedelta(hours=24)

        pending_24h = await db.recommendation_logs.find({
            "outcome_24h": None,
            "timestamp": {"$gte": cutoff_24h_start, "$lte": cutoff_24h_end}
        }).to_list(50)

        for rec in pending_24h:
            stats["checked"] += 1
            try:
                # Handle both formats:
                # Old format: rec["assets"] = [{"symbol": "BTC", "price_at_recommendation": 64000}, ...]
                # Bot format: rec["symbol"] = "BTC", rec["price_at_recommendation"] = 64000
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

                    # Small delay to respect rate limits
                    await asyncio.sleep(0.5)

                if valid_assets > 0:
                    avg_return = total_return / valid_assets
                    was_profitable = avg_return > 0

                    await db.recommendation_logs.update_one(
                        {"_id": rec["_id"]},
                        {"$set": {
                            "outcome_24h": {
                                "avg_return_pct": round(avg_return, 2),
                                "was_profitable": was_profitable,
                                "checked_at": now,
                                "assets_checked": valid_assets,
                            }
                        }}
                    )
                    stats["updated_24h"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Error checking 24h outcome for {rec.get('log_id')}: {e}")

        # Find recommendations that need 7d check
        cutoff_7d_start = now - timedelta(days=7, hours=2)
        cutoff_7d_end = now - timedelta(days=7)

        pending_7d = await db.recommendation_logs.find({
            "outcome_7d": None,
            "outcome_24h": {"$ne": None},  # Must have 24h outcome first
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
                                "checked_at": now,
                                "assets_checked": valid_assets,
                            },
                            "was_profitable": was_profitable,  # Final verdict based on 7d
                        }}
                    )
                    stats["updated_7d"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Error checking 7d outcome for {rec.get('log_id')}: {e}")

    except Exception as e:
        logger.error(f"Outcome tracker batch error: {e}")
        stats["errors"] += 1

    return stats


async def start_outcome_tracker(db):
    """Run outcome checks on a loop. Call as background task at startup."""
    logger.info("Outcome tracker started. Checking every hour.")
    
    # Wait 5 minutes after startup before first check
    await asyncio.sleep(300)

    while True:
        try:
            stats = await check_outcomes(db)
            if stats["checked"] > 0:
                logger.info(
                    f"Outcome tracker: checked {stats['checked']}, "
                    f"updated 24h: {stats['updated_24h']}, "
                    f"updated 7d: {stats['updated_7d']}, "
                    f"errors: {stats['errors']}"
                )
        except Exception as e:
            logger.error(f"Outcome tracker loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)