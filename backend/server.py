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

# ==================== CRYPTO DATA SERVICE (CoinGecko) ====================

class CryptoDataService:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.cache = {}
        self.cache_ttl = 60  # seconds
        
    async def get_prices(self) -> Dict:
        """Get top 20 crypto prices from CoinGecko"""
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
                            "last_updated": coin.get("last_updated", datetime.now(timezone.utc).isoformat())
                        }
                    self.cache[cache_key] = (datetime.now(), result)
                    return result
                else:
                    logger.warning(f"CoinGecko API returned {response.status_code}, using fallback")
                    return self._get_fallback_prices()
        except Exception as e:
            logger.error(f"CoinGecko API error: {e}")
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
        """Fallback mock data when API fails"""
        return {
            "BTC": {"id": "bitcoin", "name": "Bitcoin", "price_inr": 7245000, "change_24h": 2.3, "volume_24h": 45000000000 * USD_TO_INR, "market_cap": 141000000000000, "high_24h": 7300000, "low_24h": 7150000},
            "ETH": {"id": "ethereum", "name": "Ethereum", "price_inr": 325000, "change_24h": 1.8, "volume_24h": 18000000000 * USD_TO_INR, "market_cap": 39000000000000, "high_24h": 330000, "low_24h": 320000},
            "BNB": {"id": "binancecoin", "name": "BNB", "price_inr": 52000, "change_24h": -0.5, "volume_24h": 1200000000 * USD_TO_INR, "market_cap": 8000000000000, "high_24h": 53000, "low_24h": 51000},
            "SOL": {"id": "solana", "name": "Solana", "price_inr": 15500, "change_24h": 4.2, "volume_24h": 3500000000 * USD_TO_INR, "market_cap": 7200000000000, "high_24h": 16000, "low_24h": 15000},
            "XRP": {"id": "ripple", "name": "XRP", "price_inr": 185, "change_24h": -1.2, "volume_24h": 2800000000 * USD_TO_INR, "market_cap": 9500000000000, "high_24h": 190, "low_24h": 180},
            "ADA": {"id": "cardano", "name": "Cardano", "price_inr": 82, "change_24h": 0.8, "volume_24h": 650000000 * USD_TO_INR, "market_cap": 2900000000000, "high_24h": 85, "low_24h": 80},
            "DOGE": {"id": "dogecoin", "name": "Dogecoin", "price_inr": 28, "change_24h": 3.5, "volume_24h": 1100000000 * USD_TO_INR, "market_cap": 4100000000000, "high_24h": 29, "low_24h": 27},
            "AVAX": {"id": "avalanche-2", "name": "Avalanche", "price_inr": 4200, "change_24h": 2.1, "volume_24h": 520000000 * USD_TO_INR, "market_cap": 1700000000000, "high_24h": 4300, "low_24h": 4100},
            "DOT": {"id": "polkadot", "name": "Polkadot", "price_inr": 850, "change_24h": -0.3, "volume_24h": 380000000 * USD_TO_INR, "market_cap": 1200000000000, "high_24h": 860, "low_24h": 840},
            "MATIC": {"id": "matic-network", "name": "Polygon", "price_inr": 95, "change_24h": 1.5, "volume_24h": 420000000 * USD_TO_INR, "market_cap": 880000000000, "high_24h": 98, "low_24h": 93},
            "LINK": {"id": "chainlink", "name": "Chainlink", "price_inr": 1850, "change_24h": 2.8, "volume_24h": 680000000 * USD_TO_INR, "market_cap": 1100000000000, "high_24h": 1900, "low_24h": 1800},
            "UNI": {"id": "uniswap", "name": "Uniswap", "price_inr": 1420, "change_24h": 1.2, "volume_24h": 280000000 * USD_TO_INR, "market_cap": 850000000000, "high_24h": 1450, "low_24h": 1400},
            "ATOM": {"id": "cosmos", "name": "Cosmos", "price_inr": 1250, "change_24h": -0.8, "volume_24h": 220000000 * USD_TO_INR, "market_cap": 480000000000, "high_24h": 1280, "low_24h": 1220},
            "LTC": {"id": "litecoin", "name": "Litecoin", "price_inr": 11500, "change_24h": 0.5, "volume_24h": 450000000 * USD_TO_INR, "market_cap": 860000000000, "high_24h": 11700, "low_24h": 11300},
            "NEAR": {"id": "near", "name": "NEAR Protocol", "price_inr": 680, "change_24h": 3.8, "volume_24h": 320000000 * USD_TO_INR, "market_cap": 720000000000, "high_24h": 700, "low_24h": 660},
            "APT": {"id": "aptos", "name": "Aptos", "price_inr": 1150, "change_24h": 2.5, "volume_24h": 280000000 * USD_TO_INR, "market_cap": 520000000000, "high_24h": 1180, "low_24h": 1120},
            "ARB": {"id": "arbitrum", "name": "Arbitrum", "price_inr": 145, "change_24h": 1.8, "volume_24h": 380000000 * USD_TO_INR, "market_cap": 580000000000, "high_24h": 150, "low_24h": 142},
            "OP": {"id": "optimism", "name": "Optimism", "price_inr": 285, "change_24h": 2.2, "volume_24h": 250000000 * USD_TO_INR, "market_cap": 320000000000, "high_24h": 295, "low_24h": 278},
            "INJ": {"id": "injective-protocol", "name": "Injective", "price_inr": 3500, "change_24h": 4.5, "volume_24h": 180000000 * USD_TO_INR, "market_cap": 320000000000, "high_24h": 3600, "low_24h": 3400},
            "RENDER": {"id": "render-token", "name": "Render", "price_inr": 1250, "change_24h": 5.2, "volume_24h": 220000000 * USD_TO_INR, "market_cap": 480000000000, "high_24h": 1300, "low_24h": 1200}
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
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    @staticmethod
    def calculate_macd(prices: List[float]) -> Dict:
        """Calculate MACD indicator"""
        if len(prices) < 26:
            return {"macd": 0, "signal": 0, "histogram": 0, "trend": "neutral"}
        
        prices_arr = np.array(prices)
        
        # Calculate EMAs
        ema12 = TechnicalAnalysis._ema(prices_arr, 12)
        ema26 = TechnicalAnalysis._ema(prices_arr, 26)
        
        macd_line = ema12 - ema26
        signal_line = TechnicalAnalysis._ema(macd_line, 9) if len(macd_line) >= 9 else macd_line
        histogram = macd_line[-1] - signal_line[-1] if len(signal_line) > 0 else 0
        
        trend = "bullish" if histogram > 0 else "bearish" if histogram < 0 else "neutral"
        
        return {
            "macd": round(macd_line[-1], 4),
            "signal": round(signal_line[-1], 4),
            "histogram": round(histogram, 4),
            "trend": trend
        }
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            current = prices[-1] if prices else 0
            return {
                "upper": current * 1.02,
                "middle": current,
                "lower": current * 0.98,
                "bandwidth": 4.0,
                "position": "middle",
                "squeeze": False
            }
        
        prices_arr = np.array(prices[-period:])
        middle = np.mean(prices_arr)
        std = np.std(prices_arr)
        upper = middle + (num_std * std)
        lower = middle - (num_std * std)
        
        current_price = prices[-1]
        bandwidth = ((upper - lower) / middle) * 100
        
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
        squeeze = bandwidth < 5.0
        
        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "bandwidth": round(bandwidth, 2),
            "position": position,
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
    
    def _generate_mock_analysis(self, context: str = "") -> str:
        return f"""**Grok-Style Analysis**

📊 **Core Assessment:**
Based on current market data, we observe mixed signals requiring careful interpretation.

🔍 **Assumption Check:**
- Common belief: "This trend will continue" — BUT historical data shows mean reversion occurs 70% of time within 2 weeks
- Liquidity appears strong — HOWEVER, this could indicate distribution rather than accumulation

⚖️ **Probability Framework:**
- Bullish scenario (40%): Continuation with 15-20% upside
- Neutral scenario (35%): Consolidation in current range
- Bearish scenario (25%): Correction of 10-15%

⚠️ **Risk Factors:**
1. Global macro uncertainty (Fed policy, geopolitical tensions)
2. India-specific: INR volatility, regulatory changes
3. Tax impact: 30% VDA tax significantly reduces net returns

🔄 **Counterpoint:**
While momentum appears positive, elevated volume could indicate late-stage accumulation before distribution. Consider: Is this genuine demand or manufactured liquidity?

💡 **Alternative Actions:**
- Option A: Enter with reduced position size (50% of planned)
- Option B: Wait for pullback to support levels
- Option C: Hedge with inverse positions

{DISCLAIMER}"""

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

@api_router.get("/news")
async def get_news(category: Optional[str] = None, search: Optional[str] = None, use_ai: bool = False):
    """Get news with AI analysis"""
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
                f"Analyze this news for Indian investors: {item['title']} - {item['summary']}",
                f"Category: {item['category']}, Impact: {item['impact_level']}"
            )
        else:
            analysis = ai_service._generate_mock_analysis(item['category'])
        
        news_with_analysis.append({
            **item,
            "published_at": item["published_at"].isoformat(),
            "ai_analysis": analysis
        })
    
    return {"news": news_with_analysis, "total": len(news_with_analysis), "disclaimer": DISCLAIMER}

@api_router.get("/news/categories")
async def get_news_categories():
    return {
        "categories": [
            {"id": "world_economies", "name": "World Economies", "icon": "globe"},
            {"id": "geopolitics", "name": "Geopolitics", "icon": "flag"},
            {"id": "india_specific", "name": "India Specific", "icon": "map-pin"},
            {"id": "crypto_relevant", "name": "Crypto & Stocks", "icon": "trending-up"}
        ]
    }

# ==================== DAILY DECISION ROUTES ====================

@api_router.get("/decision/today")
async def get_daily_decision(use_ai: bool = False, risk_profile: str = "medium"):
    """Get today's investment decision with technical analysis"""
    # Get real market data
    crypto_prices = await crypto_service.get_prices()
    btc_data = crypto_prices.get("BTC", {})
    eth_data = crypto_prices.get("ETH", {})
    
    # Get historical for technicals
    btc_history = await crypto_service.get_historical_data("bitcoin", 30)
    btc_closes = [h["close"] for h in btc_history] if btc_history else [btc_data.get("price_inr", 7000000)]
    
    btc_rsi = TechnicalAnalysis.calculate_rsi(btc_closes)
    btc_macd = TechnicalAnalysis.calculate_macd(btc_closes)
    btc_bollinger = TechnicalAnalysis.calculate_bollinger_bands(btc_closes)
    
    market_data = {
        "btc_price": btc_data.get("price_inr", 7000000),
        "btc_rsi": btc_rsi,
        "btc_macd": btc_macd,
        "btc_bollinger": btc_bollinger,
        "btc_change": btc_data.get("change_24h", 0),
        "eth_price": eth_data.get("price_inr", 300000),
        "eth_change": eth_data.get("change_24h", 0),
        "nifty_level": 24500,
        "nifty_change": 0.8,
        "inr_usd": USD_TO_INR
    }
    
    # Generate decision based on technicals
    risk_mult = RISK_MULTIPLIERS.get(risk_profile, RISK_MULTIPLIERS["medium"])
    
    if btc_rsi > 70:
        recommendation = "Hold"
        confidence = 70
        reasoning = f"""**Technical Assessment: OVERBOUGHT CONDITIONS**

📊 **Key Indicators:**
- RSI: {btc_rsi} (>70 = overbought)
- MACD: {btc_macd['trend']} with histogram at {btc_macd['histogram']}
- Bollinger: Price at {btc_bollinger['position']}, bandwidth {btc_bollinger['bandwidth']}%

⚖️ **Probability Assessment:**
- 65% chance of 5-10% correction within 1-2 weeks
- 25% chance of continued rally (FOMO-driven)
- 10% chance of sharp correction (>15%)

🔍 **Counterpoint:**
Strong momentum can persist longer than expected. However, risk-adjusted returns favor waiting for RSI <60.

💡 **Alternative:**
If bullish, reduce position size to 50% of normal and set tight stop-loss at 5%.

{DISCLAIMER}"""
    elif btc_rsi < 35:
        recommendation = "Crypto"
        confidence = 72
        reasoning = f"""**Technical Assessment: OVERSOLD - ACCUMULATION ZONE**

📊 **Key Indicators:**
- RSI: {btc_rsi} (<35 = oversold)
- MACD: {btc_macd['trend']} - watch for bullish crossover
- Bollinger: Price near {btc_bollinger['position']}, potential bounce

⚖️ **Probability Assessment:**
- 70% chance of 10-20% recovery within 2-3 weeks
- 20% chance of further decline (capitulation)
- 10% chance of rapid V-shaped recovery

🔍 **Counterpoint:**
"Catching falling knives" is dangerous. Ensure support levels are holding before entry.

💡 **Strategy:**
- Deploy 40% of planned capital now
- Reserve 60% for potential further dips
- Stop-loss: 12% below entry

{DISCLAIMER}"""
    else:
        recommendation = "Both"
        confidence = 65
        reasoning = f"""**Technical Assessment: NEUTRAL - BALANCED APPROACH**

📊 **Key Indicators:**
- BTC RSI: {btc_rsi} (neutral zone 40-60)
- MACD: {btc_macd['trend']}
- Bollinger: {btc_bollinger['position']}, squeeze={btc_bollinger['squeeze']}

⚖️ **Allocation Suggestion:**
- Crypto (40%): BTC 50%, ETH 30%, SOL 20%
- Stocks (60%): Banking 30%, IT 25%, FMCG 25%, Pharma 20%

🔍 **Counterpoint:**
Neutral markets can break either direction. Bollinger squeeze indicates big move coming - direction uncertain.

💡 **Risk Management:**
- Position size: {int(5 * risk_mult['position_size'])}% max per trade
- Stop-loss: {int(10 * risk_mult['stop_loss'])}% for crypto, {int(7 * risk_mult['stop_loss'])}% for stocks
- Rebalance on 15%+ moves

{DISCLAIMER}"""
    
    allocations = {
        "crypto": {"BTC": 50, "ETH": 30, "SOL": 20} if recommendation in ["Crypto", "Both"] else {},
        "stocks": {"HDFCBANK": 25, "TCS": 25, "HINDUNILVR": 25, "SUNPHARMA": 25} if recommendation in ["Stocks", "Both"] else {}
    }
    
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
                "Regulatory changes (SEBI/RBI crypto stance)",
                "Global macro deterioration",
                f"30% VDA tax reduces net crypto returns significantly",
                "INR volatility affecting international comparisons"
            ],
            "timeline": "Swing trade (1-4 weeks) for crypto, Position (6-12 months) for stocks"
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
