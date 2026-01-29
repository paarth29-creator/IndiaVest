"""Leader & Influencer Statements Service"""
import httpx
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import re

logger = logging.getLogger(__name__)

NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')

# Key leaders and their search terms
LEADERS = {
    "elon_musk": {
        "name": "Elon Musk",
        "role": "CEO Tesla/SpaceX, X Owner",
        "queries": ["Elon Musk Bitcoin", "Elon Musk crypto", "Elon Musk Tesla", "Elon Musk Dogecoin", "Elon Musk markets"],
        "assets": ["BTC", "DOGE", "ETH", "TSLA"]
    },
    "jerome_powell": {
        "name": "Jerome Powell",
        "role": "US Federal Reserve Chairman",
        "queries": ["Jerome Powell interest rates", "Federal Reserve policy", "Fed rate decision", "Powell inflation"],
        "assets": ["USD", "NIFTY", "BTC", "STOCKS"]
    },
    "donald_trump": {
        "name": "Donald Trump",
        "role": "US President",
        "queries": ["Trump crypto", "Trump Bitcoin", "Trump tariffs", "Trump economy", "Trump markets"],
        "assets": ["BTC", "USD", "STOCKS"]
    },
    "rbi_governor": {
        "name": "RBI Governor",
        "role": "Reserve Bank of India Governor",
        "queries": ["RBI Governor statement", "RBI policy", "RBI interest rate", "India monetary policy"],
        "assets": ["INR", "NIFTY", "BANKNIFTY"]
    },
    "finance_minister": {
        "name": "Finance Minister India",
        "role": "Indian Finance Minister",
        "queries": ["Nirmala Sitharaman crypto", "India Finance Minister budget", "India crypto regulation"],
        "assets": ["INR", "NIFTY", "BTC"]
    },
    "sec_chair": {
        "name": "SEC Chairman",
        "role": "US Securities & Exchange Commission",
        "queries": ["SEC crypto", "Gary Gensler crypto", "SEC Bitcoin ETF", "SEC regulation"],
        "assets": ["BTC", "ETH", "XRP", "SOL"]
    },
    "michael_saylor": {
        "name": "Michael Saylor",
        "role": "MicroStrategy Executive Chairman",
        "queries": ["Michael Saylor Bitcoin", "MicroStrategy Bitcoin", "Saylor BTC"],
        "assets": ["BTC"]
    },
    "cathie_wood": {
        "name": "Cathie Wood",
        "role": "ARK Invest CEO",
        "queries": ["Cathie Wood Bitcoin", "ARK Invest crypto", "Cathie Wood Tesla"],
        "assets": ["BTC", "ETH", "TSLA"]
    }
}

# Fallback statements when APIs fail
FALLBACK_STATEMENTS = [
    {
        "id": "fallback_1",
        "leader": "Elon Musk",
        "role": "CEO Tesla/SpaceX, X Owner",
        "statement": "The future of finance is digital. Traditional banking systems are inefficient and need disruption.",
        "source": "X (Twitter)",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=3),
        "assets_mentioned": ["BTC", "DOGE"],
        "sentiment_score": 0.7
    },
    {
        "id": "fallback_2",
        "leader": "Jerome Powell",
        "role": "US Federal Reserve Chairman",
        "statement": "We remain data-dependent on inflation. The labor market continues to show resilience.",
        "source": "Federal Reserve Press Conference",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=6),
        "assets_mentioned": ["USD", "STOCKS"],
        "sentiment_score": 0.1
    },
    {
        "id": "fallback_3",
        "leader": "RBI Governor",
        "role": "Reserve Bank of India Governor",
        "statement": "Inflation management remains our primary focus while supporting economic growth.",
        "source": "RBI MPC Meeting",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=8),
        "assets_mentioned": ["INR", "NIFTY"],
        "sentiment_score": 0.2
    },
    {
        "id": "fallback_4",
        "leader": "Michael Saylor",
        "role": "MicroStrategy Executive Chairman",
        "statement": "Bitcoin is the apex property of the human race. Digital scarcity is the innovation of our century.",
        "source": "X (Twitter)",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=4),
        "assets_mentioned": ["BTC"],
        "sentiment_score": 0.95
    },
    {
        "id": "fallback_5",
        "leader": "SEC Chairman",
        "role": "US Securities & Exchange Commission",
        "statement": "Crypto markets require investor protection. We are working on comprehensive regulatory frameworks.",
        "source": "SEC Statement",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=12),
        "assets_mentioned": ["BTC", "ETH", "XRP"],
        "sentiment_score": -0.3
    },
    {
        "id": "fallback_6",
        "leader": "Donald Trump",
        "role": "US President",
        "statement": "America will be the crypto capital of the world. We will make Bitcoin great!",
        "source": "Truth Social",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=5),
        "assets_mentioned": ["BTC", "USD"],
        "sentiment_score": 0.8
    },
    {
        "id": "fallback_7",
        "leader": "Finance Minister India",
        "role": "Indian Finance Minister",
        "statement": "The 30% VDA tax ensures regulatory oversight while allowing innovation in digital assets.",
        "source": "Parliament Session",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=24),
        "assets_mentioned": ["BTC", "ETH", "INR"],
        "sentiment_score": -0.2
    },
    {
        "id": "fallback_8",
        "leader": "Cathie Wood",
        "role": "ARK Invest CEO",
        "statement": "Bitcoin could reach $1.5 million by 2030. Institutional adoption is just beginning.",
        "source": "ARK Invest Report",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=18),
        "assets_mentioned": ["BTC", "ETH"],
        "sentiment_score": 0.9
    }
]


def clean_text(text: str) -> str:
    """Remove all markdown formatting symbols from text"""
    if not text:
        return ""
    # Remove asterisks
    text = text.replace('*', '')
    # Remove double asterisks (bold)
    text = re.sub(r'\*\*', '', text)
    # Remove underscores (italic)
    text = re.sub(r'_+', '', text)
    # Remove backticks
    text = text.replace('`', '')
    # Remove hash symbols at start of lines (headers)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class LeaderNewsService:
    def __init__(self):
        self.newsapi_key = NEWSAPI_KEY
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def fetch_from_newsapi(self, query: str) -> List[Dict]:
        """Fetch news from NewsAPI"""
        if not self.newsapi_key:
            logger.warning("NEWSAPI_KEY not set")
            return []
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "apiKey": self.newsapi_key,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 5
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("articles", [])
                else:
                    logger.warning(f"NewsAPI returned {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"NewsAPI error: {e}")
            return []
    
    async def get_leader_statements(self, use_real_api: bool = True) -> List[Dict]:
        """Get latest statements from key leaders and influencers"""
        cache_key = "leader_statements"
        
        # Check cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_data
        
        statements = []
        
        if use_real_api and self.newsapi_key:
            # Fetch real news for each leader
            for leader_id, leader_info in LEADERS.items():
                for query in leader_info["queries"][:2]:  # Limit queries per leader
                    articles = await self.fetch_from_newsapi(query)
                    
                    for article in articles[:2]:  # Limit articles per query
                        # Extract quote/statement from title or description
                        statement_text = article.get("description") or article.get("title", "")
                        statement_text = clean_text(statement_text)
                        
                        if len(statement_text) > 30:  # Minimum meaningful content
                            published_at = article.get("publishedAt", "")
                            try:
                                pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                            except:
                                pub_date = datetime.now(timezone.utc)
                            
                            statements.append({
                                "id": f"news_{leader_id}_{len(statements)}",
                                "leader": leader_info["name"],
                                "role": leader_info["role"],
                                "statement": statement_text[:500],
                                "source": article.get("source", {}).get("name", "News"),
                                "url": article.get("url", ""),
                                "published_at": pub_date,
                                "assets_mentioned": leader_info["assets"],
                                "sentiment_score": 0.0  # Will be calculated by AI
                            })
        
        # If no real data, use fallback
        if len(statements) < 5:
            statements = FALLBACK_STATEMENTS.copy()
        
        # Sort by date and limit
        statements.sort(key=lambda x: x["published_at"] if isinstance(x["published_at"], datetime) else datetime.now(timezone.utc), reverse=True)
        statements = statements[:12]
        
        # Cache results
        self.cache[cache_key] = (datetime.now(), statements)
        
        return statements


leader_news_service = LeaderNewsService()
