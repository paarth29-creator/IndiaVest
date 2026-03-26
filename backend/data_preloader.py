"""
IndiaVest Data Preloader
========================
Fetches and caches 365 days of daily price + volume data for all tracked coins.
Stores raw data in MongoDB so the backtester never hits CoinGecko repeatedly.

Rate limit handling:
  - CoinGecko free tier with API key: 30 requests/minute
  - We fetch 10 coins = 10 requests
  - 2-second delay between requests to stay safe
  - Raw data refreshes every 12 hours (not every backtest run)

Collections used:
  - market_data_cache:    raw daily prices + volumes per coin
  - regime_backtests:     computed regime statistics (from scoring_engine.py)

Usage:
  preloader = DataPreloader(db)
  await preloader.load_all()              # fetch + cache all coins
  data = await preloader.get_cached("bitcoin")  # retrieve cached data
"""

import asyncio
import httpx
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging
import os

logger = logging.getLogger(__name__)

COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# All coins we track (CoinGecko IDs)
TRACKED_COINS = [
    "bitcoin", "ethereum", "solana", "binancecoin", "ripple",
    "cardano", "dogecoin", "avalanche-2", "polkadot", "chainlink"
]

# How often to refresh raw data (hours)
RAW_DATA_TTL_HOURS = 12

# Delay between CoinGecko requests (seconds) to respect rate limits
REQUEST_DELAY = 2.5


class DataPreloader:
    """Fetches and caches historical market data in MongoDB."""

    def __init__(self, db):
        self.db = db
        self.collection = db["market_data_cache"]
        self._loading = False

    async def load_all(self, days: int = 365, force: bool = False) -> Dict[str, str]:
        """Fetch 365 days of data for all tracked coins.
        
        Args:
            days: number of days of history to fetch
            force: if True, bypass cache TTL and re-fetch everything
            
        Returns:
            {coin_id: "loaded" | "cached" | "failed"}
        """
        if self._loading:
            logger.warning("Data preloader already running, skipping duplicate call")
            return {c: "skipped" for c in TRACKED_COINS}

        self._loading = True
        results = {}
        loaded_count = 0
        cached_count = 0
        failed_count = 0

        logger.info(f"Starting data preload for {len(TRACKED_COINS)} coins ({days} days each)...")

        for coin_id in TRACKED_COINS:
            try:
                if not force:
                    existing = await self._get_if_fresh(coin_id, days)
                    if existing:
                        results[coin_id] = "cached"
                        cached_count += 1
                        logger.info(f"  {coin_id}: using cached data ({existing['data_points']} points)")
                        continue

                # Fetch from CoinGecko
                data = await self._fetch_from_coingecko(coin_id, days)
                if data:
                    await self._store(coin_id, days, data)
                    results[coin_id] = "loaded"
                    loaded_count += 1
                    logger.info(f"  {coin_id}: fetched {len(data['prices'])} data points")
                else:
                    results[coin_id] = "failed"
                    failed_count += 1
                    logger.warning(f"  {coin_id}: fetch failed")

                # Rate limit delay (only between API calls, not for cached)
                await asyncio.sleep(REQUEST_DELAY)

            except Exception as e:
                results[coin_id] = "failed"
                failed_count += 1
                logger.error(f"  {coin_id}: error: {e}")

        self._loading = False
        logger.info(
            f"Preload complete: {loaded_count} loaded, {cached_count} cached, {failed_count} failed"
        )
        return results

    async def get_cached(self, coin_id: str, days: int = 365) -> Optional[Dict]:
        """Get cached market data for a coin.
        
        Returns:
            {"timestamps": [...], "prices": [...], "volumes": [...], "data_points": int}
            or None if not cached.
        """
        doc = await self._get_if_fresh(coin_id, days)
        if doc:
            return {
                "timestamps": doc["timestamps"],
                "prices": doc["prices"],
                "volumes": doc["volumes"],
                "data_points": doc["data_points"],
                "fetched_at": doc["fetched_at"],
            }
        return None

    async def get_or_fetch(self, coin_id: str, days: int = 365) -> Optional[Dict]:
        """Get cached data, or fetch if missing/stale. Single coin, on-demand."""
        cached = await self.get_cached(coin_id, days)
        if cached:
            return cached

        data = await self._fetch_from_coingecko(coin_id, days)
        if data:
            await self._store(coin_id, days, data)
            return data
        return None

    async def get_all_cached(self) -> Dict[str, Optional[Dict]]:
        """Get cached data for all tracked coins."""
        results = {}
        for coin_id in TRACKED_COINS:
            results[coin_id] = await self.get_cached(coin_id)
        return results

    async def get_cache_status(self) -> Dict:
        """Return cache freshness status for all coins."""
        status = {}
        for coin_id in TRACKED_COINS:
            doc = await self.collection.find_one(
                {"coin_id": coin_id},
                {"fetched_at": 1, "data_points": 1, "days": 1}
            )
            if doc:
                age_hours = (datetime.now(timezone.utc) - doc["fetched_at"]).total_seconds() / 3600
                status[coin_id] = {
                    "cached": True,
                    "data_points": doc.get("data_points", 0),
                    "fetched_at": doc["fetched_at"].isoformat(),
                    "age_hours": round(age_hours, 1),
                    "fresh": age_hours < RAW_DATA_TTL_HOURS,
                }
            else:
                status[coin_id] = {
                    "cached": False,
                    "data_points": 0,
                    "fetched_at": None,
                    "age_hours": None,
                    "fresh": False,
                }
        return status

    # ---- Private methods ----

    async def _get_if_fresh(self, coin_id: str, days: int) -> Optional[Dict]:
        """Check if we have fresh cached data."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=RAW_DATA_TTL_HOURS)
        doc = await self.collection.find_one({
            "coin_id": coin_id,
            "days": {"$gte": days},
            "fetched_at": {"$gte": cutoff}
        })
        return doc

    async def _fetch_from_coingecko(self, coin_id: str, days: int) -> Optional[Dict]:
        """Fetch daily market chart data from CoinGecko."""
        try:
            headers = {}
            if COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
                    params={
                        "vs_currency": "inr",
                        "days": str(days),
                        "interval": "daily"
                    },
                    headers=headers
                )

                if response.status_code == 200:
                    raw = response.json()
                    prices_raw = raw.get("prices", [])
                    volumes_raw = raw.get("total_volumes", [])

                    if not prices_raw:
                        logger.warning(f"CoinGecko returned empty prices for {coin_id}")
                        return None

                    return {
                        "timestamps": [int(p[0]) for p in prices_raw],
                        "prices": [float(p[1]) for p in prices_raw],
                        "volumes": [float(v[1]) for v in volumes_raw] if volumes_raw else [0.0] * len(prices_raw),
                        "data_points": len(prices_raw),
                    }

                elif response.status_code == 429:
                    logger.warning(f"CoinGecko rate limited on {coin_id}. Waiting 60s...")
                    await asyncio.sleep(60)
                    # Retry once
                    response = await client.get(
                        f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart",
                        params={"vs_currency": "inr", "days": str(days), "interval": "daily"},
                        headers=headers
                    )
                    if response.status_code == 200:
                        raw = response.json()
                        prices_raw = raw.get("prices", [])
                        volumes_raw = raw.get("total_volumes", [])
                        if prices_raw:
                            return {
                                "timestamps": [int(p[0]) for p in prices_raw],
                                "prices": [float(p[1]) for p in prices_raw],
                                "volumes": [float(v[1]) for v in volumes_raw] if volumes_raw else [0.0] * len(prices_raw),
                                "data_points": len(prices_raw),
                            }
                    logger.error(f"CoinGecko retry also failed for {coin_id}: {response.status_code}")
                    return None
                else:
                    logger.warning(f"CoinGecko returned {response.status_code} for {coin_id}")
                    return None

        except Exception as e:
            logger.error(f"Error fetching {coin_id} from CoinGecko: {e}")
            return None

    async def _store(self, coin_id: str, days: int, data: Dict):
        """Store raw market data in MongoDB."""
        doc = {
            "coin_id": coin_id,
            "days": days,
            "timestamps": data["timestamps"],
            "prices": data["prices"],
            "volumes": data["volumes"],
            "data_points": data["data_points"],
            "fetched_at": datetime.now(timezone.utc),
        }
        await self.collection.update_one(
            {"coin_id": coin_id},
            {"$set": doc},
            upsert=True
        )


# ====================================================================
# STARTUP INTEGRATION
# ====================================================================
# Call this from server.py's startup event to pre-warm everything.
#
# Usage in server.py:
#
#   from data_preloader import DataPreloader, run_preload_and_backtest
#   from scoring_engine import ScoringEngine
#
#   preloader = DataPreloader(db)
#   scoring_engine = ScoringEngine(db)
#
#   @app.on_event("startup")
#   async def startup():
#       asyncio.create_task(run_preload_and_backtest(preloader, scoring_engine))
#
# ====================================================================

async def run_preload_and_backtest(preloader: 'DataPreloader', engine: 'ScoringEngine'):
    """Full startup sequence: fetch data, then run backtests.
    Runs as a background task so it doesn't block server startup."""
    try:
        logger.info("=== IndiaVest Data Preload Starting ===")

        # Step 1: Fetch raw data for all coins
        load_results = await preloader.load_all(days=365)
        loaded = sum(1 for v in load_results.values() if v == "loaded")
        cached = sum(1 for v in load_results.values() if v == "cached")
        failed = sum(1 for v in load_results.values() if v == "failed")
        logger.info(f"Raw data: {loaded} fetched, {cached} already cached, {failed} failed")

        # Step 2: Run backtests using cached data
        logger.info("Running regime backtests...")
        await engine.warm_cache()

        logger.info("=== IndiaVest Data Preload Complete ===")

    except Exception as e:
        logger.error(f"Preload failed: {e}")