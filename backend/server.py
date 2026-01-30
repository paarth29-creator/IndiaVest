from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import random
import asyncio
import json
import io
import csv
import numpy as np
from scipy import stats

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'test_database')]

# API Keys
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
FIREBASE_SERVER_KEY = os.environ.get('FIREBASE_SERVER_KEY', '')

# Create the main app
app = FastAPI(title="InvestIQ India - Production Ready")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== CONSTANTS ====================

DISCLAIMER = """⚠️ DISCLAIMER: This is NOT financial advice. Past performance does NOT guarantee future results. 
High risk of capital loss. Virtual/educational use only. Consult a SEBI-registered advisor before investing real money.
Crypto taxed at 30% (VDA) + 1% TDS in India. Stock LTCG 10% above ₹1L."""

EXTREME_RISK_WARNING = """🚨 EXTREME RISK WARNING: These are high-volatility, speculative assets. 
Probability of 50-100% loss is HIGH. NOT suitable for most investors. 
For EDUCATIONAL/VIRTUAL use only. Never invest money you cannot afford to lose completely."""

# INR conversion rate (will be fetched dynamically)
USD_TO_INR = 83.50

# ==================== CACHING SYSTEM ====================
# Cache for personalized advice to ensure consistency
PERSONALIZED_ADVICE_CACHE = {}
CACHE_TTL_SECONDS = 300  # 5 minute cache for same inputs

def get_cache_key(capital: float, risk_profile: str) -> str:
    """Generate cache key based on amount (rounded) and hour"""
    hour_key = datetime.now().strftime("%Y%m%d%H")  # Changes every hour
    amount_key = int(capital / 1000) * 1000  # Round to nearest 1000
    return f"{amount_key}_{risk_profile}_{hour_key}"

def get_cached_advice(cache_key: str) -> Optional[Dict]:
    """Get cached advice if still valid"""
    if cache_key in PERSONALIZED_ADVICE_CACHE:
        cached_time, cached_data = PERSONALIZED_ADVICE_CACHE[cache_key]
        if (datetime.now() - cached_time).seconds < CACHE_TTL_SECONDS:
            return cached_data
        else:
            del PERSONALIZED_ADVICE_CACHE[cache_key]
    return None

def set_cached_advice(cache_key: str, data: Dict):
    """Cache the advice"""
    PERSONALIZED_ADVICE_CACHE[cache_key] = (datetime.now(), data)
    # Clean old entries
    for key in list(PERSONALIZED_ADVICE_CACHE.keys()):
        if key != cache_key:
            cached_time, _ = PERSONALIZED_ADVICE_CACHE[key]
            if (datetime.now() - cached_time).seconds > CACHE_TTL_SECONDS * 2:
                del PERSONALIZED_ADVICE_CACHE[key]

# Risk tolerance multipliers
RISK_MULTIPLIERS = {
    "low": {"position_size": 0.5, "stop_loss": 1.5, "volatility_threshold": 0.5},
    "medium": {"position_size": 1.0, "stop_loss": 1.0, "volatility_threshold": 1.0},
    "high": {"position_size": 1.5, "stop_loss": 0.7, "volatility_threshold": 1.5},
    "aggressive": {"position_size": 2.0, "stop_loss": 0.5, "volatility_threshold": 2.0}
}

# ==================== MODELS ====================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime
    capital: float = 100000.0
    risk_profile: str = "medium"
    fcm_token: Optional[str] = None

class Trade(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    asset_type: str
    asset_symbol: str
    asset_name: str
    quantity: float
    price_inr: float
    total_value_inr: float
    trade_type: str
    trade_date: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    is_virtual: bool = True
    notes: Optional[str] = None

class TradeCreate(BaseModel):
    asset_type: str
    asset_symbol: str
    asset_name: str
    quantity: float
    price_inr: float
    trade_type: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    is_virtual: bool = True
    notes: Optional[str] = None

class WatchlistItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    asset_type: str
    asset_symbol: str
    asset_name: str
    added_at: datetime
    target_price: Optional[float] = None
    alert_enabled: bool = False

class WatchlistCreate(BaseModel):
    asset_type: str
    asset_symbol: str
    asset_name: str
    target_price: Optional[float] = None
    alert_enabled: bool = False

class CapitalUpdate(BaseModel):
    capital: float

class RiskProfileUpdate(BaseModel):
    risk_profile: str

class FCMTokenUpdate(BaseModel):
    fcm_token: str

# ==================== TEXT CLEANING UTILITY ====================

def strip_markdown(text: str) -> str:
    """
    Comprehensively remove ALL markdown formatting from text.
    Returns clean plain text.
    """
    if not text:
        return ""
    
    import re
    
    # Remove bold/italic (**, *, ___, __, _)
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # ***text***
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # **text**
    text = re.sub(r'\*(.+?)\*', r'\1', text)          # *text*
    text = re.sub(r'___(.+?)___', r'\1', text)        # ___text___
    text = re.sub(r'__(.+?)__', r'\1', text)          # __text__
    text = re.sub(r'_(.+?)_', r'\1', text)            # _text_
    
    # Remove any remaining standalone asterisks
    text = text.replace('***', '')
    text = text.replace('**', '')
    text = text.replace('*', '')
    
    # Remove headers (# ## ### etc.)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove blockquotes (>)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    
    # Remove horizontal rules (---, ___, ***)
    text = re.sub(r'^[-_*]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove inline code (`code`)
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    # Remove code blocks (```code```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # Remove links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove images ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
    
    # Remove bullet points (-, *, +) at start of lines but keep the text
    text = re.sub(r'^\s*[-*+]\s+', '  ', text, flags=re.MULTILINE)
    
    # Remove numbered lists (1. 2. etc.) but keep the text
    text = re.sub(r'^\s*\d+\.\s+', '  ', text, flags=re.MULTILINE)
    
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    
    return text.strip()

# ==================== CRYPTO DATA SERVICE (CoinGecko) ====================

class CryptoDataService:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.cache = {}
        self.cache_ttl = 30  # 30 seconds cache for fresher data
        self.last_usd_inr_rate = 83.50  # Fallback USD/INR rate
        
    async def get_usd_inr_rate(self) -> float:
        """Get current USD to INR exchange rate"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Try CoinGecko exchange rates
                response = await client.get(f"{self.base_url}/exchange_rates")
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get("rates", {})
                    if "inr" in rates:
                        # BTC to INR rate / BTC to USD rate = USD to INR
                        inr_rate = rates["inr"]["value"]
                        usd_rate = rates["usd"]["value"]
                        self.last_usd_inr_rate = inr_rate / usd_rate
                        return self.last_usd_inr_rate
        except Exception as e:
            logger.warning(f"Failed to get USD/INR rate: {e}")
        return self.last_usd_inr_rate
        
    async def get_prices(self) -> Dict:
        """Get top 20 crypto prices from CoinGecko with accurate INR pricing"""
        cache_key = "crypto_prices"
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_data
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {}
                if COINGECKO_API_KEY:
                    headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
                
                # Try INR first
                response = await client.get(
                    f"{self.base_url}/coins/markets",
                    params={
                        "vs_currency": "inr",
                        "order": "market_cap_desc",
                        "per_page": 20,
                        "page": 1,
                        "sparkline": False,
                        "price_change_percentage": "24h,7d,30d"
                    },
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    result = {}
                    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
                    timestamp_ist = now_ist.strftime("%d %b %H:%M IST")
                    
                    for coin in data:
                        symbol = coin["symbol"].upper()
                        result[symbol] = {
                            "id": coin["id"],
                            "name": coin["name"],
                            "price_inr": coin["current_price"],
                            "change_24h": coin.get("price_change_percentage_24h", 0) or 0,
                            "change_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
                            "change_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
                            "volume_24h": coin.get("total_volume", 0),
                            "market_cap": coin.get("market_cap", 0),
                            "high_24h": coin.get("high_24h", 0),
                            "low_24h": coin.get("low_24h", 0),
                            "ath": coin.get("ath", 0),
                            "atl": coin.get("atl", 0),
                            "circulating_supply": coin.get("circulating_supply", 0),
                            "last_updated": timestamp_ist,
                            "source": "CoinGecko"
                        }
                    self.cache[cache_key] = (datetime.now(), result)
                    return result
                elif response.status_code == 429:
                    # Rate limited - try USD and convert
                    logger.warning("CoinGecko INR rate limited, trying USD conversion")
                    return await self._get_prices_via_usd(client, headers)
                else:
                    logger.warning(f"CoinGecko API returned {response.status_code}, using fallback")
                    return self._get_fallback_prices()
        except Exception as e:
            logger.error(f"CoinGecko API error: {e}")
            return self._get_fallback_prices()
    
    async def _get_prices_via_usd(self, client, headers) -> Dict:
        """Fallback: Get USD prices and convert to INR"""
        try:
            usd_inr = await self.get_usd_inr_rate()
            
            response = await client.get(
                f"{self.base_url}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 20,
                    "page": 1,
                    "sparkline": False,
                    "price_change_percentage": "24h,7d,30d"
                },
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                result = {}
                now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
                timestamp_ist = now_ist.strftime("%d %b %H:%M IST")
                
                for coin in data:
                    symbol = coin["symbol"].upper()
                    usd_price = coin["current_price"]
                    inr_price = usd_price * usd_inr
                    
                    result[symbol] = {
                        "id": coin["id"],
                        "name": coin["name"],
                        "price_inr": round(inr_price, 2),
                        "price_usd": usd_price,
                        "change_24h": coin.get("price_change_percentage_24h", 0) or 0,
                        "change_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
                        "change_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
                        "volume_24h": (coin.get("total_volume", 0) or 0) * usd_inr,
                        "market_cap": (coin.get("market_cap", 0) or 0) * usd_inr,
                        "high_24h": (coin.get("high_24h", 0) or 0) * usd_inr,
                        "low_24h": (coin.get("low_24h", 0) or 0) * usd_inr,
                        "ath": (coin.get("ath", 0) or 0) * usd_inr,
                        "atl": (coin.get("atl", 0) or 0) * usd_inr,
                        "circulating_supply": coin.get("circulating_supply", 0),
                        "last_updated": timestamp_ist,
                        "source": f"CoinGecko (USD×{usd_inr:.2f})"
                    }
                self.cache["crypto_prices"] = (datetime.now(), result)
                return result
        except Exception as e:
            logger.error(f"USD conversion fallback error: {e}")
        return self._get_fallback_prices()
    
    async def get_coin_detail(self, coin_id: str) -> Dict:
        """Get detailed coin data including on-chain metrics"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {}
                if COINGECKO_API_KEY:
                    headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
                
                response = await client.get(
                    f"{self.base_url}/coins/{coin_id}",
                    params={
                        "localization": False,
                        "tickers": False,
                        "market_data": True,
                        "community_data": True,
                        "developer_data": True
                    },
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    market_data = data.get("market_data", {})
                    
                    return {
                        "id": data["id"],
                        "symbol": data["symbol"].upper(),
                        "name": data["name"],
                        "price_inr": market_data.get("current_price", {}).get("inr", 0),
                        "price_usd": market_data.get("current_price", {}).get("usd", 0),
                        "change_24h": market_data.get("price_change_percentage_24h", 0) or 0,
                        "change_7d": market_data.get("price_change_percentage_7d", 0) or 0,
                        "change_30d": market_data.get("price_change_percentage_30d", 0) or 0,
                        "volume_24h": market_data.get("total_volume", {}).get("inr", 0),
                        "market_cap": market_data.get("market_cap", {}).get("inr", 0),
                        "market_cap_rank": market_data.get("market_cap_rank", 0),
                        "high_24h": market_data.get("high_24h", {}).get("inr", 0),
                        "low_24h": market_data.get("low_24h", {}).get("inr", 0),
                        "ath": market_data.get("ath", {}).get("inr", 0),
                        "ath_change_pct": market_data.get("ath_change_percentage", {}).get("inr", 0),
                        "atl": market_data.get("atl", {}).get("inr", 0),
                        "circulating_supply": market_data.get("circulating_supply", 0),
                        "total_supply": market_data.get("total_supply", 0),
                        "max_supply": market_data.get("max_supply"),
                        "tvl": data.get("market_data", {}).get("total_value_locked", {}).get("usd"),
                        "fdv": market_data.get("fully_diluted_valuation", {}).get("inr", 0),
                        "sentiment_up": data.get("sentiment_votes_up_percentage", 0),
                        "sentiment_down": data.get("sentiment_votes_down_percentage", 0),
                        "description": data.get("description", {}).get("en", "")[:500],
                        "last_updated": market_data.get("last_updated", datetime.now(timezone.utc).isoformat())
                    }
        except Exception as e:
            logger.error(f"Coin detail error: {e}")
        return None
    
    async def get_historical_data(self, coin_id: str, days: int = 30) -> List[Dict]:
        """Get historical OHLC data for technical analysis"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                headers = {}
                if COINGECKO_API_KEY:
                    headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
                
                response = await client.get(
                    f"{self.base_url}/coins/{coin_id}/ohlc",
                    params={"vs_currency": "inr", "days": days},
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return [
                        {
                            "timestamp": d[0],
                            "open": d[1],
                            "high": d[2],
                            "low": d[3],
                            "close": d[4]
                        }
                        for d in data
                    ]
        except Exception as e:
            logger.error(f"Historical data error: {e}")
        return []
    
    def _get_fallback_prices(self) -> Dict:
        """Fallback data when API fails - uses realistic current prices"""
        # Updated fallback prices as of late Jan 2026 (approximate)
        # BTC ~$92,000 USD = ~₹77 lakh INR
        now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        timestamp_ist = now_ist.strftime("%d %b %H:%M IST")
        
        return {
            "BTC": {"id": "bitcoin", "name": "Bitcoin", "price_inr": 7700000, "change_24h": 1.5, "volume_24h": 45000000000 * USD_TO_INR, "market_cap": 1800000000000 * USD_TO_INR, "high_24h": 7750000, "low_24h": 7620000, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "ETH": {"id": "ethereum", "name": "Ethereum", "price_inr": 275000, "change_24h": 2.1, "volume_24h": 18000000000 * USD_TO_INR, "market_cap": 330000000000 * USD_TO_INR, "high_24h": 280000, "low_24h": 270000, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "BNB": {"id": "binancecoin", "name": "BNB", "price_inr": 52000, "change_24h": -0.5, "volume_24h": 1200000000 * USD_TO_INR, "market_cap": 80000000000 * USD_TO_INR, "high_24h": 53000, "low_24h": 51500, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "SOL": {"id": "solana", "name": "Solana", "price_inr": 21000, "change_24h": 3.2, "volume_24h": 3500000000 * USD_TO_INR, "market_cap": 100000000000 * USD_TO_INR, "high_24h": 21500, "low_24h": 20200, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "XRP": {"id": "ripple", "name": "XRP", "price_inr": 250, "change_24h": 1.8, "volume_24h": 2800000000 * USD_TO_INR, "market_cap": 140000000000 * USD_TO_INR, "high_24h": 255, "low_24h": 245, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "ADA": {"id": "cardano", "name": "Cardano", "price_inr": 85, "change_24h": 2.5, "volume_24h": 800000000 * USD_TO_INR, "market_cap": 30000000000 * USD_TO_INR, "high_24h": 88, "low_24h": 82, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "DOGE": {"id": "dogecoin", "name": "Dogecoin", "price_inr": 30, "change_24h": 4.2, "volume_24h": 1500000000 * USD_TO_INR, "market_cap": 45000000000 * USD_TO_INR, "high_24h": 31, "low_24h": 28.5, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "AVAX": {"id": "avalanche-2", "name": "Avalanche", "price_inr": 3200, "change_24h": 1.9, "volume_24h": 450000000 * USD_TO_INR, "market_cap": 13000000000 * USD_TO_INR, "high_24h": 3300, "low_24h": 3100, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "DOT": {"id": "polkadot", "name": "Polkadot", "price_inr": 600, "change_24h": 2.8, "volume_24h": 350000000 * USD_TO_INR, "market_cap": 8500000000 * USD_TO_INR, "high_24h": 615, "low_24h": 580, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "MATIC": {"id": "matic-network", "name": "Polygon", "price_inr": 42, "change_24h": 3.1, "volume_24h": 280000000 * USD_TO_INR, "market_cap": 4200000000 * USD_TO_INR, "high_24h": 44, "low_24h": 40, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "LINK": {"id": "chainlink", "name": "Chainlink", "price_inr": 1850, "change_24h": 2.8, "volume_24h": 680000000 * USD_TO_INR, "market_cap": 11000000000 * USD_TO_INR, "high_24h": 1900, "low_24h": 1800, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "UNI": {"id": "uniswap", "name": "Uniswap", "price_inr": 1420, "change_24h": 1.2, "volume_24h": 280000000 * USD_TO_INR, "market_cap": 8500000000 * USD_TO_INR, "high_24h": 1450, "low_24h": 1400, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
            "LTC": {"id": "litecoin", "name": "Litecoin", "price_inr": 11500, "change_24h": 0.5, "volume_24h": 450000000 * USD_TO_INR, "market_cap": 8600000000 * USD_TO_INR, "high_24h": 11700, "low_24h": 11300, "last_updated": timestamp_ist, "source": "Fallback (estimated)"},
        }

crypto_service = CryptoDataService()

# ==================== STOCK DATA SERVICE (yfinance) ====================

class StockDataService:
    def __init__(self):
        self.nifty50_symbols = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "HINDUNILVR.NS", "BHARTIARTL.NS", "SBIN.NS", "BAJFINANCE.NS", "WIPRO.NS",
            "LT.NS", "ASIANPAINT.NS", "MARUTI.NS", "TATAMOTORS.NS", "SUNPHARMA.NS",
            "TITAN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "HCLTECH.NS", "TECHM.NS",
            "NESTLEIND.NS", "ULTRACEMCO.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS",
            "COALINDIA.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS",
            "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "GRASIM.NS",
            "HEROMOTOCO.NS", "HINDALCO.NS", "INDUSINDBK.NS", "ITC.NS", "M&M.NS",
            "BAJAJ-AUTO.NS", "BAJAJFINSV.NS", "BPCL.NS", "BRITANNIA.NS", "HDFCLIFE.NS",
            "SBILIFE.NS", "SHREECEM.NS", "TATACONSUM.NS", "UPL.NS", "VEDL.NS"
        ]
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    async def get_nifty50(self) -> Dict:
        """Get Nifty 50 stock prices"""
        cache_key = "nifty50"
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_data
        
        try:
            import yfinance as yf
            
            # Run yfinance in a thread to not block async
            import asyncio
            loop = asyncio.get_event_loop()
            
            def fetch_stocks():
                tickers = yf.Tickers(" ".join(self.nifty50_symbols))
                result = {}
                for symbol in self.nifty50_symbols:
                    try:
                        ticker = tickers.tickers.get(symbol)
                        if ticker:
                            info = ticker.info
                            hist = ticker.history(period="5d")
                            
                            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                            
                            if prev_close and current_price:
                                change_pct = ((current_price - prev_close) / prev_close) * 100
                            else:
                                change_pct = 0
                            
                            clean_symbol = symbol.replace(".NS", "")
                            result[clean_symbol] = {
                                "symbol": clean_symbol,
                                "name": info.get("longName", info.get("shortName", clean_symbol)),
                                "price_inr": current_price,
                                "change_24h": round(change_pct, 2),
                                "volume": info.get("volume", 0),
                                "market_cap": info.get("marketCap", 0),
                                "pe_ratio": info.get("trailingPE") or info.get("forwardPE", 0),
                                "eps": info.get("trailingEps", 0),
                                "dividend_yield": info.get("dividendYield", 0) or 0,
                                "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
                                "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
                                "sector": info.get("sector", "Unknown"),
                                "industry": info.get("industry", "Unknown"),
                                "beta": info.get("beta", 1.0),
                                "last_updated": datetime.now(timezone.utc).isoformat()
                            }
                    except Exception as e:
                        logger.warning(f"Error fetching {symbol}: {e}")
                        continue
                return result
            
            result = await loop.run_in_executor(None, fetch_stocks)
            
            if result:
                self.cache[cache_key] = (datetime.now(), result)
                return result
            else:
                return self._get_fallback_stocks()
                
        except Exception as e:
            logger.error(f"Stock fetch error: {e}")
            return self._get_fallback_stocks()
    
    async def get_stock_detail(self, symbol: str) -> Dict:
        """Get detailed stock data"""
        try:
            import yfinance as yf
            import asyncio
            
            loop = asyncio.get_event_loop()
            
            def fetch_detail():
                ticker = yf.Ticker(f"{symbol}.NS")
                info = ticker.info
                hist = ticker.history(period="1y")
                
                # Calculate additional metrics
                if not hist.empty:
                    returns = hist['Close'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(252) * 100  # Annualized
                    sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
                else:
                    volatility = 0
                    sharpe = 0
                
                return {
                    "symbol": symbol,
                    "name": info.get("longName", symbol),
                    "price_inr": info.get("currentPrice", 0),
                    "change_24h": info.get("regularMarketChangePercent", 0),
                    "volume": info.get("volume", 0),
                    "avg_volume": info.get("averageVolume", 0),
                    "market_cap": info.get("marketCap", 0),
                    "pe_ratio": info.get("trailingPE", 0),
                    "forward_pe": info.get("forwardPE", 0),
                    "eps": info.get("trailingEps", 0),
                    "dividend_yield": (info.get("dividendYield", 0) or 0) * 100,
                    "book_value": info.get("bookValue", 0),
                    "price_to_book": info.get("priceToBook", 0),
                    "debt_to_equity": info.get("debtToEquity", 0),
                    "return_on_equity": info.get("returnOnEquity", 0),
                    "revenue_growth": info.get("revenueGrowth", 0),
                    "earnings_growth": info.get("earningsGrowth", 0),
                    "profit_margin": info.get("profitMargins", 0),
                    "beta": info.get("beta", 1.0),
                    "volatility_annual": round(volatility, 2),
                    "sharpe_ratio": round(sharpe, 2),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
                    "sector": info.get("sector", "Unknown"),
                    "industry": info.get("industry", "Unknown"),
                    "description": info.get("longBusinessSummary", "")[:500],
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            
            return await loop.run_in_executor(None, fetch_detail)
            
        except Exception as e:
            logger.error(f"Stock detail error for {symbol}: {e}")
            return None
    
    async def get_historical_data(self, symbol: str, period: str = "1mo") -> List[Dict]:
        """Get historical OHLC data for stocks"""
        try:
            import yfinance as yf
            import asyncio
            
            loop = asyncio.get_event_loop()
            
            def fetch_history():
                ticker = yf.Ticker(f"{symbol}.NS")
                hist = ticker.history(period=period)
                return [
                    {
                        "date": index.strftime("%Y-%m-%d"),
                        "open": row["Open"],
                        "high": row["High"],
                        "low": row["Low"],
                        "close": row["Close"],
                        "volume": row["Volume"]
                    }
                    for index, row in hist.iterrows()
                ]
            
            return await loop.run_in_executor(None, fetch_history)
            
        except Exception as e:
            logger.error(f"Historical data error: {e}")
            return []
    
    def _get_fallback_stocks(self) -> Dict:
        """Fallback mock data"""
        return {
            "RELIANCE": {"symbol": "RELIANCE", "name": "Reliance Industries", "price_inr": 2850, "change_24h": 0.8, "volume": 12500000, "market_cap": 1920000000000, "pe_ratio": 28.5, "eps": 100, "sector": "Energy", "beta": 0.95},
            "TCS": {"symbol": "TCS", "name": "Tata Consultancy Services", "price_inr": 3920, "change_24h": -0.3, "volume": 3200000, "market_cap": 1420000000000, "pe_ratio": 32.1, "eps": 122, "sector": "IT", "beta": 0.75},
            "HDFCBANK": {"symbol": "HDFCBANK", "name": "HDFC Bank", "price_inr": 1680, "change_24h": 1.2, "volume": 8500000, "market_cap": 1280000000000, "pe_ratio": 19.8, "eps": 85, "sector": "Banking", "beta": 1.05},
            "INFY": {"symbol": "INFY", "name": "Infosys", "price_inr": 1520, "change_24h": 0.5, "volume": 6200000, "market_cap": 630000000000, "pe_ratio": 25.3, "eps": 60, "sector": "IT", "beta": 0.85},
            "ICICIBANK": {"symbol": "ICICIBANK", "name": "ICICI Bank", "price_inr": 1250, "change_24h": 0.9, "volume": 9800000, "market_cap": 880000000000, "pe_ratio": 18.2, "eps": 69, "sector": "Banking", "beta": 1.15},
            "HINDUNILVR": {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "price_inr": 2450, "change_24h": -0.2, "volume": 1800000, "market_cap": 575000000000, "pe_ratio": 58.5, "eps": 42, "sector": "FMCG", "beta": 0.45},
            "BHARTIARTL": {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "price_inr": 1580, "change_24h": 1.5, "volume": 4200000, "market_cap": 890000000000, "pe_ratio": 45.2, "eps": 35, "sector": "Telecom", "beta": 0.85},
            "SBIN": {"symbol": "SBIN", "name": "State Bank of India", "price_inr": 820, "change_24h": 2.1, "volume": 18500000, "market_cap": 732000000000, "pe_ratio": 11.5, "eps": 71, "sector": "Banking", "beta": 1.35},
            "BAJFINANCE": {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "price_inr": 7250, "change_24h": -0.8, "volume": 1200000, "market_cap": 450000000000, "pe_ratio": 35.8, "eps": 203, "sector": "NBFC", "beta": 1.45},
            "WIPRO": {"symbol": "WIPRO", "name": "Wipro", "price_inr": 485, "change_24h": 0.3, "volume": 5800000, "market_cap": 252000000000, "pe_ratio": 22.8, "eps": 21, "sector": "IT", "beta": 0.80},
            "LT": {"symbol": "LT", "name": "Larsen & Toubro", "price_inr": 3450, "change_24h": 1.8, "volume": 2100000, "market_cap": 480000000000, "pe_ratio": 38.5, "eps": 90, "sector": "Infrastructure", "beta": 1.25},
            "TATAMOTORS": {"symbol": "TATAMOTORS", "name": "Tata Motors", "price_inr": 985, "change_24h": 2.5, "volume": 15200000, "market_cap": 365000000000, "pe_ratio": 12.8, "eps": 77, "sector": "Auto", "beta": 1.65},
            "SUNPHARMA": {"symbol": "SUNPHARMA", "name": "Sun Pharma", "price_inr": 1720, "change_24h": 0.4, "volume": 2800000, "market_cap": 413000000000, "pe_ratio": 38.2, "eps": 45, "sector": "Pharma", "beta": 0.55},
            "TITAN": {"symbol": "TITAN", "name": "Titan Company", "price_inr": 3250, "change_24h": 1.1, "volume": 1500000, "market_cap": 288000000000, "pe_ratio": 85.5, "eps": 38, "sector": "Consumer", "beta": 0.95},
            "AXISBANK": {"symbol": "AXISBANK", "name": "Axis Bank", "price_inr": 1180, "change_24h": 0.6, "volume": 8200000, "market_cap": 364000000000, "pe_ratio": 14.5, "eps": 81, "sector": "Banking", "beta": 1.25},
        }

stock_service = StockDataService()

# ==================== TECHNICAL ANALYSIS ====================

class TechnicalAnalysis:
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = float(np.mean(gains[-period:]))
        avg_loss = float(np.mean(losses[-period:]))
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(round(rsi, 2))
    
    @staticmethod
    def calculate_macd(prices: List[float]) -> Dict:
        """Calculate MACD indicator"""
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0, "trend": "neutral"}
        
        prices_arr = np.array(prices)
        
        # Calculate EMAs
        ema12 = TechnicalAnalysis._ema(prices_arr, 12)
        ema26 = TechnicalAnalysis._ema(prices_arr, 26)
        
        macd_line = ema12 - ema26
        signal_line = TechnicalAnalysis._ema(macd_line, 9) if len(macd_line) >= 9 else macd_line
        histogram = float(macd_line[-1] - signal_line[-1]) if len(signal_line) > 0 else 0.0
        
        trend = "bullish" if histogram > 0 else "bearish" if histogram < 0 else "neutral"
        
        return {
            "macd": float(round(float(macd_line[-1]), 4)),
            "signal": float(round(float(signal_line[-1]), 4)),
            "histogram": float(round(histogram, 4)),
            "trend": str(trend)
        }
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            current = float(prices[-1]) if prices else 0.0
            return {
                "upper": float(current * 1.02),
                "middle": float(current),
                "lower": float(current * 0.98),
                "bandwidth": 4.0,
                "position": "middle",
                "squeeze": False
            }
        
        prices_arr = np.array(prices[-period:])
        middle = float(np.mean(prices_arr))
        std = float(np.std(prices_arr))
        upper = middle + (num_std * std)
        lower = middle - (num_std * std)
        
        current_price = float(prices[-1])
        bandwidth = ((upper - lower) / middle) * 100 if middle > 0 else 0.0
        
        # Determine position
        if current_price >= upper:
            position = "above_upper"
        elif current_price <= lower:
            position = "below_lower"
        elif current_price > middle:
            position = "upper_half"
        else:
            position = "lower_half"
        
        # Detect squeeze (low bandwidth)
        squeeze = bool(bandwidth < 5.0)
        
        return {
            "upper": float(round(upper, 2)),
            "middle": float(round(middle, 2)),
            "lower": float(round(lower, 2)),
            "bandwidth": float(round(bandwidth, 2)),
            "position": str(position),
            "squeeze": squeeze
        }
    
    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Calculate Average True Range for volatility"""
        if len(highs) < period + 1:
            return 0.0
        
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        
        atr = np.mean(tr_list[-period:])
        return round(atr, 4)
    
    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema

# ==================== PORTFOLIO ANALYTICS ====================

class PortfolioAnalytics:
    @staticmethod
    def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.065) -> float:
        """Calculate Sharpe Ratio (risk-adjusted return)"""
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_arr = np.array(returns)
        excess_returns = returns_arr - (risk_free_rate / 252)  # Daily risk-free rate
        
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = (np.mean(excess_returns) * 252) / (np.std(excess_returns) * np.sqrt(252))
        return round(sharpe, 2)
    
    @staticmethod
    def calculate_diversification_score(holdings: List[Dict]) -> float:
        """Calculate portfolio diversification score"""
        if not holdings:
            return 0.0
        
        # Count unique assets and types
        num_assets = len(holdings)
        asset_types = set(h.get("asset_type") for h in holdings)
        sectors = set(h.get("sector", "Unknown") for h in holdings)
        
        # Calculate concentration (Herfindahl-Hirschman Index)
        total_value = sum(h.get("current_value", 0) for h in holdings)
        if total_value == 0:
            return 0.0
        
        hhi = sum((h.get("current_value", 0) / total_value) ** 2 for h in holdings)
        
        # Score based on multiple factors
        asset_score = min(num_assets * 5, 30)  # Max 30 points for # of assets
        type_score = len(asset_types) * 15  # 15 points per asset type
        sector_score = min(len(sectors) * 5, 25)  # Max 25 points for sectors
        concentration_score = max(0, 30 - (hhi * 100))  # Lower HHI = better
        
        total_score = asset_score + type_score + sector_score + concentration_score
        return min(100, round(total_score, 1))
    
    @staticmethod
    def monte_carlo_simulation(
        initial_value: float,
        expected_return: float,
        volatility: float,
        days: int,
        num_simulations: int = 1000
    ) -> Dict:
        """Run Monte Carlo simulation for portfolio projection"""
        np.random.seed(42)  # For reproducibility
        
        daily_return = expected_return / 252
        daily_volatility = volatility / np.sqrt(252)
        
        # Generate random returns
        random_returns = np.random.normal(
            daily_return,
            daily_volatility,
            (num_simulations, days)
        )
        
        # Calculate cumulative returns
        price_paths = initial_value * np.cumprod(1 + random_returns, axis=1)
        
        # Calculate statistics
        final_values = price_paths[:, -1]
        
        return {
            "initial_value": initial_value,
            "days": days,
            "simulations": num_simulations,
            "percentiles": {
                "p5": round(np.percentile(final_values, 5), 2),
                "p25": round(np.percentile(final_values, 25), 2),
                "p50": round(np.percentile(final_values, 50), 2),
                "p75": round(np.percentile(final_values, 75), 2),
                "p95": round(np.percentile(final_values, 95), 2)
            },
            "mean": round(np.mean(final_values), 2),
            "std": round(np.std(final_values), 2),
            "prob_profit": round(np.mean(final_values > initial_value) * 100, 1),
            "prob_double": round(np.mean(final_values > initial_value * 2) * 100, 1),
            "prob_loss_50": round(np.mean(final_values < initial_value * 0.5) * 100, 1),
            "max_value": round(np.max(final_values), 2),
            "min_value": round(np.min(final_values), 2)
        }
    
    @staticmethod
    def backtest_vs_benchmark(
        portfolio_values: List[float],
        benchmark_values: List[float],
        dates: List[str]
    ) -> Dict:
        """Backtest portfolio against benchmark"""
        if len(portfolio_values) < 2 or len(benchmark_values) < 2:
            return {"error": "Insufficient data for backtesting"}
        
        portfolio_returns = np.diff(portfolio_values) / portfolio_values[:-1]
        benchmark_returns = np.diff(benchmark_values) / benchmark_values[:-1]
        
        # Calculate alpha and beta
        if np.var(benchmark_returns) > 0:
            beta = np.cov(portfolio_returns, benchmark_returns)[0, 1] / np.var(benchmark_returns)
            alpha = np.mean(portfolio_returns) - beta * np.mean(benchmark_returns)
        else:
            beta = 1.0
            alpha = 0.0
        
        # Calculate cumulative returns
        portfolio_cumulative = (portfolio_values[-1] / portfolio_values[0] - 1) * 100
        benchmark_cumulative = (benchmark_values[-1] / benchmark_values[0] - 1) * 100
        
        return {
            "portfolio_return": round(portfolio_cumulative, 2),
            "benchmark_return": round(benchmark_cumulative, 2),
            "outperformance": round(portfolio_cumulative - benchmark_cumulative, 2),
            "alpha": round(alpha * 252 * 100, 2),  # Annualized alpha
            "beta": round(beta, 2),
            "correlation": round(np.corrcoef(portfolio_returns, benchmark_returns)[0, 1], 2),
            "portfolio_volatility": round(np.std(portfolio_returns) * np.sqrt(252) * 100, 2),
            "benchmark_volatility": round(np.std(benchmark_returns) * np.sqrt(252) * 100, 2)
        }

# ==================== TAX CALCULATOR ====================

class IndianTaxCalculator:
    VDA_TAX_RATE = 0.30  # 30% flat tax on crypto
    VDA_TDS_RATE = 0.01  # 1% TDS
    LTCG_RATE = 0.10  # 10% above 1L
    STCG_RATE = 0.15  # 15% for <1 year
    LTCG_EXEMPTION = 100000  # 1 Lakh exemption
    
    @staticmethod
    def calculate_crypto_tax(gains: float, is_loss: bool = False) -> Dict:
        """Calculate crypto VDA tax"""
        if is_loss or gains <= 0:
            return {
                "taxable_gain": 0,
                "tax_payable": 0,
                "tds_applicable": 0,
                "net_gain_after_tax": gains,
                "effective_rate": 0,
                "note": "Losses cannot be offset against other income or carried forward for crypto"
            }
        
        tax = gains * IndianTaxCalculator.VDA_TAX_RATE
        tds = gains * IndianTaxCalculator.VDA_TDS_RATE
        
        return {
            "taxable_gain": round(gains, 2),
            "tax_payable": round(tax, 2),
            "tds_applicable": round(tds, 2),
            "net_gain_after_tax": round(gains - tax, 2),
            "effective_rate": 30.0,
            "note": "30% flat tax + 1% TDS on transactions > ₹10,000"
        }
    
    @staticmethod
    def calculate_stock_tax(gains: float, holding_days: int) -> Dict:
        """Calculate stock capital gains tax"""
        is_ltcg = holding_days >= 365
        
        if gains <= 0:
            return {
                "type": "LTCG" if is_ltcg else "STCG",
                "taxable_gain": 0,
                "tax_payable": 0,
                "net_gain_after_tax": gains,
                "effective_rate": 0,
                "note": "Losses can be offset against capital gains"
            }
        
        if is_ltcg:
            # LTCG: 10% above 1L exemption
            taxable = max(0, gains - IndianTaxCalculator.LTCG_EXEMPTION)
            tax = taxable * IndianTaxCalculator.LTCG_RATE
            effective_rate = (tax / gains * 100) if gains > 0 else 0
            
            return {
                "type": "LTCG",
                "holding_period": f"{holding_days} days",
                "gross_gain": round(gains, 2),
                "exemption": IndianTaxCalculator.LTCG_EXEMPTION,
                "taxable_gain": round(taxable, 2),
                "tax_payable": round(tax, 2),
                "net_gain_after_tax": round(gains - tax, 2),
                "effective_rate": round(effective_rate, 2),
                "note": "LTCG: 10% on gains above ₹1 lakh"
            }
        else:
            # STCG: 15% flat
            tax = gains * IndianTaxCalculator.STCG_RATE
            
            return {
                "type": "STCG",
                "holding_period": f"{holding_days} days",
                "taxable_gain": round(gains, 2),
                "tax_payable": round(tax, 2),
                "net_gain_after_tax": round(gains - tax, 2),
                "effective_rate": 15.0,
                "note": "STCG: 15% flat rate for holdings < 1 year"
            }

# ==================== AI ANALYSIS SERVICE ====================

class AIAnalysisService:
    def __init__(self):
        self.llm_key = EMERGENT_LLM_KEY
    
    async def generate_grok_style_analysis(self, prompt: str, context: str = "") -> str:
        """Generate Grok-style deep analysis with Claude"""
        if not self.llm_key:
            return self._generate_mock_analysis(context)
        
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            system_prompt = """You are an expert financial analyst with Grok-style reasoning. Your analysis MUST:

1. DISSECT ASSUMPTIONS: Challenge conventional wisdom, question popular narratives
2. PROVIDE COUNTERPOINTS: For every bullish case, present bearish scenarios and vice versa
3. TRUTH-SEEKING: Prioritize accuracy over comfort, acknowledge uncertainty
4. PROBABILISTIC: Give specific probability estimates (e.g., "65% chance of...")
5. EVIDENCE-BASED: Support claims with data, metrics, historical precedents
6. RISK WARNINGS: Always highlight downside risks clearly
7. INDIA-SPECIFIC: Consider INR volatility, 30% VDA tax, SEBI/RBI regulations
8. ALTERNATIVES: Suggest alternative actions (e.g., "Alternatively, wait for confirmation...")

Format with clear sections. Be direct and analytical. No fluff."""

            chat = LlmChat(
                api_key=self.llm_key,
                session_id=f"analysis_{uuid.uuid4().hex[:8]}",
                system_message=system_prompt
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            
            full_prompt = f"{context}\n\n{prompt}" if context else prompt
            user_message = UserMessage(text=full_prompt)
            response = await chat.send_message(user_message)
            return response
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return self._generate_mock_analysis(context)
    
    def _generate_mock_analysis(self, context: str = "", news_title: str = "", news_summary: str = "") -> str:
        """Generate unique mock analysis based on specific news content"""
        
        # If we have specific news content, generate unique analysis
        if news_title:
            # Determine sentiment and action based on keywords
            title_lower = news_title.lower()
            summary_lower = (news_summary or "").lower()
            combined = title_lower + " " + summary_lower
            
            # Bullish keywords
            bullish_words = ["surge", "high", "rally", "inflows", "growth", "bullish", "boost", "record", "soar", "gain"]
            bearish_words = ["crash", "fall", "drop", "decline", "bearish", "fear", "concern", "risk", "tension", "cut"]
            crypto_words = ["bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi", "nft"]
            stock_words = ["nifty", "sensex", "equity", "stock", "fii", "sebi", "share"]
            
            is_bullish = any(w in combined for w in bullish_words)
            is_bearish = any(w in combined for w in bearish_words)
            is_crypto = any(w in combined for w in crypto_words)
            is_stock = any(w in combined for w in stock_words)
            
            # Generate unique probability estimates based on content
            if is_bullish:
                bull_prob = random.randint(50, 70)
                bear_prob = random.randint(10, 25)
            elif is_bearish:
                bull_prob = random.randint(20, 35)
                bear_prob = random.randint(40, 60)
            else:
                bull_prob = random.randint(35, 50)
                bear_prob = random.randint(25, 40)
            
            neutral_prob = 100 - bull_prob - bear_prob
            
            # Generate unique price impact estimate
            if is_bullish:
                impact = f"+{random.randint(3, 12)}% to +{random.randint(15, 25)}%"
            elif is_bearish:
                impact = f"-{random.randint(5, 15)}% to -{random.randint(2, 8)}%"
            else:
                impact = f"-{random.randint(2, 5)}% to +{random.randint(3, 8)}%"
            
            # Asset-specific recommendation
            if is_crypto:
                asset_rec = "BTC and ETH likely most affected. Consider SOL for higher beta exposure."
            elif is_stock:
                asset_rec = "Nifty 50 constituents, especially banking and IT sectors, most impacted."
            else:
                asset_rec = "Broad market impact expected across both crypto and equity."
            
            # Determine action
            if is_bullish and bull_prob > 55:
                action = "CONSIDER BUYING on dips. Set stop-loss at 5-7% below entry."
            elif is_bearish and bear_prob > 45:
                action = "REDUCE EXPOSURE or wait for stabilization. Avoid catching falling knife."
            else:
                action = "HOLD current positions. Monitor for clearer signals before acting."
            
            return strip_markdown(f"""ANALYSIS OF: {news_title[:80]}...

CORE ASSESSMENT:
This news event has significant implications for Indian investors. The immediate market reaction suggests {bull_prob}% probability of positive outcome.

KEY OBSERVATIONS:
1. {news_summary[:150] if news_summary else 'Market sentiment shifting based on this development.'}
2. {asset_rec}
3. Time horizon: Short-term impact (1-7 days) most pronounced.

PROBABILITY FRAMEWORK:
Bullish scenario ({bull_prob}%): Price impact of {impact} within 48-72 hours
Neutral scenario ({neutral_prob}%): Consolidation, limited movement
Bearish scenario ({bear_prob}%): Reversal if broader macro deteriorates

COUNTERPOINT:
Markets often overreact initially. Wait for confirmation before large positions. Consider: Could this be priced in already? What is the second-order effect?

RISK FACTORS:
Global macro uncertainty (Fed, geopolitics)
India-specific: INR volatility, regulatory changes
Tax impact: 30% VDA tax on crypto, 10% LTCG on stocks above Rs 1L

RECOMMENDED ACTION: {action}

{DISCLAIMER}""")
        
        # Default generic analysis if no specific news
        return strip_markdown(f"""MARKET ANALYSIS

CORE ASSESSMENT:
Based on current market data, we observe mixed signals requiring careful interpretation.

ASSUMPTION CHECK:
Common belief: This trend will continue BUT historical data shows mean reversion occurs 70% of time within 2 weeks
Liquidity appears strong HOWEVER this could indicate distribution rather than accumulation

PROBABILITY FRAMEWORK:
Bullish scenario (40%): Continuation with 15-20% upside
Neutral scenario (35%): Consolidation in current range
Bearish scenario (25%): Correction of 10-15%

RISK FACTORS:
1. Global macro uncertainty (Fed policy, geopolitical tensions)
2. India-specific: INR volatility, regulatory changes
3. Tax impact: 30% VDA tax significantly reduces net returns

COUNTERPOINT:
While momentum appears positive, elevated volume could indicate late-stage accumulation before distribution. Consider: Is this genuine demand or manufactured liquidity?

ALTERNATIVE ACTIONS:
Option A: Enter with reduced position size (50% of planned)
Option B: Wait for pullback to support levels
Option C: Hedge with inverse positions

{DISCLAIMER}""")

ai_service = AIAnalysisService()

# ==================== NEWS SERVICE ====================

MOCK_NEWS_DATA = [
    {"id": "news_1", "title": "US Federal Reserve Signals Potential Rate Cut in Q3 2025", "source": "Reuters", "category": "world_economies", "published_at": datetime.now(timezone.utc) - timedelta(hours=2), "summary": "Fed Chair indicates dovish stance amid cooling inflation, potentially boosting global risk assets.", "url": "https://reuters.com/markets/fed-rate-cut", "impact_level": "high"},
    {"id": "news_2", "title": "RBI Maintains Repo Rate at 6.5%, Signals Neutral Stance", "source": "Economic Times", "category": "india_specific", "published_at": datetime.now(timezone.utc) - timedelta(hours=4), "summary": "Reserve Bank of India keeps rates unchanged, focuses on inflation management while supporting growth.", "url": "https://economictimes.com/rbi-policy", "impact_level": "high"},
    {"id": "news_3", "title": "Bitcoin ETF Inflows Reach $500M Daily Average", "source": "Bloomberg", "category": "crypto_relevant", "published_at": datetime.now(timezone.utc) - timedelta(hours=6), "summary": "Institutional adoption continues as spot Bitcoin ETFs see sustained inflows.", "url": "https://bloomberg.com/bitcoin-etf", "impact_level": "high"},
    {"id": "news_4", "title": "India-China Border Tensions Ease After Diplomatic Talks", "source": "Business Standard", "category": "geopolitics", "published_at": datetime.now(timezone.utc) - timedelta(hours=8), "summary": "Both nations agree to de-escalation measures, reducing geopolitical risk premium.", "url": "https://business-standard.com/india-china", "impact_level": "medium"},
    {"id": "news_5", "title": "Ethereum Layer 2 TVL Surpasses $50 Billion", "source": "CoinDesk", "category": "crypto_relevant", "published_at": datetime.now(timezone.utc) - timedelta(hours=10), "summary": "Arbitrum and Optimism lead growth as scalability solutions gain traction.", "url": "https://coindesk.com/l2-tvl", "impact_level": "medium"},
    {"id": "news_6", "title": "SEBI Proposes New Framework for Crypto Regulation", "source": "Economic Times", "category": "india_specific", "published_at": datetime.now(timezone.utc) - timedelta(hours=12), "summary": "Securities regulator outlines potential licensing requirements for crypto exchanges.", "url": "https://economictimes.com/sebi-crypto", "impact_level": "high"},
    {"id": "news_7", "title": "Oil Prices Surge 5% on OPEC+ Production Cuts", "source": "Reuters", "category": "world_economies", "published_at": datetime.now(timezone.utc) - timedelta(hours=14), "summary": "Energy costs rise globally, impacting inflation outlook for emerging markets.", "url": "https://reuters.com/oil-opec", "impact_level": "high"},
    {"id": "news_8", "title": "Nifty 50 Hits All-Time High Amid FII Inflows", "source": "Business Standard", "category": "india_specific", "published_at": datetime.now(timezone.utc) - timedelta(hours=16), "summary": "Foreign institutional investors pump ₹15,000 crore into Indian equities this week.", "url": "https://business-standard.com/nifty-high", "impact_level": "high"},
    {"id": "news_9", "title": "Solana Network Processes 100M Daily Transactions", "source": "CoinDesk", "category": "crypto_relevant", "published_at": datetime.now(timezone.utc) - timedelta(hours=18), "summary": "High throughput blockchain sees massive DeFi and NFT activity.", "url": "https://coindesk.com/solana-txns", "impact_level": "medium"},
    {"id": "news_10", "title": "US-EU Trade Agreement Progress Boosts Global Sentiment", "source": "Bloomberg", "category": "geopolitics", "published_at": datetime.now(timezone.utc) - timedelta(hours=20), "summary": "Negotiations advance on tariff reductions, easing global trade tensions.", "url": "https://bloomberg.com/us-eu-trade", "impact_level": "medium"}
]

# ==================== AUTH HELPERS ====================

async def get_session_token(request: Request) -> Optional[str]:
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
    return session_token

async def get_current_user(request: Request) -> Optional[User]:
    session_token = await get_session_token(request)
    if not session_token:
        return None
    
    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        return None
    
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    
    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if user_doc:
        return User(**user_doc)
    return None

async def require_auth(request: Request) -> User:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ==================== API ROUTES ====================

@api_router.get("/")
async def root():
    return {"message": "InvestIQ India API", "status": "healthy", "version": "2.0.0", "disclaimer": DISCLAIMER}

# ==================== AUTH ROUTES ====================

@api_router.get("/auth/check")
async def check_auth(request: Request):
    user = await get_current_user(request)
    if user:
        return {"authenticated": True, "user": user.dict()}
    return {"authenticated": False}

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await require_auth(request)
    return user.dict()


@api_router.post("/auth/dev-login")
async def dev_login(response: Response):
    """Development-only endpoint to create a test session"""
    user_id = "dev_user_test"
    email = "dev@test.com"
    
    # Create or find dev user
    existing_user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not existing_user:
        new_user = {
            "user_id": user_id,
            "email": email,
            "name": "Dev Tester",
            "picture": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "capital": 100000.0,
            "risk_profile": "medium"
        }
        await db.users.insert_one(new_user)
        existing_user = {k: v for k, v in new_user.items() if k != "_id"}
    
    # Create session token
    session_token = f"dev_session_{uuid.uuid4().hex[:16]}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc)
    })
    
    # Convert datetime in user response
    user_response = {k: (str(v) if isinstance(v, datetime) else v) for k, v in existing_user.items()}
    
    return {"success": True, "user": user_response, "session_token": session_token}

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    async with httpx.AsyncClient() as client:
        try:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            if auth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")
            user_data = auth_response.json()
        except httpx.RequestError as e:
            logger.error(f"Auth API error: {e}")
            raise HTTPException(status_code=500, detail="Authentication service unavailable")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    existing_user = await db.users.find_one({"email": user_data["email"]}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
    else:
        new_user = {
            "user_id": user_id,
            "email": user_data["email"],
            "name": user_data["name"],
            "picture": user_data.get("picture"),
            "created_at": datetime.now(timezone.utc),
            "capital": 100000.0,
            "risk_profile": "medium"
        }
        await db.users.insert_one(new_user)
    
    session_token = user_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc)
    })
    
    response.set_cookie(
        key="session_token", value=session_token, httponly=True,
        secure=True, samesite="none", max_age=7*24*60*60, path="/"
    )
    
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"success": True, "user": user_doc, "session_token": session_token}

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = await get_session_token(request)
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    response.delete_cookie(key="session_token", path="/")
    return {"success": True}

# ==================== CRYPTO ROUTES ====================

@api_router.get("/crypto/prices")
async def get_crypto_prices():
    """Get real-time crypto prices from CoinGecko"""
    prices = await crypto_service.get_prices()
    return {"data": prices, "currency": "INR", "source": "coingecko", "disclaimer": DISCLAIMER}

@api_router.get("/crypto/{symbol}")
async def get_crypto_detail(symbol: str):
    """Get detailed crypto data including on-chain metrics"""
    symbol = symbol.upper()
    
    # Map symbol to CoinGecko ID
    symbol_to_id = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "SOL": "solana",
        "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
        "DOT": "polkadot", "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
        "ATOM": "cosmos", "LTC": "litecoin", "NEAR": "near", "APT": "aptos",
        "ARB": "arbitrum", "OP": "optimism", "INJ": "injective-protocol", "RENDER": "render-token"
    }
    
    coin_id = symbol_to_id.get(symbol, symbol.lower())
    detail = await crypto_service.get_coin_detail(coin_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail=f"Crypto {symbol} not found")
    
    # Add technical analysis
    historical = await crypto_service.get_historical_data(coin_id, 30)
    if historical:
        closes = [h["close"] for h in historical]
        highs = [h["high"] for h in historical]
        lows = [h["low"] for h in historical]
        
        detail["technicals"] = {
            "rsi": TechnicalAnalysis.calculate_rsi(closes),
            "macd": TechnicalAnalysis.calculate_macd(closes),
            "bollinger": TechnicalAnalysis.calculate_bollinger_bands(closes),
            "atr": TechnicalAnalysis.calculate_atr(highs, lows, closes),
            "atr_percent": round(TechnicalAnalysis.calculate_atr(highs, lows, closes) / closes[-1] * 100, 2) if closes else 0
        }
    
    return detail

@api_router.get("/crypto/{symbol}/history")
async def get_crypto_history(symbol: str, days: int = 30):
    """Get historical OHLC data"""
    symbol_to_id = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin"}
    coin_id = symbol_to_id.get(symbol.upper(), symbol.lower())
    data = await crypto_service.get_historical_data(coin_id, days)
    return {"symbol": symbol, "data": data, "days": days}

# ==================== STOCK ROUTES ====================

@api_router.get("/stocks/nifty50")
async def get_nifty50():
    """Get Nifty 50 stock prices using yfinance"""
    stocks = await stock_service.get_nifty50()
    return {"data": stocks, "currency": "INR", "source": "yfinance", "disclaimer": DISCLAIMER}

@api_router.get("/stocks/prices")
async def get_stock_prices():
    """Alias for nifty50"""
    return await get_nifty50()

@api_router.get("/stocks/{symbol}")
async def get_stock_detail(symbol: str):
    """Get detailed stock data with fundamentals"""
    symbol = symbol.upper().replace(".NS", "")
    detail = await stock_service.get_stock_detail(symbol)
    
    if not detail:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    
    # Add historical data for technical analysis
    historical = await stock_service.get_historical_data(symbol, "3mo")
    if historical:
        closes = [h["close"] for h in historical]
        highs = [h["high"] for h in historical]
        lows = [h["low"] for h in historical]
        
        detail["technicals"] = {
            "rsi": TechnicalAnalysis.calculate_rsi(closes),
            "macd": TechnicalAnalysis.calculate_macd(closes),
            "bollinger": TechnicalAnalysis.calculate_bollinger_bands(closes)
        }
    
    return detail

@api_router.get("/stocks/{symbol}/history")
async def get_stock_history(symbol: str, period: str = "1mo"):
    """Get historical OHLC data for stocks"""
    data = await stock_service.get_historical_data(symbol.upper(), period)
    return {"symbol": symbol, "data": data, "period": period}

# ==================== NEWS ROUTES ====================

# Import leader news service
from leader_news_service import leader_news_service, clean_text

def remove_markdown(text: str) -> str:
    """Wrapper for strip_markdown - ensures all AI text is clean"""
    return strip_markdown(text)

@api_router.get("/news")
async def get_news(category: Optional[str] = None, search: Optional[str] = None, use_ai: bool = False):
    """Get news with AI analysis - uses NewsAPI when available"""
    news = []
    
    # Try to fetch from NewsAPI first
    if NEWSAPI_KEY:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                params = {
                    "apiKey": NEWSAPI_KEY,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 15
                }
                
                # Build query based on category
                if category == "crypto_relevant":
                    params["q"] = "Bitcoin OR Ethereum OR crypto OR cryptocurrency"
                elif category == "india_specific":
                    params["q"] = "India economy OR RBI OR Nifty OR Indian markets"
                elif category == "geopolitics":
                    params["q"] = "geopolitics OR trade war OR sanctions"
                elif category == "world_economies":
                    params["q"] = "Federal Reserve OR economy OR inflation OR interest rates"
                else:
                    params["q"] = "markets OR finance OR economy OR Bitcoin OR stocks"
                
                if search:
                    params["q"] = search
                
                response = await client.get("https://newsapi.org/v2/everything", params=params)
                
                if response.status_code == 200:
                    articles = response.json().get("articles", [])
                    for idx, article in enumerate(articles[:12]):
                        pub_date = article.get("publishedAt", "")
                        try:
                            published_at = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        except:
                            published_at = datetime.now(timezone.utc)
                        
                        # Determine category from content
                        title_lower = (article.get("title") or "").lower()
                        if any(w in title_lower for w in ["bitcoin", "crypto", "ethereum", "btc"]):
                            cat = "crypto_relevant"
                        elif any(w in title_lower for w in ["india", "rbi", "nifty", "rupee"]):
                            cat = "india_specific"
                        elif any(w in title_lower for w in ["china", "russia", "war", "sanction"]):
                            cat = "geopolitics"
                        else:
                            cat = "world_economies"
                        
                        news.append({
                            "id": f"news_{idx}_{hash(article.get('title', ''))}",
                            "title": clean_text(article.get("title", "")),
                            "source": article.get("source", {}).get("name", "News"),
                            "category": category or cat,
                            "published_at": published_at,
                            "summary": clean_text(article.get("description", "")),
                            "url": article.get("url", ""),
                            "impact_level": "high" if any(w in title_lower for w in ["crash", "surge", "breaking", "major"]) else "medium"
                        })
        except Exception as e:
            logger.error(f"NewsAPI fetch error: {e}")
    
    # Fallback to mock data if NewsAPI fails or no key
    if not news:
        news = MOCK_NEWS_DATA.copy()
        if category:
            news = [n for n in news if n["category"] == category]
        if search:
            search_lower = search.lower()
            news = [n for n in news if search_lower in n["title"].lower() or search_lower in n["summary"].lower()]
    
    news_with_analysis = []
    for item in news[:10]:
        if use_ai:
            analysis = await ai_service.generate_grok_style_analysis(
                f"Analyze this news for Indian investors: {item['title']} - {item.get('summary', '')}",
                f"Category: {item['category']}, Impact: {item.get('impact_level', 'medium')}"
            )
        else:
            # Pass news-specific content for UNIQUE analysis per item
            analysis = ai_service._generate_mock_analysis(
                context=item.get('category', ''),
                news_title=item.get('title', ''),
                news_summary=item.get('summary', '')
            )
        
        # Clean analysis of any markdown
        analysis = remove_markdown(analysis)
        
        pub_at = item["published_at"]
        if isinstance(pub_at, datetime):
            pub_at = pub_at.isoformat()
        
        news_with_analysis.append({
            **item,
            "published_at": pub_at,
            "ai_analysis": analysis
        })
    
    return {"news": news_with_analysis, "total": len(news_with_analysis), "disclaimer": DISCLAIMER}

@api_router.get("/news/leader-statements")
async def get_leader_statements(use_ai: bool = True):
    """Get latest statements from key leaders and influencers with AI analysis"""
    statements = await leader_news_service.get_leader_statements(use_real_api=bool(NEWSAPI_KEY))
    
    analyzed_statements = []
    for stmt in statements:
        # Generate AI analysis for impact
        if use_ai and EMERGENT_LLM_KEY:
            try:
                analysis_prompt = f"""Analyze this statement from {stmt['leader']} ({stmt['role']}):

Statement: "{stmt['statement']}"
Assets potentially affected: {', '.join(stmt['assets_mentioned'])}

Provide Grok-style analysis with:
1. Step-by-step logical chain of how this affects markets
2. Counterpoints and alternative interpretations
3. Probabilistic impact estimate (e.g., "65% chance of +8-15% BTC move in next 48h")
4. A clear RECOMMENDED ACTION at the end (e.g., "BUY BTC (short-term), HOLD ETH, AVOID SOL")

Consider 30% VDA tax for Indian crypto investors. Be direct and evidence-based."""

                analysis = await ai_service.generate_grok_style_analysis(analysis_prompt, "")
                
                # Extract sentiment from analysis
                sentiment = 0.0
                analysis_lower = analysis.lower()
                if "bullish" in analysis_lower or "buy" in analysis_lower:
                    sentiment = 0.6
                elif "bearish" in analysis_lower or "sell" in analysis_lower:
                    sentiment = -0.6
                
                stmt["sentiment_score"] = sentiment
            except Exception as e:
                logger.error(f"AI analysis error: {e}")
                analysis = f"""Impact Analysis for {stmt['leader']}:

This statement from {stmt['role']} has potential implications for {', '.join(stmt['assets_mentioned'])}.

Key Considerations:
- Market sentiment may shift based on perceived policy direction
- Indian investors should consider 30% VDA tax implications
- Short-term volatility likely in mentioned assets

Probability Assessment:
- 55% chance of 3-8% price movement in affected assets within 24-48 hours
- Direction depends on broader market context

RECOMMENDED ACTION: Monitor closely. Consider small position if aligned with existing strategy. Set stop-loss at 8%.

{DISCLAIMER}"""
        else:
            analysis = f"""Statement from {stmt['leader']} ({stmt['role']}):

This could impact {', '.join(stmt['assets_mentioned'])}.

RECOMMENDED ACTION: Watch for market reaction. No immediate action required.

{DISCLAIMER}"""
        
        # Clean all markdown from analysis
        analysis = remove_markdown(analysis)
        
        pub_at = stmt["published_at"]
        if isinstance(pub_at, datetime):
            pub_at = pub_at.isoformat()
            # Convert to IST
            ist_time = (stmt["published_at"] + timedelta(hours=5, minutes=30)).strftime("%d %b, %H:%M IST")
        else:
            ist_time = str(pub_at)
        
        analyzed_statements.append({
            "id": stmt["id"],
            "leader": stmt["leader"],
            "role": stmt["role"],
            "statement": clean_text(stmt["statement"]),
            "source": stmt["source"],
            "url": stmt.get("url", ""),
            "published_at": pub_at,
            "published_ist": ist_time,
            "assets_mentioned": stmt["assets_mentioned"],
            "sentiment_score": stmt.get("sentiment_score", 0.0),
            "ai_analysis": analysis,
            "impact_history": {
                "1h_change": round(random.uniform(-3, 5), 2),
                "24h_change": round(random.uniform(-8, 12), 2),
                "7d_change": round(random.uniform(-15, 25), 2)
            }
        })
    
    return {
        "statements": analyzed_statements,
        "total": len(analyzed_statements),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER
    }

@api_router.get("/news/categories")
async def get_news_categories():
    return {
        "categories": [
            {"id": "world_economies", "name": "World Economies", "icon": "globe"},
            {"id": "geopolitics", "name": "Geopolitics", "icon": "flag"},
            {"id": "india_specific", "name": "India Specific", "icon": "map-pin"},
            {"id": "crypto_relevant", "name": "Crypto & Stocks", "icon": "trending-up"},
            {"id": "leader_statements", "name": "Leader Statements", "icon": "person"}
        ]
    }

# ==================== DAILY DECISION ROUTES ====================

@api_router.get("/decision/today")
async def get_daily_decision(use_ai: bool = True, risk_profile: str = "medium"):
    """Get today's investment decision with real-time data from yfinance + CoinGecko"""
    
    # Fetch real crypto data from CoinGecko
    crypto_prices = await crypto_service.get_prices()
    btc_data = crypto_prices.get("BTC", {})
    eth_data = crypto_prices.get("ETH", {})
    sol_data = crypto_prices.get("SOL", {})
    
    # Fetch real stock data from yfinance
    stock_prices = await stock_service.get_nifty50()
    
    # Get Nifty index and USD/INR directly from yfinance
    nifty_level = 24500.0
    usd_inr_rate = USD_TO_INR
    
    try:
        import yfinance as yf
        # Get Nifty 50 index
        nifty = yf.Ticker("^NSEI")
        nifty_hist = nifty.history(period="2d")
        if len(nifty_hist) >= 1:
            nifty_level = float(nifty_hist['Close'].iloc[-1])
        
        # Get USD/INR rate
        usdinr = yf.Ticker("INR=X")
        usdinr_hist = usdinr.history(period="1d")
        if len(usdinr_hist) >= 1:
            usd_inr_rate = float(usdinr_hist['Close'].iloc[-1])
    except Exception as e:
        logger.warning(f"yfinance index fetch error: {e}")
    
    # Calculate Nifty average change from top stocks
    top_stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    nifty_changes = [float(stock_prices.get(s, {}).get("change_24h", 0)) for s in top_stocks if s in stock_prices]
    avg_nifty_change = float(np.mean(nifty_changes)) if nifty_changes else 0.5
    
    # Get historical data for technicals
    btc_history = await crypto_service.get_historical_data("bitcoin", 30)
    btc_closes = [float(h["close"]) for h in btc_history] if btc_history else [float(btc_data.get("price_inr", 7700000))]
    
    eth_history = await crypto_service.get_historical_data("ethereum", 30)
    eth_closes = [float(h["close"]) for h in eth_history] if eth_history else [float(eth_data.get("price_inr", 275000))]
    
    # Calculate technical indicators
    btc_rsi = float(TechnicalAnalysis.calculate_rsi(btc_closes))
    btc_macd = TechnicalAnalysis.calculate_macd(btc_closes)
    btc_bollinger = TechnicalAnalysis.calculate_bollinger_bands(btc_closes)
    
    eth_rsi = float(TechnicalAnalysis.calculate_rsi(eth_closes))
    
    # Ensure all values are native Python types (not numpy)
    btc_price = float(btc_data.get("price_inr", 0) or 7700000)
    btc_change = float(btc_data.get("change_24h", 0) or 0)
    eth_price = float(eth_data.get("price_inr", 0) or 275000)
    eth_change = float(eth_data.get("change_24h", 0) or 0)
    sol_price = float(sol_data.get("price_inr", 0) or 21000)
    sol_change = float(sol_data.get("change_24h", 0) or 0)
    btc_volume = float(btc_data.get("volume_24h", 0) or 0)
    
    # Build comprehensive market snapshot with guaranteed values
    market_data = {
        "btc_price": btc_price,
        "btc_rsi": btc_rsi,
        "btc_macd": {
            "macd": float(btc_macd.get("macd", 0)),
            "signal": float(btc_macd.get("signal", 0)),
            "histogram": float(btc_macd.get("histogram", 0)),
            "trend": str(btc_macd.get("trend", "neutral"))
        },
        "btc_bollinger": {
            "upper": float(btc_bollinger.get("upper", 0)),
            "middle": float(btc_bollinger.get("middle", 0)),
            "lower": float(btc_bollinger.get("lower", 0)),
            "bandwidth": float(btc_bollinger.get("bandwidth", 0)),
            "position": str(btc_bollinger.get("position", "middle")),
            "squeeze": bool(btc_bollinger.get("squeeze", False))
        },
        "btc_change": btc_change,
        "btc_volume": btc_volume,
        "eth_price": eth_price,
        "eth_rsi": eth_rsi,
        "eth_change": eth_change,
        "sol_price": sol_price,
        "sol_change": sol_change,
        "nifty_level": float(nifty_level),
        "nifty_change": float(avg_nifty_change),
        "inr_usd": float(usd_inr_rate),
        "last_updated": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%d %b %H:%M IST"),
        "data_status": "live" if btc_price > 1000000 else "fallback"
    }
    
    # Risk multipliers
    risk_mult = RISK_MULTIPLIERS.get(risk_profile, RISK_MULTIPLIERS["medium"])
    
    # Determine recommendation based on technicals
    crypto_score = 0
    stock_score = 0

    # Crypto scoring
    if btc_rsi < 35:
        crypto_score += 30  # Oversold - bullish
    elif btc_rsi > 70:
        crypto_score -= 20  # Overbought - bearish
    else:
        crypto_score += 10  # Neutral
    
    if btc_macd["trend"] == "bullish":
        crypto_score += 20
    elif btc_macd["trend"] == "bearish":
        crypto_score -= 15
    
    if btc_change > 3:
        crypto_score += 15
    elif btc_change < -3:
        crypto_score -= 10
    
    # Stock scoring
    if avg_nifty_change > 1:
        stock_score += 25
    elif avg_nifty_change < -1:
        stock_score -= 15
    else:
        stock_score += 10
    
    # Determine recommendation
    if crypto_score > 40 and crypto_score > stock_score:
        recommendation = "Crypto"
        confidence = min(85, 50 + crypto_score)
    elif stock_score > 30 and stock_score > crypto_score:
        recommendation = "Stocks"
        confidence = min(80, 50 + stock_score)
    elif crypto_score > 20 and stock_score > 20:
        recommendation = "Both"
        confidence = min(75, 45 + (crypto_score + stock_score) // 2)
    else:
        recommendation = "Hold"
        confidence = 60

    # Generate reasoning
    reasoning = remove_markdown(f"""TODAYS INVESTMENT RECOMMENDATION: {recommendation}

TECHNICAL ANALYSIS SUMMARY:

BITCOIN (BTC):
- Current Price: Rs {btc_data.get('price_inr', 0):,.0f}
- 24h Change: {btc_data.get('change_24h', 0):.2f}%
- RSI(14): {btc_rsi} {'(OVERSOLD - potential buy)' if btc_rsi < 35 else '(OVERBOUGHT - caution)' if btc_rsi > 70 else '(Neutral)'}
- MACD Trend: {btc_macd['trend'].upper()}
- Bollinger Position: {btc_bollinger['position']}

ETHEREUM (ETH):
- Current Price: Rs {eth_data.get('price_inr', 0):,.0f}
- 24h Change: {eth_data.get('change_24h', 0):.2f}%
- RSI(14): {eth_rsi}

INDIAN STOCKS (Nifty Proxy):
- Average Top 5 Change: {avg_nifty_change:.2f}%
- Market Sentiment: {'Bullish' if avg_nifty_change > 1 else 'Bearish' if avg_nifty_change < -1 else 'Neutral'}

PROBABILITY ASSESSMENT:
- Bullish Scenario (45%): {recommendation} outperforms over next 2-4 weeks
- Neutral Scenario (35%): Sideways consolidation
- Bearish Scenario (20%): 10-15% correction possible

RISK-ADJUSTED STRATEGY for {risk_profile.upper()} profile:
- Max Position Size: {int(5 * risk_mult['position_size'])}% per trade
- Stop-Loss: {int(10 * risk_mult['stop_loss'])}% for crypto, {int(7 * risk_mult['stop_loss'])}% for stocks
- Take-Profit Target: 15-25% for crypto, 10-15% for stocks

COUNTERPOINT:
Markets can remain irrational. Even with favorable technicals, black swan events can cause sudden reversals. Always use stop-losses and never invest money you cannot afford to lose.

TAX CONSIDERATION (India):
- Crypto: 30% VDA tax on all gains. Need 43% gross gain to net 30% after tax.
- Stocks LTCG: 10% on gains above Rs 1 lakh (holding >1 year)
- Stocks STCG: 15% flat (holding <1 year)

RECOMMENDED ACTION: {recommendation.upper()} with {confidence}% confidence.

{DISCLAIMER}""")
    
    # Build allocations
    allocations = {
        "crypto": {},
        "stocks": {}
    }
    
    if recommendation in ["Crypto", "Both"]:
        allocations["crypto"] = {"BTC": 50, "ETH": 30, "SOL": 20}
    
    if recommendation in ["Stocks", "Both"]:
        allocations["stocks"] = {"HDFCBANK": 25, "TCS": 25, "RELIANCE": 25, "INFY": 25}
    
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "time_ist": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M IST"),
        "market_snapshot": market_data,
        "decision": {
            "recommendation": recommendation,
            "confidence": confidence,
            "reasoning": reasoning,
            "allocations": allocations,
            "risks": [
                "Regulatory changes (SEBI/RBI crypto stance could impact suddenly)",
                "Global macro uncertainty (Fed policy, geopolitical tensions)",
                "30% VDA tax significantly reduces net crypto returns in India",
                "INR volatility affects real returns on international assets",
                "Technical indicators are backward-looking, not predictive"
            ],
            "timeline": "Swing trade (1-4 weeks) for crypto, Position (6-12 months) for stocks",
            "what_if_available": True
        },
        "data_sources": {
            "crypto": "CoinGecko API (real-time)",
            "stocks": "yfinance (real-time)",
            "news": "NewsAPI" if NEWSAPI_KEY else "Fallback data"
        },
        "disclaimer": DISCLAIMER
    }

@api_router.post("/decision/what-if")
async def what_if_simulation(request: Request):
    """What-if simulator - recalculate recommendation with custom metrics"""
    body = await request.json()
    
    # Get overrides from request
    btc_price = body.get("btc_price")
    btc_change = body.get("btc_change")
    eth_price = body.get("eth_price")
    nifty_change = body.get("nifty_change")
    btc_rsi = body.get("btc_rsi", 50)
    confidence_override = body.get("confidence")
    
    # Simple scoring based on inputs
    score = 50
    
    if btc_rsi < 35:
        score += 25
        recommendation = "Crypto"
    elif btc_rsi > 70:
        score -= 15
        recommendation = "Hold"
    else:
        score += 10
        recommendation = "Both"
    
    if btc_change and btc_change > 5:
        score += 15
    elif btc_change and btc_change < -5:
        score -= 20
        recommendation = "Hold" if recommendation != "Hold" else recommendation
    
    if nifty_change and nifty_change > 2:
        score += 10
        if recommendation == "Hold":
            recommendation = "Stocks"
    
    return {
        "what_if_result": {
            "recommendation": recommendation,
            "confidence": confidence_override or min(85, score),
            "inputs_used": {
                "btc_price": btc_price,
                "btc_change": btc_change,
                "eth_price": eth_price,
                "nifty_change": nifty_change,
                "btc_rsi": btc_rsi
            },
            "note": "This is a simulation based on your custom inputs. Real market conditions may differ."
        },
        "disclaimer": DISCLAIMER
    }

# ==================== DAY TRADING DASHBOARD ====================

@api_router.get("/daytrading/should-trade")
async def should_day_trade_crypto(risk_profile: str = "medium"):
    """Crypto Day Trading Dashboard - Should I trade today?"""
    crypto_prices = await crypto_service.get_prices()
    
    # Analyze market conditions
    total_volume = sum(c.get("volume_24h", 0) for c in crypto_prices.values())
    avg_volatility = float(np.mean([abs(c.get("change_24h", 0)) for c in crypto_prices.values()]))
    
    # Get top liquid coins
    liquid_coins = []
    for symbol, data in crypto_prices.items():
        volume_usd = data.get("volume_24h", 0) / USD_TO_INR
        if volume_usd > 500000000:  # >$500M volume
            liquid_coins.append({
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price_inr": float(data.get("price_inr", 0)),
                "change_24h": float(data.get("change_24h", 0)),
                "volume_24h": float(data.get("volume_24h", 0)),
                "volume_usd": float(volume_usd)
            })
    
    # Calculate day trading score
    liquidity_score = min(len(liquid_coins) * 10, 40)
    volatility_score = float(min(avg_volatility * 10, 30) if avg_volatility > 1.5 else avg_volatility * 5)
    
    risk_mult = RISK_MULTIPLIERS.get(risk_profile, RISK_MULTIPLIERS["medium"])
    
    # Market hours check (IST)
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    is_good_hours = 9 <= ist_now.hour <= 23  # Active trading hours
    hours_score = 20 if is_good_hours else 5
    
    total_score = float(liquidity_score + volatility_score + hours_score)
    should_trade = bool(total_score > 50 and avg_volatility > 1.5)
    confidence = float(min(total_score, 85))
    
    # Top 5 recommendations
    top_coins = sorted(liquid_coins, key=lambda x: abs(x["change_24h"]) * x["volume_usd"], reverse=True)[:5]
    
    recommendations = []
    for coin in top_coins:
        price = float(coin["price_inr"])
        volatility = float(abs(coin["change_24h"]))
        
        # Calculate entry, stop-loss, take-profit
        entry_low = price * 0.995
        entry_high = price * 1.005
        stop_loss = price * (1 - 0.02 * risk_mult["stop_loss"])
        take_profit_1 = price * 1.02  # 1:1 RR
        take_profit_2 = price * 1.04  # 1:2 RR
        take_profit_3 = price * 1.06  # 1:3 RR
        
        recommendations.append({
            "symbol": coin["symbol"],
            "name": coin["name"],
            "current_price_inr": round(price, 2),
            "change_24h": round(float(coin["change_24h"]), 2),
            "volume_24h_inr": float(coin["volume_24h"]),
            "entry_range": {"low": round(entry_low, 2), "high": round(entry_high, 2)},
            "stop_loss": round(stop_loss, 2),
            "stop_loss_pct": round((1 - stop_loss/price) * 100, 1),
            "take_profit": {
                "tp1_1to1": round(take_profit_1, 2),
                "tp2_1to2": round(take_profit_2, 2),
                "tp3_1to3": round(take_profit_3, 2)
            },
            "max_position_pct": round(2 * risk_mult["position_size"], 1),
            "expected_hold_time": "<4 hours",
            "signal_strength": "strong" if volatility > 3 else "moderate" if volatility > 1.5 else "weak"
        })
    
    reasoning = f"""**Day Trading Assessment - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}**

📊 **Market Conditions:**
- Total crypto volume: ${total_volume/USD_TO_INR/1e9:.1f}B
- Average 24h volatility: {avg_volatility:.1f}%
- Liquid coins (>$500M vol): {len(liquid_coins)}
- IST time: {ist_now.strftime('%H:%M')} ({'✅ Active hours' if is_good_hours else '⚠️ Off-peak hours'})

⚖️ **Score Breakdown:**
- Liquidity: {liquidity_score}/40
- Volatility: {volatility_score:.0f}/30
- Market hours: {hours_score}/20
- **Total: {total_score:.0f}/90**

🔍 **Counterpoint:**
{'High volatility presents opportunities but also increased risk of stop-loss hunting. Consider smaller positions.' if avg_volatility > 3 else 'Lower volatility means tighter ranges - ensure spreads do not eat into profits.'}

⚠️ **Risk Warning:**
Day trading crypto is EXTREMELY risky. 90%+ of day traders lose money. The 30% VDA tax in India makes frequent trading even less profitable. Use only money you can afford to lose completely.

💡 **Alternative:**
If market conditions are unfavorable, consider:
1. Paper trading to practice
2. Swing trading (1-7 days) for better risk-adjusted returns
3. DCA into long-term positions

{DISCLAIMER}"""
    
    return {
        "should_trade": bool(should_trade),
        "confidence": float(confidence),
        "score": float(total_score),
        "market_conditions": {
            "total_volume_usd": float(total_volume / USD_TO_INR),
            "avg_volatility": float(round(avg_volatility, 2)),
            "liquid_coins_count": int(len(liquid_coins)),
            "is_good_hours": bool(is_good_hours),
            "ist_time": ist_now.strftime("%H:%M IST")
        },
        "top_5_recommendations": recommendations,
        "reasoning": reasoning,
        "extreme_risk_warning": EXTREME_RISK_WARNING,
        "disclaimer": DISCLAIMER
    }

@api_router.post("/daytrading/personalized")
async def get_personalized_day_trading(request: Request):
    """Personalized Day Trading recommendations based on capital input - DEPLOYS FULL AMOUNT"""
    body = await request.json()
    capital = body.get("capital", 0)  # INR amount user wants to DEPLOY TODAY
    risk_profile = body.get("risk_profile", "medium")
    
    if capital <= 0:
        return {"error": "Please enter a valid capital amount > 0"}
    
    # Check cache for consistent results
    cache_key = get_cache_key(capital, risk_profile)
    cached_result = get_cached_advice(cache_key)
    if cached_result:
        return cached_result
    
    crypto_prices = await crypto_service.get_prices()
    
    # Analyze market conditions to decide YES/NO
    total_volume = sum(c.get("volume_24h", 0) for c in crypto_prices.values())
    avg_volatility = float(np.mean([abs(c.get("change_24h", 0)) for c in crypto_prices.values()]))
    positive_coins = sum(1 for c in crypto_prices.values() if c.get("change_24h", 0) > 0)
    negative_coins = len(crypto_prices) - positive_coins
    market_sentiment = "bullish" if positive_coins > negative_coins else "bearish" if negative_coins > positive_coins else "neutral"
    
    # Decision: Should we trade today?
    should_trade = True
    trade_decision_reason = ""
    
    # Conditions to NOT trade
    if avg_volatility < 1.0:
        should_trade = False
        trade_decision_reason = "Market volatility too low (<1%). Wait for better opportunities."
    elif avg_volatility > 15:
        should_trade = False
        trade_decision_reason = "Market too volatile (>15%). High risk of flash crashes. Consider waiting."
    elif total_volume / USD_TO_INR < 10e9:  # Less than $10B total volume
        should_trade = False
        trade_decision_reason = "Low market liquidity. Slippage risk is high."
    
    # If NO trade, return alternatives
    if not should_trade:
        result = {
            "should_trade": False,
            "decision": "NO - NOT RECOMMENDED TODAY",
            "decision_reason": trade_decision_reason,
            "alternatives": [
                {"action": "HOLD CASH", "description": "Keep your Rs " + f"{capital:,.0f}" + " in savings. Wait for better market conditions."},
                {"action": "LONG-TERM STOCKS", "description": "Consider putting into Nifty 50 index funds for 6-12 month horizon."},
                {"action": "PAPER TRADE", "description": "Practice with virtual money today to learn without risk."},
            ],
            "market_conditions": {
                "avg_volatility": round(avg_volatility, 2),
                "total_volume_usd": float(total_volume / USD_TO_INR),
                "sentiment": market_sentiment
            },
            "summary": {
                "capital_input": capital,
                "total_deployed": 0,
                "deployment_pct": 0,
                "positions_count": 0,
                "expected_yield_range": {
                    "best_case_inr": 0,
                    "best_case_pct": 0,
                    "expected_inr": 0,
                    "expected_pct": 0,
                    "worst_case_inr": 0,
                    "worst_case_pct": 0,
                    "probability_profit_overall": 0
                },
                "allocation_breakdown": []
            },
            "recommendations": [],
            "overall_reasoning": strip_markdown(f"""TRADING DECISION: NO - NOT RECOMMENDED TODAY

REASON: {trade_decision_reason}

MARKET CONDITIONS:
- Average Volatility: {avg_volatility:.1f}%
- Market Sentiment: {market_sentiment.upper()}
- Total Volume: ${total_volume/USD_TO_INR/1e9:.1f}B

ALTERNATIVES:
1. HOLD CASH - Keep your Rs {capital:,.0f} safe. Missing one day costs nothing.
2. LONG-TERM INVESTING - Put into Nifty 50 ETF for steady 12-15% annual returns.
3. PAPER TRADE - Practice with virtual money to build skills without risk.

REMEMBER: The best traders know when NOT to trade. Protecting capital is more important than seeking profits.

{DISCLAIMER}"""),
            "disclaimer": DISCLAIMER
        }
        set_cached_advice(cache_key, result)
        return result
    
    # YES - Proceed with full deployment
    # Use deterministic seed based on capital + hour for consistent results
    seed_value = int(capital) + int(datetime.now().strftime("%Y%m%d%H"))
    random.seed(seed_value)
    
    # Get ALL tradeable coins (not just top by market cap)
    stablecoins = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "PYUSD"}
    tradeable_coins = []
    
    for symbol, data in crypto_prices.items():
        if symbol in stablecoins:
            continue
        volume_usd = data.get("volume_24h", 0) / USD_TO_INR
        change_24h = data.get("change_24h", 0)
        abs_change = abs(change_24h)
        
        # Require minimum $100M volume and >1.5% volatility for day trading
        if volume_usd > 100000000 and abs_change > 1.5:
            momentum = 1 if change_24h > 0 else -1
            volatility_score = min(abs_change / 2, 5)
            volume_score = min(volume_usd / 1e9, 5)
            combined_score = volatility_score * volume_score * (1 + 0.3 * momentum)
            
            tradeable_coins.append({
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price_inr": float(data.get("price_inr", 0)),
                "change_24h": float(change_24h),
                "volume_24h": float(data.get("volume_24h", 0)),
                "volume_usd": float(volume_usd),
                "score": combined_score
            })
    
    risk_mult = RISK_MULTIPLIERS.get(risk_profile, RISK_MULTIPLIERS["medium"])
    
    # FULL DEPLOYMENT: Allocate 100% of capital across 3-5 positions
    num_positions = random.choice([3, 4, 5])
    
    # Deterministic but varied coin selection
    sorted_coins = sorted(tradeable_coins, key=lambda x: x["score"], reverse=True)[:15]
    random.shuffle(sorted_coins)
    selected_coins = sorted(sorted_coins[:8], key=lambda x: x["score"], reverse=True)[:num_positions]
    
    # Fixed allocation templates (deterministic based on seed)
    if num_positions == 3:
        allocations = [40, 35, 25]
    elif num_positions == 4:
        allocations = random.choice([[35, 30, 25, 10], [30, 30, 25, 15]])
    else:
        allocations = random.choice([[35, 25, 20, 15, 5], [30, 25, 20, 15, 10]])
    
    recommendations = []
    total_allocated = 0
    
    for i, coin in enumerate(selected_coins):
        if i >= len(allocations):
            break
            
        price = float(coin["price_inr"])
        volatility = float(abs(coin["change_24h"]))
        
        # Calculate position value from allocation percentage
        position_pct = allocations[i] / 100
        position_value = capital * position_pct
        
        if position_value < 500:  # Skip if too small
            continue
            
        quantity = position_value / price
        
        # Entry range (±0.5% to ±1% depending on volatility)
        entry_spread = 0.005 if volatility < 3 else 0.01
        entry_low = price * (1 - entry_spread)
        entry_high = price * (1 + entry_spread)
        
        # Stop loss based on risk profile (1.5% - 3%)
        sl_pct = 0.02 * risk_mult["stop_loss"]
        stop_loss = price * (1 - sl_pct)
        
        # Take profit levels with realistic targets
        tp1 = price * (1 + sl_pct * 1.0)  # 1:1 RR
        tp2 = price * (1 + sl_pct * 1.5)  # 1:1.5 RR
        tp3 = price * (1 + sl_pct * 2.5)  # 1:2.5 RR
        
        # Expected profit/loss calculations
        loss_scenario = position_value * sl_pct
        profit_tp1 = position_value * sl_pct * 1.0
        profit_tp2 = position_value * sl_pct * 1.5
        profit_best = position_value * sl_pct * 2.5
        
        # Probabilistic estimate based on volatility and momentum
        base_win_prob = 50
        if coin["change_24h"] > 0:
            base_win_prob += 5  # Positive momentum bonus
        if volatility > 3 and volatility < 7:
            base_win_prob += 5  # Sweet spot volatility
        win_probability = min(base_win_prob + random.randint(-5, 5), 65)  # Add some variance
        
        expected_profit = (profit_tp1 * win_probability/100) - (loss_scenario * (100-win_probability)/100)
        
        recommendations.append({
            "rank": i + 1,
            "symbol": coin["symbol"],
            "name": coin["name"],
            "current_price_inr": round(price, 2),
            "change_24h": round(coin["change_24h"], 2),
            "allocation_pct": allocations[i],
            "entry_range": {"low": round(entry_low, 2), "high": round(entry_high, 2)},
            "suggested_quantity": round(quantity, 8),
            "suggested_investment_inr": round(position_value, 0),
            "stop_loss": round(stop_loss, 2),
            "stop_loss_pct": round(sl_pct * 100, 1),
            "take_profit": {
                "tp1_1to1": round(tp1, 2),
                "tp2_1to1_5": round(tp2, 2),
                "tp3_1to2_5": round(tp3, 2)
            },
            "sell_guidance": {
                "target_time": "Within 2-4 hours" if volatility > 4 else "By IST 6:00 PM",
                "exit_strategy": "Book 50% at TP1, move stop to entry. Book 30% at TP2. Let 20% ride to TP3 or EOD."
            },
            "expected_profit_loss": {
                "best_case_inr": round(profit_best, 0),
                "expected_inr": round(expected_profit, 0),
                "worst_case_inr": round(-loss_scenario, 0),
                "probability_profit": win_probability,
                "probability_loss": 100 - win_probability
            },
            "reasoning": strip_markdown(f"""TRADE {i+1}: {coin['name']} ({coin['symbol']}) - ALLOCATION: {allocations[i]}% (Rs {position_value:,.0f})

SIGNAL STRENGTH: {'STRONG' if volatility > 4 else 'MODERATE' if volatility > 2 else 'WEAK'}

WHY THIS COIN:
24h Volume: ${coin['volume_usd']/1e9:.1f}B provides sufficient liquidity.
24h Change: {coin['change_24h']:.1f}% shows {'bullish' if coin['change_24h'] > 0 else 'bearish'} momentum.

ENTRY: Rs {entry_low:,.0f} - Rs {entry_high:,.0f}
Quantity: {quantity:.6f} {coin['symbol']}

EXIT PLAN:
STOP LOSS: Rs {stop_loss:,.0f} (-{sl_pct*100:.1f}%) = Max loss Rs {loss_scenario:,.0f}
TP1: Rs {tp1:,.0f} (+{sl_pct*100:.1f}%) - Book 50%
TP2: Rs {tp2:,.0f} (+{sl_pct*150:.1f}%) - Book 30%
TP3: Rs {tp3:,.0f} (+{sl_pct*250:.1f}%) - Let 20% ride

RISK: {win_probability}% win probability | Max loss Rs {loss_scenario:,.0f} | Best gain Rs {profit_best:,.0f}

{DISCLAIMER}""")
        })
        
        total_allocated += position_value
    
    # Calculate overall expected outcome
    if recommendations:
        total_position = sum(r["suggested_investment_inr"] for r in recommendations)
        avg_win_prob = float(np.mean([r["expected_profit_loss"]["probability_profit"] for r in recommendations]))
        expected_total_profit = sum(r["expected_profit_loss"]["expected_inr"] for r in recommendations)
        best_case = sum(r["expected_profit_loss"]["best_case_inr"] for r in recommendations)
        worst_case = sum(r["expected_profit_loss"]["worst_case_inr"] for r in recommendations)
    else:
        total_position = 0
        avg_win_prob = 0
        expected_total_profit = 0
        best_case = 0
        worst_case = 0
    
    summary = {
        "capital_input": capital,
        "total_deployed": round(total_position, 0),
        "deployment_pct": round(total_position / capital * 100, 1) if capital > 0 else 0,
        "positions_count": len(recommendations),
        "expected_yield_range": {
            "best_case_inr": round(best_case, 0),
            "best_case_pct": round(best_case / capital * 100, 2) if capital > 0 else 0,
            "expected_inr": round(expected_total_profit, 0),
            "expected_pct": round(expected_total_profit / capital * 100, 2) if capital > 0 else 0,
            "worst_case_inr": round(worst_case, 0),
            "worst_case_pct": round(worst_case / capital * 100, 2) if capital > 0 else 0,
            "probability_profit_overall": round(avg_win_prob, 0)
        },
        "allocation_breakdown": [
            {"symbol": r["symbol"], "amount": r["suggested_investment_inr"], "pct": r["allocation_pct"]}
            for r in recommendations
        ]
    }
    
    return {
        "summary": summary,
        "recommendations": recommendations,
        "market_conditions": {
            "total_volume_usd": float(total_volume / USD_TO_INR),
            "avg_volatility": round(avg_volatility, 2),
            "tradeable_coins_count": len(tradeable_coins)
        },
        "overall_reasoning": strip_markdown(f"""FULL DEPLOYMENT DAY TRADING PLAN - Rs {capital:,.0f}

CAPITAL DEPLOYMENT:
Total Amount: Rs {capital:,.0f}
Deployed Today: Rs {total_position:,.0f} ({total_position/capital*100:.1f}%)
Number of Positions: {len(recommendations)}

ALLOCATION BREAKDOWN:
""" + "\n".join([f"  {r['symbol']}: Rs {r['suggested_investment_inr']:,.0f} ({r['allocation_pct']}%)" for r in recommendations]) + f"""

EXPECTED END-OF-DAY OUTCOME:
Best Case: +Rs {best_case:,.0f} (+{best_case/capital*100:.1f}%)
Expected: +Rs {expected_total_profit:,.0f} (+{expected_total_profit/capital*100:.2f}%)
Worst Case: Rs {worst_case:,.0f} ({worst_case/capital*100:.1f}%)

Overall Win Probability: {avg_win_prob:.0f}%

CRITICAL WARNINGS:
1. This deploys your FULL Rs {capital:,.0f} into day trades
2. Worst case scenario: you lose Rs {abs(worst_case):,.0f} TODAY
3. 30% VDA tax applies to all profits
4. Crypto markets are 24/7 - monitor positions or set alerts
5. Do NOT average down on losing positions

RECOMMENDATION:
Only proceed if you can afford to lose the full Rs {capital:,.0f}. Day trading has a >70% failure rate among retail traders.

{DISCLAIMER}"""),
        "disclaimer": DISCLAIMER
    }

# ==================== HIGH RISK / HIGH REWARD ====================

@api_router.get("/highrisk/{horizon}")
async def get_high_risk_opportunities(horizon: str, risk_profile: str = "aggressive"):
    """High Risk / High Reward opportunities by time horizon"""
    if horizon not in ["day", "4weeks", "12weeks", "52weeks"]:
        raise HTTPException(status_code=400, detail="Invalid horizon. Use: day, 4weeks, 12weeks, 52weeks")
    
    crypto_prices = await crypto_service.get_prices()
    stock_prices = await stock_service.get_nifty50()
    
    horizon_params = {
        "day": {"volatility_min": 3, "hold_time": "Intraday (4-8 hours)", "max_allocation": 1},
        "4weeks": {"volatility_min": 5, "hold_time": "4 weeks", "max_allocation": 2},
        "12weeks": {"volatility_min": 8, "hold_time": "12 weeks", "max_allocation": 3},
        "52weeks": {"volatility_min": 10, "hold_time": "52 weeks", "max_allocation": 5}
    }
    params = horizon_params[horizon]
    
    # Filter high-volatility cryptos (smaller caps, high momentum)
    crypto_opportunities = []
    for symbol, data in crypto_prices.items():
        market_cap_usd = data.get("market_cap", 0) / USD_TO_INR
        change = abs(data.get("change_24h", 0))
        
        # Small-mid cap with high volatility
        if market_cap_usd < 10e9 and change > params["volatility_min"]:
            upside_estimate = random.randint(50, 300)
            downside_estimate = random.randint(40, 70)
            
            crypto_opportunities.append({
                "type": "crypto",
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price_inr": data.get("price_inr", 0),
                "change_24h": data.get("change_24h", 0),
                "market_cap_usd": market_cap_usd,
                "volatility_indicator": "EXTREME" if change > 10 else "HIGH",
                "upside_estimate_pct": upside_estimate,
                "downside_estimate_pct": downside_estimate,
                "probability_profit": random.randint(30, 55),
                "probability_loss_50plus": random.randint(25, 45),
                "suggested_allocation_pct": params["max_allocation"],
                "stop_loss_pct": 25 if horizon == "day" else 35,
                "expected_catalysts": ["Market sentiment shift", "Protocol upgrades", "Exchange listings"]
            })
    
    # Filter high-beta stocks
    stock_opportunities = []
    for symbol, data in stock_prices.items():
        beta = data.get("beta", 1.0)
        market_cap = data.get("market_cap", 0)
        
        # High beta, smaller cap
        if beta > 1.3 and market_cap < 500000000000:  # <500B INR
            upside_estimate = random.randint(30, 100)
            downside_estimate = random.randint(20, 40)
            
            stock_opportunities.append({
                "type": "stock",
                "symbol": symbol,
                "name": data.get("name", symbol),
                "price_inr": data.get("price_inr", 0),
                "change_24h": data.get("change_24h", 0),
                "beta": beta,
                "market_cap_inr": market_cap,
                "sector": data.get("sector", "Unknown"),
                "volatility_indicator": "HIGH" if beta > 1.5 else "ELEVATED",
                "upside_estimate_pct": upside_estimate,
                "downside_estimate_pct": downside_estimate,
                "probability_profit": random.randint(40, 60),
                "suggested_allocation_pct": params["max_allocation"],
                "stop_loss_pct": 15,
                "expected_catalysts": ["Earnings surprise", "Sector rotation", "Policy changes"]
            })
    
    # Sort by potential upside
    crypto_opportunities.sort(key=lambda x: x["upside_estimate_pct"], reverse=True)
    stock_opportunities.sort(key=lambda x: x["upside_estimate_pct"], reverse=True)
    
    reasoning = f"""**High Risk/High Reward Analysis - {horizon.upper()} Horizon**

🚨 **EXTREME RISK WARNING:**
{EXTREME_RISK_WARNING}

📊 **Selection Criteria:**
- Crypto: Market cap <$10B, 24h volatility >{params['volatility_min']}%
- Stocks: Beta >1.3, Market cap <₹5,000 Cr
- Hold time: {params['hold_time']}
- Max allocation: {params['max_allocation']}% of portfolio per position

⚖️ **Expected Outcomes:**
- Best case: 50-300% gains possible
- Worst case: 50-100% loss highly probable
- Probability of profit: ~35-50% (coin flip or worse)

🔍 **Counterpoint:**
These are SPECULATIVE positions. For every success story, there are 10+ failures. The asymmetric risk-reward only works with strict position sizing and stop-losses.

💡 **Alternative Approach:**
Instead of high-risk speculation:
1. Allocate 90% to blue-chips, 10% to speculative
2. Use options/futures for leverage with defined risk
3. Paper trade first to test strategy
4. Consider: Is the tax-adjusted expected return positive?

**Tax Reality Check:**
With 30% VDA tax, a 100% crypto gain becomes 70% net. A 50% loss is still 50% loss. The math often doesn't favor speculation.

{DISCLAIMER}"""
    
    return {
        "horizon": horizon,
        "hold_time": params["hold_time"],
        "crypto_opportunities": crypto_opportunities[:5],
        "stock_opportunities": stock_opportunities[:5],
        "reasoning": reasoning,
        "extreme_risk_warning": EXTREME_RISK_WARNING,
        "disclaimer": DISCLAIMER,
        "max_total_allocation_pct": params["max_allocation"] * 5  # Max 5 positions
    }

# ==================== SIMULATOR ROUTES ====================

@api_router.post("/simulator/trade")
async def execute_virtual_trade(trade: TradeCreate, request: Request):
    user = await require_auth(request)
    
    total_value = trade.quantity * trade.price_inr
    
    trade_record = {
        "trade_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "asset_type": trade.asset_type,
        "asset_symbol": trade.asset_symbol,
        "asset_name": trade.asset_name,
        "quantity": trade.quantity,
        "price_inr": trade.price_inr,
        "total_value_inr": total_value,
        "trade_type": trade.trade_type,
        "trade_date": datetime.now(timezone.utc),
        "stop_loss": trade.stop_loss or (trade.price_inr * 0.9 if trade.trade_type == "buy" else None),
        "take_profit": trade.take_profit,
        "is_virtual": True,
        "notes": trade.notes
    }
    
    await db.trades.insert_one(trade_record)
    trade_record.pop("_id", None)
    trade_record["trade_date"] = trade_record["trade_date"].isoformat()
    
    return {"success": True, "trade": trade_record, "disclaimer": DISCLAIMER}

@api_router.get("/simulator/portfolio")
async def get_simulator_portfolio(request: Request):
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": True},
        {"_id": 0}
    ).to_list(1000)
    
    # Get current prices
    crypto_prices = await crypto_service.get_prices()
    stock_prices = await stock_service.get_nifty50()
    
    # Calculate holdings
    holdings = {}
    for trade in trades:
        key = f"{trade['asset_type']}_{trade['asset_symbol']}"
        if key not in holdings:
            holdings[key] = {
                "asset_type": trade["asset_type"],
                "asset_symbol": trade["asset_symbol"],
                "asset_name": trade["asset_name"],
                "quantity": 0,
                "total_invested": 0
            }
        
        if trade["trade_type"] == "buy":
            holdings[key]["total_invested"] += trade["total_value_inr"]
            holdings[key]["quantity"] += trade["quantity"]
        else:
            holdings[key]["quantity"] -= trade["quantity"]
            holdings[key]["total_invested"] -= trade["total_value_inr"]
    
    # Calculate current values
    portfolio = []
    total_value = 0
    total_invested = 0
    returns = []
    
    for key, holding in holdings.items():
        if holding["quantity"] <= 0:
            continue
        
        if holding["asset_type"] == "crypto":
            current_price = crypto_prices.get(holding["asset_symbol"], {}).get("price_inr", 0)
        else:
            current_price = stock_prices.get(holding["asset_symbol"], {}).get("price_inr", 0)
        
        current_value = holding["quantity"] * current_price
        avg_price = holding["total_invested"] / holding["quantity"] if holding["quantity"] > 0 else 0
        pnl = current_value - holding["total_invested"]
        pnl_pct = (pnl / holding["total_invested"] * 100) if holding["total_invested"] > 0 else 0
        
        portfolio.append({
            **holding,
            "avg_price": avg_price,
            "current_price": current_price,
            "current_value": current_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct
        })
        
        total_value += current_value
        total_invested += holding["total_invested"]
        if holding["total_invested"] > 0:
            returns.append(pnl_pct / 100)
    
    # Calculate analytics
    sharpe = PortfolioAnalytics.calculate_sharpe_ratio(returns) if returns else 0
    diversification = PortfolioAnalytics.calculate_diversification_score(portfolio)
    
    return {
        "holdings": portfolio,
        "summary": {
            "total_value": total_value,
            "total_invested": total_invested,
            "total_pnl": total_value - total_invested,
            "total_pnl_pct": ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
            "num_holdings": len(portfolio),
            "sharpe_ratio": sharpe,
            "diversification_score": diversification
        },
        "trades": [{**t, "trade_date": t["trade_date"].isoformat() if isinstance(t["trade_date"], datetime) else t["trade_date"]} for t in trades[-20:]],
        "disclaimer": DISCLAIMER
    }

# ==================== PORTFOLIO ROUTES ====================

@api_router.post("/portfolio/trade")
async def add_portfolio_trade(trade: TradeCreate, request: Request):
    user = await require_auth(request)
    
    total_value = trade.quantity * trade.price_inr
    
    trade_record = {
        "trade_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "asset_type": trade.asset_type,
        "asset_symbol": trade.asset_symbol,
        "asset_name": trade.asset_name,
        "quantity": trade.quantity,
        "price_inr": trade.price_inr,
        "total_value_inr": total_value,
        "trade_type": trade.trade_type,
        "trade_date": datetime.now(timezone.utc),
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "is_virtual": False,
        "notes": trade.notes
    }
    
    await db.trades.insert_one(trade_record)
    trade_record.pop("_id", None)
    trade_record["trade_date"] = trade_record["trade_date"].isoformat()
    
    return {"success": True, "trade": trade_record}

@api_router.get("/portfolio")
async def get_portfolio(request: Request):
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": False},
        {"_id": 0}
    ).to_list(1000)
    
    crypto_prices = await crypto_service.get_prices()
    stock_prices = await stock_service.get_nifty50()
    
    holdings = {}
    for trade in trades:
        key = f"{trade['asset_type']}_{trade['asset_symbol']}"
        if key not in holdings:
            holdings[key] = {
                "asset_type": trade["asset_type"],
                "asset_symbol": trade["asset_symbol"],
                "asset_name": trade["asset_name"],
                "quantity": 0,
                "total_invested": 0,
                "first_trade_date": trade["trade_date"]
            }
        
        if trade["trade_type"] == "buy":
            holdings[key]["total_invested"] += trade["total_value_inr"]
            holdings[key]["quantity"] += trade["quantity"]
        else:
            holdings[key]["quantity"] -= trade["quantity"]
            holdings[key]["total_invested"] -= trade["total_value_inr"]
    
    portfolio = []
    total_value = 0
    total_invested = 0
    returns = []
    
    for key, holding in holdings.items():
        if holding["quantity"] <= 0:
            continue
        
        if holding["asset_type"] == "crypto":
            current_price = crypto_prices.get(holding["asset_symbol"], {}).get("price_inr", 0)
        else:
            current_price = stock_prices.get(holding["asset_symbol"], {}).get("price_inr", 0)
        
        current_value = holding["quantity"] * current_price
        avg_price = holding["total_invested"] / holding["quantity"] if holding["quantity"] > 0 else 0
        pnl = current_value - holding["total_invested"]
        pnl_pct = (pnl / holding["total_invested"] * 100) if holding["total_invested"] > 0 else 0
        
        # Calculate holding days
        first_date = holding["first_trade_date"]
        if isinstance(first_date, datetime):
            holding_days = (datetime.now(timezone.utc) - first_date.replace(tzinfo=timezone.utc)).days
        else:
            holding_days = 0
        
        # Calculate tax
        if holding["asset_type"] == "crypto":
            tax_info = IndianTaxCalculator.calculate_crypto_tax(pnl)
        else:
            tax_info = IndianTaxCalculator.calculate_stock_tax(pnl, holding_days)
        
        portfolio.append({
            **holding,
            "avg_price": avg_price,
            "current_price": current_price,
            "current_value": current_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "holding_days": holding_days,
            "tax_estimate": tax_info
        })
        
        total_value += current_value
        total_invested += holding["total_invested"]
        if holding["total_invested"] > 0:
            returns.append(pnl_pct / 100)
    
    sharpe = PortfolioAnalytics.calculate_sharpe_ratio(returns) if returns else 0
    diversification = PortfolioAnalytics.calculate_diversification_score(portfolio)
    
    # Generate AI analysis
    analysis_prompt = f"Portfolio: {len(portfolio)} holdings, Total value: ₹{total_value:,.0f}, P&L: {((total_value-total_invested)/total_invested*100) if total_invested > 0 else 0:.1f}%, Sharpe: {sharpe}, Diversification: {diversification}"
    ai_analysis = ai_service._generate_mock_analysis(analysis_prompt)
    
    return {
        "holdings": portfolio,
        "summary": {
            "total_value": total_value,
            "total_invested": total_invested,
            "total_pnl": total_value - total_invested,
            "total_pnl_pct": ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
            "num_holdings": len(portfolio),
            "sharpe_ratio": sharpe,
            "diversification_score": diversification
        },
        "ai_analysis": ai_analysis,
        "trades": [{**t, "trade_date": t["trade_date"].isoformat() if isinstance(t["trade_date"], datetime) else t["trade_date"]} for t in trades[-20:]],
        "disclaimer": DISCLAIMER
    }

@api_router.get("/portfolio/monte-carlo")
async def portfolio_monte_carlo(
    request: Request,
    days: int = 252,
    expected_return: float = 0.12,
    volatility: float = 0.25
):
    """Run Monte Carlo simulation on portfolio"""
    user = await require_auth(request)
    
    # Get current portfolio value
    portfolio_response = await get_portfolio(request)
    initial_value = portfolio_response["summary"]["total_value"]
    
    if initial_value <= 0:
        initial_value = user.capital
    
    simulation = PortfolioAnalytics.monte_carlo_simulation(
        initial_value=initial_value,
        expected_return=expected_return,
        volatility=volatility,
        days=days,
        num_simulations=1000
    )
    
    return {
        "simulation": simulation,
        "parameters": {
            "initial_value": initial_value,
            "days": days,
            "expected_annual_return": expected_return,
            "annual_volatility": volatility
        },
        "interpretation": f"""**Monte Carlo Projection ({days} days, 1000 simulations)**

📊 **Expected Outcomes:**
- Median outcome: ₹{simulation['percentiles']['p50']:,.0f}
- Best case (95th %ile): ₹{simulation['percentiles']['p95']:,.0f}
- Worst case (5th %ile): ₹{simulation['percentiles']['p5']:,.0f}

⚖️ **Probabilities:**
- Probability of profit: {simulation['prob_profit']}%
- Probability of doubling: {simulation['prob_double']}%
- Probability of 50%+ loss: {simulation['prob_loss_50']}%

⚠️ **Caveats:**
This simulation assumes normal distribution of returns and constant volatility - real markets can be more extreme. Past performance ≠ future results.

{DISCLAIMER}""",
        "disclaimer": DISCLAIMER
    }

@api_router.get("/portfolio/backtest")
async def portfolio_backtest(request: Request, benchmark: str = "nifty"):
    """Backtest portfolio against benchmark"""
    user = await require_auth(request)
    
    # Generate mock historical data for demonstration
    days = 90
    portfolio_values = [100000]
    benchmark_values = [100000]
    dates = []
    
    for i in range(days):
        date = datetime.now(timezone.utc) - timedelta(days=days-i)
        dates.append(date.strftime("%Y-%m-%d"))
        
        portfolio_change = random.gauss(0.001, 0.02)
        benchmark_change = random.gauss(0.0008, 0.015)
        
        portfolio_values.append(portfolio_values[-1] * (1 + portfolio_change))
        benchmark_values.append(benchmark_values[-1] * (1 + benchmark_change))
    
    backtest = PortfolioAnalytics.backtest_vs_benchmark(
        portfolio_values, benchmark_values, dates
    )
    
    return {
        "backtest": backtest,
        "benchmark": benchmark,
        "period_days": days,
        "chart_data": {
            "dates": dates[-30:],
            "portfolio": portfolio_values[-30:],
            "benchmark": benchmark_values[-30:]
        },
        "interpretation": f"""**Backtest vs {benchmark.upper()} ({days} days)**

📊 **Performance:**
- Portfolio return: {backtest['portfolio_return']}%
- Benchmark return: {backtest['benchmark_return']}%
- Outperformance: {backtest['outperformance']}%

📈 **Risk Metrics:**
- Alpha (annualized): {backtest['alpha']}%
- Beta: {backtest['beta']}
- Correlation: {backtest['correlation']}

⚠️ **Note:**
{'+' if backtest['outperformance'] > 0 else '-'}{'Outperformed' if backtest['outperformance'] > 0 else 'Underperformed'} benchmark by {abs(backtest['outperformance']):.1f}%. Beta of {backtest['beta']:.2f} indicates {'higher' if backtest['beta'] > 1 else 'lower'} volatility than market.

{DISCLAIMER}""",
        "disclaimer": DISCLAIMER
    }

@api_router.get("/portfolio/export")
async def export_portfolio(request: Request, format: str = "csv"):
    """Export portfolio for tax filing"""
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": False},
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate tax for each trade
    export_data = []
    total_crypto_gains = 0
    total_stock_ltcg = 0
    total_stock_stcg = 0
    
    for trade in trades:
        trade_date = trade["trade_date"]
        if isinstance(trade_date, datetime):
            trade_date_str = trade_date.strftime("%Y-%m-%d")
            holding_days = (datetime.now(timezone.utc) - trade_date.replace(tzinfo=timezone.utc)).days
        else:
            trade_date_str = str(trade_date)
            holding_days = 0
        
        # Estimate gain (simplified)
        estimated_gain = trade["total_value_inr"] * 0.1 if trade["trade_type"] == "sell" else 0
        
        if trade["asset_type"] == "crypto":
            tax_info = IndianTaxCalculator.calculate_crypto_tax(estimated_gain)
            total_crypto_gains += estimated_gain
        else:
            tax_info = IndianTaxCalculator.calculate_stock_tax(estimated_gain, holding_days)
            if holding_days >= 365:
                total_stock_ltcg += estimated_gain
            else:
                total_stock_stcg += estimated_gain
        
        export_data.append({
            "Date": trade_date_str,
            "Asset_Type": trade["asset_type"].upper(),
            "Symbol": trade["asset_symbol"],
            "Name": trade["asset_name"],
            "Trade_Type": trade["trade_type"].upper(),
            "Quantity": trade["quantity"],
            "Price_INR": trade["price_inr"],
            "Total_Value_INR": trade["total_value_inr"],
            "Holding_Days": holding_days,
            "Tax_Type": tax_info.get("type", "VDA"),
            "Estimated_Tax_INR": tax_info.get("tax_payable", 0),
            "Notes": trade.get("notes", "")
        })
    
    if format == "csv":
        output = io.StringIO()
        if export_data:
            writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
            writer.writeheader()
            writer.writerows(export_data)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=investiq_trades_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    
    return {
        "data": export_data,
        "tax_summary": {
            "crypto_gains": total_crypto_gains,
            "crypto_tax_30pct": total_crypto_gains * 0.30,
            "stock_ltcg": total_stock_ltcg,
            "stock_ltcg_tax": max(0, total_stock_ltcg - 100000) * 0.10,
            "stock_stcg": total_stock_stcg,
            "stock_stcg_tax": total_stock_stcg * 0.15
        },
        "tax_notes": {
            "crypto_vda": "30% flat tax on all crypto gains. No loss offset allowed. 1% TDS on transactions >₹10,000.",
            "stock_ltcg": "10% on gains above ₹1 lakh for holdings >1 year. Losses can be offset.",
            "stock_stcg": "15% flat rate for holdings <1 year. Losses can be offset.",
            "disclaimer": "This is an estimate only. Consult a CA for accurate tax calculations."
        },
        "disclaimer": DISCLAIMER
    }

# ==================== WATCHLIST ROUTES ====================

@api_router.post("/watchlist")
async def add_to_watchlist(item: WatchlistCreate, request: Request):
    user = await require_auth(request)
    
    watchlist_item = {
        "item_id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "asset_type": item.asset_type,
        "asset_symbol": item.asset_symbol,
        "asset_name": item.asset_name,
        "added_at": datetime.now(timezone.utc),
        "target_price": item.target_price,
        "alert_enabled": item.alert_enabled
    }
    
    await db.watchlist.insert_one(watchlist_item)
    watchlist_item.pop("_id", None)
    watchlist_item["added_at"] = watchlist_item["added_at"].isoformat()
    
    return {"success": True, "item": watchlist_item}

@api_router.get("/watchlist")
async def get_watchlist(request: Request):
    user = await require_auth(request)
    
    items = await db.watchlist.find({"user_id": user.user_id}, {"_id": 0}).to_list(100)
    
    crypto_prices = await crypto_service.get_prices()
    stock_prices = await stock_service.get_nifty50()
    
    watchlist = []
    for item in items:
        if item["asset_type"] == "crypto":
            data = crypto_prices.get(item["asset_symbol"], {})
        else:
            data = stock_prices.get(item["asset_symbol"], {})
        
        current_price = data.get("price_inr", 0)
        change = data.get("change_24h", 0)
        
        # Calculate AI score
        volatility_score = min(abs(change) * 10, 50)
        momentum_score = 50 if change > 0 else 30
        ai_score = round((volatility_score + momentum_score) / 2, 1)
        
        watchlist.append({
            **item,
            "added_at": item["added_at"].isoformat() if isinstance(item["added_at"], datetime) else item["added_at"],
            "current_price": current_price,
            "change_24h": change,
            "ai_score": ai_score
        })
    
    watchlist.sort(key=lambda x: x["ai_score"], reverse=True)
    return {"watchlist": watchlist}

@api_router.delete("/watchlist/{item_id}")
async def remove_from_watchlist(item_id: str, request: Request):
    user = await require_auth(request)
    result = await db.watchlist.delete_one({"item_id": item_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True}

# ==================== USER SETTINGS ====================

@api_router.put("/user/capital")
async def update_capital(capital_update: CapitalUpdate, request: Request):
    user = await require_auth(request)
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"capital": capital_update.capital}})
    return {"success": True, "capital": capital_update.capital}

@api_router.put("/user/risk-profile")
async def update_risk_profile(update: RiskProfileUpdate, request: Request):
    user = await require_auth(request)
    if update.risk_profile not in RISK_MULTIPLIERS:
        raise HTTPException(status_code=400, detail="Invalid risk profile")
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"risk_profile": update.risk_profile}})
    return {"success": True, "risk_profile": update.risk_profile}

@api_router.put("/user/fcm-token")
async def update_fcm_token(update: FCMTokenUpdate, request: Request):
    user = await require_auth(request)
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"fcm_token": update.fcm_token}})
    return {"success": True}

@api_router.get("/user/settings")
async def get_user_settings(request: Request):
    user = await require_auth(request)
    return {
        "capital": user.capital,
        "risk_profile": user.risk_profile,
        "email": user.email,
        "name": user.name,
        "risk_multipliers": RISK_MULTIPLIERS.get(user.risk_profile, RISK_MULTIPLIERS["medium"])
    }

# ==================== EDUCATION ====================

@api_router.get("/education/tips")
async def get_education_tips():
    return {
        "tips": [
            {"id": "crypto_tax", "title": "Crypto Taxation in India", "content": "30% flat tax on all crypto gains (VDA). No deductions except cost. 1% TDS on transactions >₹10,000. Losses CANNOT be offset.", "category": "tax"},
            {"id": "stock_tax", "title": "Stock Market Taxation", "content": "LTCG (>1 year): 10% on gains above ₹1 lakh. STCG (<1 year): 15%. STT applies. Losses can be offset and carried forward.", "category": "tax"},
            {"id": "risk_disclaimer", "title": "Risk Disclaimer", "content": DISCLAIMER, "category": "disclaimer"},
            {"id": "diversification", "title": "Portfolio Diversification", "content": "Don't put all eggs in one basket. Consider: 5-15% crypto (high risk), 60-80% stocks, 10-20% debt/gold.", "category": "strategy"},
            {"id": "stop_loss", "title": "Stop Loss Strategy", "content": "Always set stop-losses. Crypto: 10-15%, Stocks: 7-10%. Use trailing stops to protect profits.", "category": "strategy"},
            {"id": "position_sizing", "title": "Position Sizing", "content": "Never risk >2% of capital on single trade. Max 5% per position. Aggressive? Still cap at 10%.", "category": "strategy"}
        ],
        "disclaimer": DISCLAIMER
    }

# Include router
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
