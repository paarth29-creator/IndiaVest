from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'test_database')]

# Get Emergent LLM Key
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Create the main app
app = FastAPI(title="Indian Investment Guidance App")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime
    capital: float = 100000.0  # Default 1 Lakh INR virtual capital
    risk_profile: str = "moderate"  # conservative, moderate, aggressive

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime

class SessionDataResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str

class Trade(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    asset_type: str  # crypto or stock
    asset_symbol: str
    asset_name: str
    quantity: float
    price_inr: float
    total_value_inr: float
    trade_type: str  # buy or sell
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

# ==================== MOCK DATA ====================

# Top 20 Cryptos with realistic INR prices (as of mock date)
MOCK_CRYPTO_DATA = {
    "BTC": {"name": "Bitcoin", "price_inr": 7245000, "change_24h": 2.3, "volume_24h": 45000000000, "market_cap": 141000000000000, "rsi": 58, "tvl": 125000000000},
    "ETH": {"name": "Ethereum", "price_inr": 325000, "change_24h": 1.8, "volume_24h": 18000000000, "market_cap": 39000000000000, "rsi": 52, "tvl": 85000000000},
    "BNB": {"name": "BNB", "price_inr": 52000, "change_24h": -0.5, "volume_24h": 1200000000, "market_cap": 8000000000000, "rsi": 45, "tvl": 12000000000},
    "SOL": {"name": "Solana", "price_inr": 15500, "change_24h": 4.2, "volume_24h": 3500000000, "market_cap": 7200000000000, "rsi": 65, "tvl": 8500000000},
    "XRP": {"name": "XRP", "price_inr": 185, "change_24h": -1.2, "volume_24h": 2800000000, "market_cap": 9500000000000, "rsi": 42, "tvl": None},
    "ADA": {"name": "Cardano", "price_inr": 82, "change_24h": 0.8, "volume_24h": 650000000, "market_cap": 2900000000000, "rsi": 48, "tvl": 450000000},
    "DOGE": {"name": "Dogecoin", "price_inr": 28, "change_24h": 3.5, "volume_24h": 1100000000, "market_cap": 4100000000000, "rsi": 55, "tvl": None},
    "AVAX": {"name": "Avalanche", "price_inr": 4200, "change_24h": 2.1, "volume_24h": 520000000, "market_cap": 1700000000000, "rsi": 51, "tvl": 2100000000},
    "DOT": {"name": "Polkadot", "price_inr": 850, "change_24h": -0.3, "volume_24h": 380000000, "market_cap": 1200000000000, "rsi": 44, "tvl": 320000000},
    "MATIC": {"name": "Polygon", "price_inr": 95, "change_24h": 1.5, "volume_24h": 420000000, "market_cap": 880000000000, "rsi": 49, "tvl": 1800000000},
    "LINK": {"name": "Chainlink", "price_inr": 1850, "change_24h": 2.8, "volume_24h": 680000000, "market_cap": 1100000000000, "rsi": 56, "tvl": 18000000000},
    "UNI": {"name": "Uniswap", "price_inr": 1420, "change_24h": 1.2, "volume_24h": 280000000, "market_cap": 850000000000, "rsi": 47, "tvl": 6200000000},
    "ATOM": {"name": "Cosmos", "price_inr": 1250, "change_24h": -0.8, "volume_24h": 220000000, "market_cap": 480000000000, "rsi": 43, "tvl": 950000000},
    "LTC": {"name": "Litecoin", "price_inr": 11500, "change_24h": 0.5, "volume_24h": 450000000, "market_cap": 860000000000, "rsi": 50, "tvl": None},
    "NEAR": {"name": "NEAR Protocol", "price_inr": 680, "change_24h": 3.8, "volume_24h": 320000000, "market_cap": 720000000000, "rsi": 62, "tvl": 580000000},
    "APT": {"name": "Aptos", "price_inr": 1150, "change_24h": 2.5, "volume_24h": 280000000, "market_cap": 520000000000, "rsi": 54, "tvl": 420000000},
    "ARB": {"name": "Arbitrum", "price_inr": 145, "change_24h": 1.8, "volume_24h": 380000000, "market_cap": 580000000000, "rsi": 51, "tvl": 3200000000},
    "OP": {"name": "Optimism", "price_inr": 285, "change_24h": 2.2, "volume_24h": 250000000, "market_cap": 320000000000, "rsi": 53, "tvl": 1100000000},
    "INJ": {"name": "Injective", "price_inr": 3500, "change_24h": 4.5, "volume_24h": 180000000, "market_cap": 320000000000, "rsi": 67, "tvl": 85000000},
    "RENDER": {"name": "Render", "price_inr": 1250, "change_24h": 5.2, "volume_24h": 220000000, "market_cap": 480000000000, "rsi": 71, "tvl": None}
}

# Nifty 50 stocks with realistic data
MOCK_STOCK_DATA = {
    "RELIANCE": {"name": "Reliance Industries", "price_inr": 2850, "change_24h": 0.8, "pe_ratio": 28.5, "eps": 100, "market_cap": 1920000, "sector": "Energy"},
    "TCS": {"name": "Tata Consultancy Services", "price_inr": 3920, "change_24h": -0.3, "pe_ratio": 32.1, "eps": 122, "market_cap": 1420000, "sector": "IT"},
    "HDFCBANK": {"name": "HDFC Bank", "price_inr": 1680, "change_24h": 1.2, "pe_ratio": 19.8, "eps": 85, "market_cap": 1280000, "sector": "Banking"},
    "INFY": {"name": "Infosys", "price_inr": 1520, "change_24h": 0.5, "pe_ratio": 25.3, "eps": 60, "market_cap": 630000, "sector": "IT"},
    "ICICIBANK": {"name": "ICICI Bank", "price_inr": 1250, "change_24h": 0.9, "pe_ratio": 18.2, "eps": 69, "market_cap": 880000, "sector": "Banking"},
    "HINDUNILVR": {"name": "Hindustan Unilever", "price_inr": 2450, "change_24h": -0.2, "pe_ratio": 58.5, "eps": 42, "market_cap": 575000, "sector": "FMCG"},
    "BHARTIARTL": {"name": "Bharti Airtel", "price_inr": 1580, "change_24h": 1.5, "pe_ratio": 45.2, "eps": 35, "market_cap": 890000, "sector": "Telecom"},
    "SBIN": {"name": "State Bank of India", "price_inr": 820, "change_24h": 2.1, "pe_ratio": 11.5, "eps": 71, "market_cap": 732000, "sector": "Banking"},
    "BAJFINANCE": {"name": "Bajaj Finance", "price_inr": 7250, "change_24h": -0.8, "pe_ratio": 35.8, "eps": 203, "market_cap": 450000, "sector": "NBFC"},
    "WIPRO": {"name": "Wipro", "price_inr": 485, "change_24h": 0.3, "pe_ratio": 22.8, "eps": 21, "market_cap": 252000, "sector": "IT"},
    "LT": {"name": "Larsen & Toubro", "price_inr": 3450, "change_24h": 1.8, "pe_ratio": 38.5, "eps": 90, "market_cap": 480000, "sector": "Infrastructure"},
    "ASIANPAINT": {"name": "Asian Paints", "price_inr": 2850, "change_24h": -0.5, "pe_ratio": 72.5, "eps": 39, "market_cap": 273000, "sector": "Paints"},
    "MARUTI": {"name": "Maruti Suzuki", "price_inr": 12500, "change_24h": 0.7, "pe_ratio": 28.2, "eps": 443, "market_cap": 393000, "sector": "Auto"},
    "TATAMOTORS": {"name": "Tata Motors", "price_inr": 985, "change_24h": 2.5, "pe_ratio": 12.8, "eps": 77, "market_cap": 365000, "sector": "Auto"},
    "SUNPHARMA": {"name": "Sun Pharma", "price_inr": 1720, "change_24h": 0.4, "pe_ratio": 38.2, "eps": 45, "market_cap": 413000, "sector": "Pharma"},
    "TITAN": {"name": "Titan Company", "price_inr": 3250, "change_24h": 1.1, "pe_ratio": 85.5, "eps": 38, "market_cap": 288000, "sector": "Consumer"},
    "AXISBANK": {"name": "Axis Bank", "price_inr": 1180, "change_24h": 0.6, "pe_ratio": 14.5, "eps": 81, "market_cap": 364000, "sector": "Banking"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank", "price_inr": 1850, "change_24h": -0.4, "pe_ratio": 21.8, "eps": 85, "market_cap": 367000, "sector": "Banking"},
    "HCLTECH": {"name": "HCL Technologies", "price_inr": 1580, "change_24h": 0.9, "pe_ratio": 24.5, "eps": 65, "market_cap": 429000, "sector": "IT"},
    "TECHM": {"name": "Tech Mahindra", "price_inr": 1420, "change_24h": 1.3, "pe_ratio": 28.8, "eps": 49, "market_cap": 138000, "sector": "IT"}
}

# Mock News Data
MOCK_NEWS_DATA = [
    {
        "id": "news_1",
        "title": "US Federal Reserve Signals Potential Rate Cut in Q3 2025",
        "source": "Reuters",
        "category": "world_economies",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=2),
        "summary": "Fed Chair indicates dovish stance amid cooling inflation, potentially boosting global risk assets.",
        "url": "https://reuters.com/markets/fed-rate-cut",
        "impact_level": "high"
    },
    {
        "id": "news_2",
        "title": "RBI Maintains Repo Rate at 6.5%, Signals Neutral Stance",
        "source": "Economic Times",
        "category": "india_specific",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=4),
        "summary": "Reserve Bank of India keeps rates unchanged, focuses on inflation management while supporting growth.",
        "url": "https://economictimes.com/rbi-policy",
        "impact_level": "high"
    },
    {
        "id": "news_3",
        "title": "Bitcoin ETF Inflows Reach $500M Daily Average",
        "source": "Bloomberg",
        "category": "crypto_relevant",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=6),
        "summary": "Institutional adoption continues as spot Bitcoin ETFs see sustained inflows.",
        "url": "https://bloomberg.com/bitcoin-etf",
        "impact_level": "high"
    },
    {
        "id": "news_4",
        "title": "India-China Border Tensions Ease After Diplomatic Talks",
        "source": "Business Standard",
        "category": "geopolitics",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=8),
        "summary": "Both nations agree to de-escalation measures, reducing geopolitical risk premium.",
        "url": "https://business-standard.com/india-china",
        "impact_level": "medium"
    },
    {
        "id": "news_5",
        "title": "Ethereum Layer 2 TVL Surpasses $50 Billion",
        "source": "CoinDesk",
        "category": "crypto_relevant",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=10),
        "summary": "Arbitrum and Optimism lead growth as scalability solutions gain traction.",
        "url": "https://coindesk.com/l2-tvl",
        "impact_level": "medium"
    },
    {
        "id": "news_6",
        "title": "SEBI Proposes New Framework for Crypto Regulation",
        "source": "Economic Times",
        "category": "india_specific",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=12),
        "summary": "Securities regulator outlines potential licensing requirements for crypto exchanges.",
        "url": "https://economictimes.com/sebi-crypto",
        "impact_level": "high"
    },
    {
        "id": "news_7",
        "title": "Oil Prices Surge 5% on OPEC+ Production Cuts",
        "source": "Reuters",
        "category": "world_economies",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=14),
        "summary": "Energy costs rise globally, impacting inflation outlook for emerging markets.",
        "url": "https://reuters.com/oil-opec",
        "impact_level": "high"
    },
    {
        "id": "news_8",
        "title": "Nifty 50 Hits All-Time High Amid FII Inflows",
        "source": "Business Standard",
        "category": "india_specific",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=16),
        "summary": "Foreign institutional investors pump ₹15,000 crore into Indian equities this week.",
        "url": "https://business-standard.com/nifty-high",
        "impact_level": "high"
    },
    {
        "id": "news_9",
        "title": "Solana Network Processes 100M Daily Transactions",
        "source": "CoinDesk",
        "category": "crypto_relevant",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=18),
        "summary": "High throughput blockchain sees massive DeFi and NFT activity.",
        "url": "https://coindesk.com/solana-txns",
        "impact_level": "medium"
    },
    {
        "id": "news_10",
        "title": "US-EU Trade Agreement Progress Boosts Global Sentiment",
        "source": "Bloomberg",
        "category": "geopolitics",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=20),
        "summary": "Negotiations advance on tariff reductions, easing global trade tensions.",
        "url": "https://bloomberg.com/us-eu-trade",
        "impact_level": "medium"
    }
]

# ==================== AUTH HELPERS ====================

async def get_session_token(request: Request) -> Optional[str]:
    """Extract session token from cookie or header"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
    return session_token

async def get_current_user(request: Request) -> Optional[User]:
    """Get current authenticated user"""
    session_token = await get_session_token(request)
    if not session_token:
        return None
    
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    if not session:
        return None
    
    # Check expiry with timezone awareness
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    
    user_doc = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    if user_doc:
        return User(**user_doc)
    return None

async def require_auth(request: Request) -> User:
    """Require authentication, raise 401 if not authenticated"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ==================== AI ANALYSIS FUNCTIONS ====================

async def generate_ai_analysis(news_item: dict) -> str:
    """Generate Grok-style AI analysis for news using Claude"""
    if not EMERGENT_LLM_KEY:
        return generate_mock_analysis(news_item)
    
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        system_prompt = """You are a sharp, analytical investment advisor with Grok-style reasoning. 
Your analysis style:
- Dissect assumptions ruthlessly
- Provide counterpoints to conventional wisdom
- Prioritize truth over comfort
- Be direct and cut through noise
- Focus on actionable insights for Indian investors

Consider:
- Impact on Indian markets (INR, Nifty, sectors)
- Crypto implications (BTC, ETH, altcoins)
- Tax implications (30% VDA tax, LTCG)
- Risk-reward with probability estimates
- Short-term vs long-term perspectives"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"news_analysis_{news_item['id']}",
            system_message=system_prompt
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        
        prompt = f"""Analyze this news for Indian investors:

Title: {news_item['title']}
Source: {news_item['source']}
Category: {news_item['category']}
Summary: {news_item['summary']}

Provide:
1. Key implications for Indian crypto investors (short-term trading)
2. Impact on Indian stock market (long-term investment)
3. Probability estimates for market movements
4. Actionable recommendation with risk warning
5. Counterpoint to the obvious interpretation

Keep response under 300 words. Be direct and analytical."""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return generate_mock_analysis(news_item)

def generate_mock_analysis(news_item: dict) -> str:
    """Generate mock analysis when AI is unavailable"""
    category = news_item.get('category', '')
    
    analyses = {
        "world_economies": f"""📊 **Market Impact Analysis**

**Crypto Implications (Short-term):**
This development signals potential USD strength/weakness dynamics. For Indian crypto traders, expect:
- BTC correlation with risk assets: 70% probability of 2-5% movement
- ETH may see higher volatility due to DeFi sensitivity
- Consider reducing position sizes during uncertainty

**Stock Market (Long-term):**
- Banking sector: Neutral to slightly positive
- IT exports: Monitor INR/USD for margin impacts
- Energy stocks: Watch crude price correlation

**Risk Warning:** High uncertainty period. Maintain stop-losses at 8-10% for crypto, 5% for stocks.

**Counterpoint:** Markets may have already priced this in. Look for divergence from expected reaction.""",

        "india_specific": f"""🇮🇳 **India-Focused Analysis**

**Immediate Crypto Impact:**
- INR volatility affects crypto entry/exit timing
- 30% VDA tax reminder: Factor this into profit calculations
- P2P premium may fluctuate ±2-3%

**Stock Market Outlook:**
- Nifty direction: 65% probability of positive bias
- Sector rotation: Watch banking and FMCG
- FII flows remain the key driver

**Actionable Insight:** 
- Short-term traders: Wait for clarity, maintain 50% cash
- Long-term: SIP strategy remains optimal

**Tax Note:** Remember LTCG of 10% above ₹1 lakh for stocks held >1 year.""",

        "crypto_relevant": f"""₿ **Crypto-Specific Analysis**

**Trading Implications:**
- BTC dominance likely to shift: Watch for altcoin opportunities
- On-chain metrics suggest accumulation phase
- RSI across majors: Neutral to slightly overbought

**For Indian Traders:**
- Entry points: Consider DCA at current levels
- Stop-loss: 10-12% trailing for volatile assets
- Avoid overleveraging given 30% tax on gains

**Probability Assessment:**
- 60% chance of continued uptrend (7-day horizon)
- 25% consolidation
- 15% correction >10%

**Contrarian View:** Retail FOMO often marks local tops. Watch funding rates for overleveraged signals.""",

        "geopolitics": f"""🌍 **Geopolitical Risk Assessment**

**Safe Haven Dynamics:**
- BTC as digital gold narrative: Strengthens during uncertainty
- Gold correlation historically 0.3-0.5 during crises
- INR depreciation risk: Consider crypto as hedge

**Indian Market Impact:**
- Defense stocks: Potential short-term boost
- IT sector: May see volatility in client spending
- Banking: Watch for risk-off sentiment

**Recommended Stance:**
- Crypto: Maintain core BTC/ETH positions
- Stocks: Defensive sectors (pharma, FMCG) preferred
- Cash: Keep 20-30% dry powder

**Timeline:** Geopolitical events typically resolve or escalate within 2-4 weeks. Plan accordingly."""
    }
    
    return analyses.get(category, analyses["world_economies"])

async def generate_daily_decision(market_data: dict, news_summary: str) -> dict:
    """Generate AI-powered daily investment decision"""
    if not EMERGENT_LLM_KEY:
        return generate_mock_decision(market_data)
    
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        system_prompt = """You are an expert investment advisor for Indian investors. 
Provide data-driven recommendations considering:
- Technical indicators (RSI, MACD, Bollinger Bands)
- Fundamental analysis for stocks
- On-chain metrics for crypto
- India-specific factors (INR, taxes, regulations)
- Risk management with probability estimates

Your output must be structured and actionable. Never give absolute predictions."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"daily_decision_{datetime.now().strftime('%Y%m%d')}",
            system_message=system_prompt
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        
        prompt = f"""Based on current market conditions, provide today's investment decision:

MARKET DATA:
- BTC: ₹{market_data['btc_price']:,.0f} (RSI: {market_data['btc_rsi']}, 24h: {market_data['btc_change']}%)
- ETH: ₹{market_data['eth_price']:,.0f} (RSI: {market_data['eth_rsi']}, 24h: {market_data['eth_change']}%)
- Nifty 50: {market_data['nifty_level']:,.0f} (Change: {market_data['nifty_change']}%)
- INR/USD: {market_data['inr_usd']}

NEWS SUMMARY:
{news_summary}

Provide:
1. TODAY'S RECOMMENDATION: Crypto / Stocks / Both / Hold
2. CONFIDENCE LEVEL: X%
3. DETAILED REASONING (3-4 paragraphs covering technical, fundamental, and macro factors)
4. SPECIFIC ALLOCATIONS if not Hold
5. KEY RISKS AND STOP-LOSS LEVELS
6. TIMELINE (day trade / swing / position)

Format as JSON with keys: recommendation, confidence, reasoning, allocations, risks, timeline"""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Try to parse JSON, fallback to structured response
        try:
            import json
            return json.loads(response)
        except:
            return {
                "recommendation": "Hold",
                "confidence": 65,
                "reasoning": response,
                "allocations": {},
                "risks": ["Market volatility", "Regulatory uncertainty"],
                "timeline": "Wait for clarity"
            }
    except Exception as e:
        logger.error(f"Decision generation error: {e}")
        return generate_mock_decision(market_data)

def generate_mock_decision(market_data: dict) -> dict:
    """Generate mock decision when AI is unavailable"""
    btc_rsi = market_data.get('btc_rsi', 55)
    nifty_change = market_data.get('nifty_change', 0.5)
    
    if btc_rsi > 70:
        recommendation = "Hold"
        reasoning = """**Market Assessment: HOLD**

Based on current technical indicators, the market shows signs of being overbought. Bitcoin's RSI at {btc_rsi} suggests potential for a short-term pullback.

**Technical Analysis:**
The crypto market is showing exhaustion signals after the recent rally. MACD histogram is flattening, indicating momentum loss. Bollinger Bands are expanding, suggesting increased volatility ahead. For stocks, Nifty remains in an uptrend but faces resistance at current levels.

**Fundamental Considerations:**
While long-term fundamentals remain strong for quality assets, the risk-reward at current levels doesn't favor aggressive positioning. The 30% VDA tax in India means you need significant moves to profit after taxes. Better opportunities may emerge after consolidation.

**Macro Environment:**
Global liquidity conditions are supportive, but near-term uncertainty from central bank communications warrants caution. INR stability is a positive, but watch for sudden moves.

**Recommendation:**
Maintain current positions. New capital should wait for RSI to cool below 60 for crypto entries. For stocks, accumulate quality names on 3-5% dips. Keep 30% portfolio in cash for opportunities."""
    elif btc_rsi < 35:
        recommendation = "Crypto"
        reasoning = """**Market Assessment: FAVOR CRYPTO**

Oversold conditions in cryptocurrency markets present accumulation opportunities for tactical traders.

**Technical Analysis:**
Bitcoin's RSI at {btc_rsi} indicates oversold territory. Historical data shows BTC recovers 70% of the time within 2 weeks when RSI drops below 35. Support levels are holding, and volume profile suggests accumulation by larger players.

**Entry Strategy:**
- Deploy 30-40% of allocated crypto capital now
- Reserve 60-70% for potential further dips
- Focus on BTC (60%) and ETH (40%) for safety
- Avoid high-beta altcoins until trend confirms

**Risk Management:**
- Stop-loss: 12% below entry
- Take profit: Scale out at 15%, 25%, 35% gains
- Position size: Max 5% of portfolio per trade

**Tax Consideration:**
With 30% VDA tax, aim for minimum 15% gross profit to achieve meaningful after-tax returns. Short-term trading costs are high - consider if swing trading (1-4 weeks) might be more tax-efficient."""
    else:
        recommendation = "Both"
        reasoning = """**Market Assessment: BALANCED ALLOCATION**

Current market conditions favor a diversified approach across both crypto and equities.

**Crypto Outlook (Short-term Focus):**
Technical indicators are neutral, providing reasonable entry points. BTC dominance is stable, suggesting altcoin opportunities may emerge. Key levels to watch: BTC support at ₹70L, resistance at ₹75L. For tactical trades, consider SOL and ETH for their ecosystem growth.

**Stock Market (Long-term Focus):**
Nifty fundamentals remain strong with {nifty_change}% movement today. Banking sector offers value with P/E below historical averages. IT sector may face headwinds from global spending cuts but quality names like TCS and Infy are accumulation candidates on dips.

**Recommended Allocation:**
- Crypto (40%): BTC 50%, ETH 30%, SOL 20%
- Stocks (60%): Banking 30%, IT 25%, FMCG 25%, Pharma 20%

**Risk Framework:**
- Crypto stop-loss: 10% trailing
- Stock stop-loss: 7% from entry
- Rebalance monthly or on 15%+ moves

**Timeline:** 
- Crypto positions: 1-4 week holding for swing trades
- Stock positions: 6-12 month minimum for LTCG benefits"""
    
    return {
        "recommendation": recommendation,
        "confidence": 68,
        "reasoning": reasoning.format(btc_rsi=btc_rsi, nifty_change=nifty_change),
        "allocations": {
            "crypto": {"BTC": 50, "ETH": 30, "SOL": 20} if recommendation in ["Crypto", "Both"] else {},
            "stocks": {"HDFCBANK": 25, "TCS": 25, "HINDUNILVR": 25, "SUNPHARMA": 25} if recommendation in ["Stocks", "Both"] else {}
        },
        "risks": [
            "Regulatory changes (SEBI/RBI crypto stance)",
            "Global macro deterioration",
            "INR volatility affecting returns",
            "30% VDA tax impact on short-term trades"
        ],
        "timeline": "Swing trade (1-4 weeks) for crypto, Position (6-12 months) for stocks"
    }

async def generate_portfolio_analysis(holdings: List[dict], trades: List[dict]) -> dict:
    """Generate AI analysis for user portfolio"""
    if not holdings:
        return {
            "summary": "No holdings to analyze. Start by adding trades to your portfolio.",
            "suggestions": ["Add your first trade to begin tracking", "Consider starting with blue-chip crypto (BTC, ETH) or stocks (HDFC, TCS)"],
            "risk_score": 0,
            "diversification_score": 0
        }
    
    # Calculate basic metrics
    total_value = sum(h.get('current_value', 0) for h in holdings)
    crypto_value = sum(h.get('current_value', 0) for h in holdings if h.get('asset_type') == 'crypto')
    stock_value = sum(h.get('current_value', 0) for h in holdings if h.get('asset_type') == 'stock')
    
    crypto_pct = (crypto_value / total_value * 100) if total_value > 0 else 0
    stock_pct = (stock_value / total_value * 100) if total_value > 0 else 0
    
    num_assets = len(holdings)
    
    # Risk score based on allocation
    risk_score = min(100, int(crypto_pct * 0.8 + (100 - num_assets * 5)))
    diversification_score = min(100, int(num_assets * 10 + min(crypto_pct, stock_pct) * 0.5))
    
    suggestions = []
    if crypto_pct > 70:
        suggestions.append("High crypto allocation ({}%). Consider adding defensive stocks for balance.".format(int(crypto_pct)))
    if stock_pct > 80:
        suggestions.append("Conservative allocation. Consider small crypto allocation (5-15%) for growth potential.")
    if num_assets < 5:
        suggestions.append("Low diversification. Aim for 8-12 assets across sectors.")
    if num_assets > 20:
        suggestions.append("Over-diversified. Consider consolidating into highest conviction positions.")
    
    return {
        "summary": f"Portfolio value: ₹{total_value:,.0f} | Crypto: {crypto_pct:.1f}% | Stocks: {stock_pct:.1f}%",
        "suggestions": suggestions if suggestions else ["Portfolio is reasonably balanced. Continue monitoring."],
        "risk_score": risk_score,
        "diversification_score": diversification_score,
        "metrics": {
            "total_value": total_value,
            "crypto_allocation": crypto_pct,
            "stock_allocation": stock_pct,
            "num_holdings": num_assets
        }
    }

# ==================== API ROUTES ====================

# Health check
@api_router.get("/")
async def root():
    return {"message": "Indian Investment Guidance API", "status": "healthy", "version": "1.0.0"}

# ==================== AUTH ROUTES ====================

@api_router.get("/auth/check")
async def check_auth(request: Request):
    """Check if user is authenticated"""
    user = await get_current_user(request)
    if user:
        return {"authenticated": True, "user": user.dict()}
    return {"authenticated": False}

@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get current user info"""
    user = await require_auth(request)
    return user.dict()

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange session_id for session_token"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Call Emergent auth API
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
    
    # Create or get user
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
            "risk_profile": "moderate"
        }
        await db.users.insert_one(new_user)
    
    # Store session
    session_token = user_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc)
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=7 * 24 * 60 * 60,
        path="/"
    )
    
    # Get full user data
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    return {
        "success": True,
        "user": user_doc,
        "session_token": session_token
    }

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user"""
    session_token = await get_session_token(request)
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"success": True}

# ==================== MARKET DATA ROUTES ====================

@api_router.get("/crypto/prices")
async def get_crypto_prices():
    """Get current crypto prices (mock data)"""
    # Add some randomness to simulate real-time data
    prices = {}
    for symbol, data in MOCK_CRYPTO_DATA.items():
        variation = random.uniform(-0.5, 0.5)
        prices[symbol] = {
            **data,
            "price_inr": data["price_inr"] * (1 + variation/100),
            "change_24h": data["change_24h"] + random.uniform(-0.3, 0.3),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    return {"data": prices, "currency": "INR", "source": "mock"}

@api_router.get("/crypto/{symbol}")
async def get_crypto_detail(symbol: str):
    """Get detailed crypto data for a specific symbol"""
    symbol = symbol.upper()
    if symbol not in MOCK_CRYPTO_DATA:
        raise HTTPException(status_code=404, detail=f"Crypto {symbol} not found")
    
    data = MOCK_CRYPTO_DATA[symbol]
    variation = random.uniform(-0.3, 0.3)
    
    return {
        "symbol": symbol,
        **data,
        "price_inr": data["price_inr"] * (1 + variation/100),
        "technicals": {
            "rsi": data["rsi"],
            "macd": "bullish" if data["rsi"] > 50 else "bearish",
            "bollinger": "middle" if 40 < data["rsi"] < 60 else ("upper" if data["rsi"] > 60 else "lower"),
            "support_inr": data["price_inr"] * 0.92,
            "resistance_inr": data["price_inr"] * 1.08
        },
        "currency": "INR",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

@api_router.get("/stocks/prices")
async def get_stock_prices():
    """Get current stock prices (mock data)"""
    prices = {}
    for symbol, data in MOCK_STOCK_DATA.items():
        variation = random.uniform(-0.3, 0.3)
        prices[symbol] = {
            **data,
            "price_inr": data["price_inr"] * (1 + variation/100),
            "change_24h": data["change_24h"] + random.uniform(-0.2, 0.2),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    return {"data": prices, "currency": "INR", "source": "mock"}

@api_router.get("/stocks/{symbol}")
async def get_stock_detail(symbol: str):
    """Get detailed stock data for a specific symbol"""
    symbol = symbol.upper()
    if symbol not in MOCK_STOCK_DATA:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")
    
    data = MOCK_STOCK_DATA[symbol]
    variation = random.uniform(-0.2, 0.2)
    
    return {
        "symbol": symbol,
        **data,
        "price_inr": data["price_inr"] * (1 + variation/100),
        "fundamentals": {
            "pe_ratio": data["pe_ratio"],
            "eps": data["eps"],
            "debt_equity": random.uniform(0.2, 1.5),
            "revenue_growth": random.uniform(5, 25),
            "dividend_yield": random.uniform(0.5, 3.5)
        },
        "currency": "INR",
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

# ==================== NEWS ROUTES ====================

@api_router.get("/news")
async def get_news(category: Optional[str] = None, search: Optional[str] = None, use_ai: bool = False):
    """Get news with optional filtering. Set use_ai=true for real AI analysis (slower)."""
    news = MOCK_NEWS_DATA.copy()
    
    if category:
        news = [n for n in news if n["category"] == category]
    
    if search:
        search_lower = search.lower()
        news = [n for n in news if search_lower in n["title"].lower() or search_lower in n["summary"].lower()]
    
    # Generate analysis for each news item
    news_with_analysis = []
    for item in news[:10]:
        if use_ai:
            analysis = await generate_ai_analysis(item)
        else:
            analysis = generate_mock_analysis(item)
        news_with_analysis.append({
            **item,
            "published_at": item["published_at"].isoformat(),
            "ai_analysis": analysis
        })
    
    return {"news": news_with_analysis, "total": len(news_with_analysis)}

@api_router.get("/news/categories")
async def get_news_categories():
    """Get available news categories"""
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
async def get_daily_decision(use_ai: bool = False):
    """Get today's investment decision. Set use_ai=true for real AI analysis (slower)."""
    # Prepare market data
    market_data = {
        "btc_price": MOCK_CRYPTO_DATA["BTC"]["price_inr"],
        "btc_rsi": MOCK_CRYPTO_DATA["BTC"]["rsi"],
        "btc_change": MOCK_CRYPTO_DATA["BTC"]["change_24h"],
        "eth_price": MOCK_CRYPTO_DATA["ETH"]["price_inr"],
        "eth_rsi": MOCK_CRYPTO_DATA["ETH"]["rsi"],
        "eth_change": MOCK_CRYPTO_DATA["ETH"]["change_24h"],
        "nifty_level": 24500,
        "nifty_change": 0.8,
        "inr_usd": 83.25
    }
    
    # Prepare news summary
    news_summary = "\n".join([f"- {n['title']}" for n in MOCK_NEWS_DATA[:5]])
    
    if use_ai:
        decision = await generate_daily_decision(market_data, news_summary)
    else:
        decision = generate_mock_decision(market_data)
    
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "time_ist": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%H:%M IST"),
        "market_snapshot": market_data,
        "decision": decision
    }

# ==================== SIMULATOR ROUTES ====================

@api_router.post("/simulator/trade")
async def execute_virtual_trade(trade: TradeCreate, request: Request):
    """Execute a virtual trade"""
    user = await require_auth(request)
    
    # Get current price
    if trade.asset_type == "crypto":
        if trade.asset_symbol not in MOCK_CRYPTO_DATA:
            raise HTTPException(status_code=404, detail="Asset not found")
        current_price = MOCK_CRYPTO_DATA[trade.asset_symbol]["price_inr"]
    else:
        if trade.asset_symbol not in MOCK_STOCK_DATA:
            raise HTTPException(status_code=404, detail="Asset not found")
        current_price = MOCK_STOCK_DATA[trade.asset_symbol]["price_inr"]
    
    # Calculate total value
    total_value = trade.quantity * trade.price_inr
    
    # Create trade record
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
        "is_virtual": trade.is_virtual,
        "notes": trade.notes
    }
    
    await db.trades.insert_one(trade_record)
    
    # Remove _id for response
    trade_record.pop("_id", None)
    trade_record["trade_date"] = trade_record["trade_date"].isoformat()
    
    return {"success": True, "trade": trade_record}

@api_router.get("/simulator/portfolio")
async def get_simulator_portfolio(request: Request):
    """Get virtual portfolio"""
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": True},
        {"_id": 0}
    ).to_list(1000)
    
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
                "avg_price": 0,
                "total_invested": 0
            }
        
        if trade["trade_type"] == "buy":
            holdings[key]["total_invested"] += trade["total_value_inr"]
            holdings[key]["quantity"] += trade["quantity"]
        else:
            holdings[key]["quantity"] -= trade["quantity"]
            holdings[key]["total_invested"] -= trade["total_value_inr"]
    
    # Calculate current values and P&L
    portfolio = []
    total_value = 0
    total_invested = 0
    
    for key, holding in holdings.items():
        if holding["quantity"] <= 0:
            continue
        
        # Get current price
        if holding["asset_type"] == "crypto":
            current_price = MOCK_CRYPTO_DATA.get(holding["asset_symbol"], {}).get("price_inr", 0)
        else:
            current_price = MOCK_STOCK_DATA.get(holding["asset_symbol"], {}).get("price_inr", 0)
        
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
    
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    
    return {
        "holdings": portfolio,
        "summary": {
            "total_value": total_value,
            "total_invested": total_invested,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "num_holdings": len(portfolio)
        },
        "trades": [{**t, "trade_date": t["trade_date"].isoformat() if isinstance(t["trade_date"], datetime) else t["trade_date"]} for t in trades[-20:]]
    }

@api_router.get("/simulator/suggestions")
async def get_trade_suggestions(request: Request, asset_type: str = "crypto"):
    """Get AI-powered trade suggestions"""
    user = await require_auth(request)
    
    if asset_type == "crypto":
        # Suggest based on RSI and momentum
        suggestions = []
        for symbol, data in MOCK_CRYPTO_DATA.items():
            if data["rsi"] < 40:
                suggestions.append({
                    "symbol": symbol,
                    "name": data["name"],
                    "action": "BUY",
                    "reason": f"Oversold (RSI: {data['rsi']})",
                    "suggested_allocation": "3-5%",
                    "stop_loss": "10% trailing",
                    "confidence": 65 + (40 - data["rsi"])
                })
            elif data["rsi"] > 70:
                suggestions.append({
                    "symbol": symbol,
                    "name": data["name"],
                    "action": "SELL/REDUCE",
                    "reason": f"Overbought (RSI: {data['rsi']})",
                    "suggested_allocation": "Reduce by 50%",
                    "stop_loss": "N/A",
                    "confidence": 60 + (data["rsi"] - 70)
                })
        
        return {"suggestions": suggestions[:5], "asset_type": "crypto"}
    else:
        # Stock suggestions based on PE and sector
        suggestions = []
        for symbol, data in MOCK_STOCK_DATA.items():
            if data["pe_ratio"] < 20:
                suggestions.append({
                    "symbol": symbol,
                    "name": data["name"],
                    "action": "BUY",
                    "reason": f"Undervalued (P/E: {data['pe_ratio']})",
                    "suggested_allocation": "5-8%",
                    "stop_loss": "7% from entry",
                    "confidence": 70
                })
        
        return {"suggestions": suggestions[:5], "asset_type": "stocks"}

# ==================== PORTFOLIO TRACKER ROUTES ====================

@api_router.post("/portfolio/trade")
async def add_portfolio_trade(trade: TradeCreate, request: Request):
    """Add a real trade to portfolio tracker"""
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
    """Get user's real portfolio"""
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": False},
        {"_id": 0}
    ).to_list(1000)
    
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
    
    for key, holding in holdings.items():
        if holding["quantity"] <= 0:
            continue
        
        if holding["asset_type"] == "crypto":
            current_price = MOCK_CRYPTO_DATA.get(holding["asset_symbol"], {}).get("price_inr", 0)
        else:
            current_price = MOCK_STOCK_DATA.get(holding["asset_symbol"], {}).get("price_inr", 0)
        
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
    
    # Generate AI analysis
    analysis = await generate_portfolio_analysis(portfolio, trades)
    
    return {
        "holdings": portfolio,
        "summary": {
            "total_value": total_value,
            "total_invested": total_invested,
            "total_pnl": total_value - total_invested,
            "total_pnl_pct": ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0,
            "num_holdings": len(portfolio)
        },
        "analysis": analysis,
        "trades": [{**t, "trade_date": t["trade_date"].isoformat() if isinstance(t["trade_date"], datetime) else t["trade_date"]} for t in trades[-20:]]
    }

@api_router.get("/portfolio/history")
async def get_portfolio_history(request: Request, days: int = 30):
    """Get portfolio value history for charts"""
    user = await require_auth(request)
    
    # Generate mock historical data
    history = []
    base_value = 100000
    
    for i in range(days, 0, -1):
        date = datetime.now(timezone.utc) - timedelta(days=i)
        variation = random.uniform(-3, 4)
        base_value = base_value * (1 + variation/100)
        
        history.append({
            "date": date.strftime("%Y-%m-%d"),
            "value": round(base_value, 2),
            "change_pct": round(variation, 2)
        })
    
    return {"history": history, "days": days}

@api_router.get("/portfolio/export")
async def export_portfolio(request: Request):
    """Export portfolio data for tax filing"""
    user = await require_auth(request)
    
    trades = await db.trades.find(
        {"user_id": user.user_id, "is_virtual": False},
        {"_id": 0}
    ).to_list(1000)
    
    # Format for CSV export
    export_data = []
    for trade in trades:
        export_data.append({
            "Date": trade["trade_date"].strftime("%Y-%m-%d") if isinstance(trade["trade_date"], datetime) else trade["trade_date"],
            "Asset Type": trade["asset_type"].upper(),
            "Symbol": trade["asset_symbol"],
            "Name": trade["asset_name"],
            "Trade Type": trade["trade_type"].upper(),
            "Quantity": trade["quantity"],
            "Price (INR)": trade["price_inr"],
            "Total Value (INR)": trade["total_value_inr"],
            "Notes": trade.get("notes", "")
        })
    
    return {
        "data": export_data,
        "tax_notes": {
            "crypto_tax": "30% flat tax on VDA gains (no loss offset allowed)",
            "stock_ltcg": "10% on gains above ₹1 lakh for holdings >1 year",
            "stock_stcg": "15% for holdings <1 year",
            "tds": "1% TDS on crypto transactions above ₹10,000"
        }
    }

# ==================== WATCHLIST ROUTES ====================

@api_router.post("/watchlist")
async def add_to_watchlist(item: WatchlistCreate, request: Request):
    """Add asset to watchlist"""
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
    """Get user's watchlist with current prices"""
    user = await require_auth(request)
    
    items = await db.watchlist.find(
        {"user_id": user.user_id},
        {"_id": 0}
    ).to_list(100)
    
    # Add current prices and rankings
    watchlist = []
    for item in items:
        if item["asset_type"] == "crypto":
            data = MOCK_CRYPTO_DATA.get(item["asset_symbol"], {})
            current_price = data.get("price_inr", 0)
            change = data.get("change_24h", 0)
            rsi = data.get("rsi", 50)
        else:
            data = MOCK_STOCK_DATA.get(item["asset_symbol"], {})
            current_price = data.get("price_inr", 0)
            change = data.get("change_24h", 0)
            rsi = 50  # Stocks don't have RSI in mock
        
        # Calculate volatility-adjusted score
        volatility_score = abs(change) * 10
        momentum_score = 100 - abs(rsi - 50) * 2
        
        watchlist.append({
            **item,
            "added_at": item["added_at"].isoformat() if isinstance(item["added_at"], datetime) else item["added_at"],
            "current_price": current_price,
            "change_24h": change,
            "ai_score": round((momentum_score + (100 - volatility_score)) / 2, 1)
        })
    
    # Sort by AI score
    watchlist.sort(key=lambda x: x["ai_score"], reverse=True)
    
    return {"watchlist": watchlist}

@api_router.delete("/watchlist/{item_id}")
async def remove_from_watchlist(item_id: str, request: Request):
    """Remove asset from watchlist"""
    user = await require_auth(request)
    
    result = await db.watchlist.delete_one({
        "item_id": item_id,
        "user_id": user.user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return {"success": True}

# ==================== USER SETTINGS ROUTES ====================

@api_router.put("/user/capital")
async def update_capital(capital_update: CapitalUpdate, request: Request):
    """Update user's virtual capital"""
    user = await require_auth(request)
    
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"capital": capital_update.capital}}
    )
    
    return {"success": True, "capital": capital_update.capital}

@api_router.get("/user/settings")
async def get_user_settings(request: Request):
    """Get user settings"""
    user = await require_auth(request)
    
    return {
        "capital": user.capital,
        "risk_profile": user.risk_profile,
        "email": user.email,
        "name": user.name
    }

# ==================== EDUCATION ROUTES ====================

@api_router.get("/education/tips")
async def get_education_tips():
    """Get educational content for Indian investors"""
    return {
        "tips": [
            {
                "id": "crypto_tax",
                "title": "Crypto Taxation in India",
                "content": "As per the 2022 budget, all crypto gains are taxed at 30% flat rate. No deductions allowed except cost of acquisition. 1% TDS applies on transactions above ₹10,000.",
                "category": "tax"
            },
            {
                "id": "stock_tax",
                "title": "Stock Market Taxation",
                "content": "LTCG (>1 year): 10% on gains above ₹1 lakh. STCG (<1 year): 15%. Dividend income taxed at slab rate.",
                "category": "tax"
            },
            {
                "id": "risk_disclaimer",
                "title": "Risk Disclaimer",
                "content": "This app provides educational information only. All investments carry risk. Past performance doesn't guarantee future results. Always do your own research (DYOR).",
                "category": "disclaimer"
            },
            {
                "id": "diversification",
                "title": "Portfolio Diversification",
                "content": "Don't put all eggs in one basket. Recommended: 5-15% crypto, 60-80% stocks, 10-20% debt. Adjust based on risk appetite and age.",
                "category": "strategy"
            },
            {
                "id": "stop_loss",
                "title": "Stop Loss Importance",
                "content": "Always set stop losses. Recommended: 10-15% for crypto, 7-10% for stocks. Trailing stop loss helps lock in profits.",
                "category": "strategy"
            }
        ]
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
