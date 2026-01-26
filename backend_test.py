#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Indian Investment Guidance App
Tests all public and auth-protected endpoints
"""

import requests
import json
import time
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# Configuration
BACKEND_URL = "http://localhost:8001/api"
TEST_USER_EMAIL = f"test.user.{int(time.time())}@example.com"
TEST_USER_NAME = "Test User"

class BackendTester:
    def __init__(self):
        self.session_token = None
        self.user_id = None
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        if not success and response_data:
            print(f"    Response: {response_data}")
        print()
    
    def create_test_user_and_session(self) -> bool:
        """Create test user and session in MongoDB"""
        print("🔧 Creating test user and session in MongoDB...")
        
        timestamp = int(time.time())
        user_id = f"user_{timestamp}"
        session_token = f"test_session_{timestamp}"
        
        mongo_script = f'''
use('test_database');
var visitorId = '{user_id}';
var sessionToken = '{session_token}';
db.users.insertOne({{
  user_id: visitorId,
  email: '{TEST_USER_EMAIL}',
  name: '{TEST_USER_NAME}',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date(),
  capital: 100000.0,
  risk_profile: 'moderate'
}});
db.user_sessions.insertOne({{
  user_id: visitorId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
}});
print('SUCCESS: User and session created');
print('Session token: ' + sessionToken);
print('User ID: ' + visitorId);
'''
        
        try:
            result = subprocess.run(
                ['mongosh', '--eval', mongo_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and 'SUCCESS' in result.stdout:
                self.session_token = session_token
                self.user_id = user_id
                self.log_test("Create test user and session", True, f"User ID: {user_id}")
                return True
            else:
                self.log_test("Create test user and session", False, f"MongoDB error: {result.stderr}")
                return False
                
        except Exception as e:
            self.log_test("Create test user and session", False, f"Exception: {str(e)}")
            return False
    
    def test_health_check(self):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    self.log_test("Health check API", True, f"Status: {data.get('status')}")
                else:
                    self.log_test("Health check API", False, "Status not healthy", data)
            else:
                self.log_test("Health check API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Health check API", False, f"Exception: {str(e)}")
    
    def test_crypto_prices(self):
        """Test crypto prices endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/crypto/prices", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                crypto_data = data.get("data", {})
                
                if len(crypto_data) >= 20:
                    # Check if BTC and ETH are present with INR prices
                    btc_data = crypto_data.get("BTC", {})
                    eth_data = crypto_data.get("ETH", {})
                    
                    if btc_data.get("price_inr") and eth_data.get("price_inr"):
                        self.log_test("Crypto prices API", True, f"Found {len(crypto_data)} cryptos with INR prices")
                    else:
                        self.log_test("Crypto prices API", False, "Missing BTC or ETH price data")
                else:
                    self.log_test("Crypto prices API", False, f"Only {len(crypto_data)} cryptos found, expected 20+")
            else:
                self.log_test("Crypto prices API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Crypto prices API", False, f"Exception: {str(e)}")
    
    def test_crypto_detail(self):
        """Test individual crypto detail endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/crypto/BTC", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["symbol", "name", "price_inr", "technicals"]
                if all(field in data for field in required_fields):
                    self.log_test("Crypto detail API (BTC)", True, f"Price: ₹{data.get('price_inr', 0):,.0f}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Crypto detail API (BTC)", False, f"Missing fields: {missing}")
            else:
                self.log_test("Crypto detail API (BTC)", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Crypto detail API (BTC)", False, f"Exception: {str(e)}")
    
    def test_stock_prices(self):
        """Test stock prices endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/stocks/prices", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                stock_data = data.get("data", {})
                
                if len(stock_data) >= 15:  # Nifty 50 subset
                    # Check if major stocks are present
                    tcs_data = stock_data.get("TCS", {})
                    reliance_data = stock_data.get("RELIANCE", {})
                    
                    if tcs_data.get("price_inr") and reliance_data.get("price_inr"):
                        self.log_test("Stock prices API", True, f"Found {len(stock_data)} stocks with INR prices")
                    else:
                        self.log_test("Stock prices API", False, "Missing TCS or RELIANCE price data")
                else:
                    self.log_test("Stock prices API", False, f"Only {len(stock_data)} stocks found, expected 15+")
            else:
                self.log_test("Stock prices API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Stock prices API", False, f"Exception: {str(e)}")
    
    def test_stock_detail(self):
        """Test individual stock detail endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/stocks/TCS", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["symbol", "name", "price_inr", "fundamentals"]
                if all(field in data for field in required_fields):
                    self.log_test("Stock detail API (TCS)", True, f"Price: ₹{data.get('price_inr', 0):,.0f}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Stock detail API (TCS)", False, f"Missing fields: {missing}")
            else:
                self.log_test("Stock detail API (TCS)", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Stock detail API (TCS)", False, f"Exception: {str(e)}")
    
    def test_news_api(self):
        """Test news API with AI analysis"""
        try:
            response = requests.get(f"{BACKEND_URL}/news", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                news_items = data.get("news", [])
                
                if len(news_items) >= 10:
                    # Check if news items have AI analysis
                    first_item = news_items[0]
                    required_fields = ["title", "source", "category", "ai_analysis"]
                    
                    if all(field in first_item for field in required_fields):
                        ai_analysis = first_item.get("ai_analysis", "")
                        if len(ai_analysis) > 100:  # Substantial analysis
                            self.log_test("News API with AI analysis", True, f"Found {len(news_items)} news items with AI analysis")
                        else:
                            self.log_test("News API with AI analysis", False, "AI analysis too short or missing")
                    else:
                        missing = [f for f in required_fields if f not in first_item]
                        self.log_test("News API with AI analysis", False, f"Missing fields: {missing}")
                else:
                    self.log_test("News API with AI analysis", False, f"Only {len(news_items)} news items found, expected 10+")
            else:
                self.log_test("News API with AI analysis", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("News API with AI analysis", False, f"Exception: {str(e)}")
    
    def test_news_categories(self):
        """Test news categories endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/news/categories", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                categories = data.get("categories", [])
                
                if len(categories) >= 4:
                    category_ids = [cat.get("id") for cat in categories]
                    expected_categories = ["world_economies", "india_specific", "crypto_relevant", "geopolitics"]
                    
                    if all(cat in category_ids for cat in expected_categories):
                        self.log_test("News categories API", True, f"Found {len(categories)} categories")
                    else:
                        self.log_test("News categories API", False, f"Missing expected categories")
                else:
                    self.log_test("News categories API", False, f"Only {len(categories)} categories found")
            else:
                self.log_test("News categories API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("News categories API", False, f"Exception: {str(e)}")
    
    def test_daily_decision(self):
        """Test daily decision API"""
        try:
            response = requests.get(f"{BACKEND_URL}/decision/today", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["date", "market_snapshot", "decision"]
                if all(field in data for field in required_fields):
                    decision = data.get("decision", {})
                    decision_fields = ["recommendation", "confidence", "reasoning"]
                    
                    if all(field in decision for field in decision_fields):
                        confidence = decision.get("confidence", 0)
                        self.log_test("Daily decision API", True, f"Recommendation: {decision.get('recommendation')}, Confidence: {confidence}%")
                    else:
                        missing = [f for f in decision_fields if f not in decision]
                        self.log_test("Daily decision API", False, f"Missing decision fields: {missing}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Daily decision API", False, f"Missing fields: {missing}")
            else:
                self.log_test("Daily decision API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Daily decision API", False, f"Exception: {str(e)}")
    
    def test_education_tips(self):
        """Test education tips endpoint"""
        try:
            response = requests.get(f"{BACKEND_URL}/education/tips", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tips = data.get("tips", [])
                
                if len(tips) >= 5:
                    first_tip = tips[0]
                    required_fields = ["id", "title", "content", "category"]
                    
                    if all(field in first_tip for field in required_fields):
                        self.log_test("Education tips API", True, f"Found {len(tips)} educational tips")
                    else:
                        missing = [f for f in required_fields if f not in first_tip]
                        self.log_test("Education tips API", False, f"Missing fields: {missing}")
                else:
                    self.log_test("Education tips API", False, f"Only {len(tips)} tips found")
            else:
                self.log_test("Education tips API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Education tips API", False, f"Exception: {str(e)}")
    
    def test_auth_me(self):
        """Test auth/me endpoint"""
        if not self.session_token:
            self.log_test("Auth /me API", False, "No session token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(f"{BACKEND_URL}/auth/me", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["user_id", "email", "name"]
                if all(field in data for field in required_fields):
                    if data.get("user_id") == self.user_id:
                        self.log_test("Auth /me API", True, f"User: {data.get('name')} ({data.get('email')})")
                    else:
                        self.log_test("Auth /me API", False, f"User ID mismatch: expected {self.user_id}, got {data.get('user_id')}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Auth /me API", False, f"Missing fields: {missing}")
            elif response.status_code == 401:
                self.log_test("Auth /me API", False, "Authentication failed - invalid token")
            else:
                self.log_test("Auth /me API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Auth /me API", False, f"Exception: {str(e)}")
    
    def test_simulator_portfolio(self):
        """Test simulator portfolio endpoint"""
        if not self.session_token:
            self.log_test("Simulator portfolio API", False, "No session token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(f"{BACKEND_URL}/simulator/portfolio", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["holdings", "summary", "trades"]
                if all(field in data for field in required_fields):
                    summary = data.get("summary", {})
                    self.log_test("Simulator portfolio API", True, f"Portfolio loaded with {summary.get('num_holdings', 0)} holdings")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Simulator portfolio API", False, f"Missing fields: {missing}")
            elif response.status_code == 401:
                self.log_test("Simulator portfolio API", False, "Authentication failed")
            else:
                self.log_test("Simulator portfolio API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Simulator portfolio API", False, f"Exception: {str(e)}")
    
    def test_simulator_trade(self):
        """Test simulator trade execution"""
        if not self.session_token:
            self.log_test("Simulator trade API", False, "No session token available")
            return
            
        try:
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            trade_data = {
                "asset_type": "crypto",
                "asset_symbol": "BTC",
                "asset_name": "Bitcoin",
                "quantity": 0.001,
                "price_inr": 7245000,
                "trade_type": "buy",
                "is_virtual": True,
                "notes": "Test trade from backend testing"
            }
            
            response = requests.post(f"{BACKEND_URL}/simulator/trade", 
                                   headers=headers, 
                                   json=trade_data, 
                                   timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") and "trade" in data:
                    trade = data["trade"]
                    self.log_test("Simulator trade API", True, f"Trade executed: {trade.get('trade_type')} {trade.get('quantity')} {trade.get('asset_symbol')}")
                else:
                    self.log_test("Simulator trade API", False, "Trade execution failed", data)
            elif response.status_code == 401:
                self.log_test("Simulator trade API", False, "Authentication failed")
            else:
                self.log_test("Simulator trade API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Simulator trade API", False, f"Exception: {str(e)}")
    
    def test_portfolio(self):
        """Test real portfolio endpoint"""
        if not self.session_token:
            self.log_test("Portfolio API", False, "No session token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(f"{BACKEND_URL}/portfolio", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ["holdings", "summary", "analysis", "trades"]
                if all(field in data for field in required_fields):
                    summary = data.get("summary", {})
                    analysis = data.get("analysis", {})
                    self.log_test("Portfolio API", True, f"Portfolio with {summary.get('num_holdings', 0)} holdings, risk score: {analysis.get('risk_score', 0)}")
                else:
                    missing = [f for f in required_fields if f not in data]
                    self.log_test("Portfolio API", False, f"Missing fields: {missing}")
            elif response.status_code == 401:
                self.log_test("Portfolio API", False, "Authentication failed")
            else:
                self.log_test("Portfolio API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Portfolio API", False, f"Exception: {str(e)}")
    
    def test_portfolio_trade(self):
        """Test real portfolio trade"""
        if not self.session_token:
            self.log_test("Portfolio trade API", False, "No session token available")
            return
            
        try:
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            trade_data = {
                "asset_type": "stock",
                "asset_symbol": "TCS",
                "asset_name": "Tata Consultancy Services",
                "quantity": 1,
                "price_inr": 3920,
                "trade_type": "buy",
                "is_virtual": False,
                "notes": "Test real trade from backend testing"
            }
            
            response = requests.post(f"{BACKEND_URL}/portfolio/trade", 
                                   headers=headers, 
                                   json=trade_data, 
                                   timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") and "trade" in data:
                    trade = data["trade"]
                    self.log_test("Portfolio trade API", True, f"Real trade executed: {trade.get('trade_type')} {trade.get('quantity')} {trade.get('asset_symbol')}")
                else:
                    self.log_test("Portfolio trade API", False, "Trade execution failed", data)
            elif response.status_code == 401:
                self.log_test("Portfolio trade API", False, "Authentication failed")
            else:
                self.log_test("Portfolio trade API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Portfolio trade API", False, f"Exception: {str(e)}")
    
    def test_watchlist_get(self):
        """Test get watchlist endpoint"""
        if not self.session_token:
            self.log_test("Watchlist GET API", False, "No session token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.get(f"{BACKEND_URL}/watchlist", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if "watchlist" in data:
                    watchlist = data["watchlist"]
                    self.log_test("Watchlist GET API", True, f"Watchlist loaded with {len(watchlist)} items")
                else:
                    self.log_test("Watchlist GET API", False, "Missing watchlist field")
            elif response.status_code == 401:
                self.log_test("Watchlist GET API", False, "Authentication failed")
            else:
                self.log_test("Watchlist GET API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Watchlist GET API", False, f"Exception: {str(e)}")
    
    def test_watchlist_add(self):
        """Test add to watchlist endpoint"""
        if not self.session_token:
            self.log_test("Watchlist ADD API", False, "No session token available")
            return
            
        try:
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            
            watchlist_data = {
                "asset_type": "crypto",
                "asset_symbol": "ETH",
                "asset_name": "Ethereum",
                "target_price": 350000,
                "alert_enabled": True
            }
            
            response = requests.post(f"{BACKEND_URL}/watchlist", 
                                   headers=headers, 
                                   json=watchlist_data, 
                                   timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success") and "item" in data:
                    item = data["item"]
                    self.watchlist_item_id = item.get("item_id")  # Store for deletion test
                    self.log_test("Watchlist ADD API", True, f"Added {item.get('asset_symbol')} to watchlist")
                else:
                    self.log_test("Watchlist ADD API", False, "Failed to add to watchlist", data)
            elif response.status_code == 401:
                self.log_test("Watchlist ADD API", False, "Authentication failed")
            else:
                self.log_test("Watchlist ADD API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Watchlist ADD API", False, f"Exception: {str(e)}")
    
    def test_watchlist_delete(self):
        """Test delete from watchlist endpoint"""
        if not self.session_token:
            self.log_test("Watchlist DELETE API", False, "No session token available")
            return
            
        if not hasattr(self, 'watchlist_item_id') or not self.watchlist_item_id:
            self.log_test("Watchlist DELETE API", False, "No watchlist item ID available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.delete(f"{BACKEND_URL}/watchlist/{self.watchlist_item_id}", 
                                     headers=headers, 
                                     timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    self.log_test("Watchlist DELETE API", True, "Successfully removed item from watchlist")
                else:
                    self.log_test("Watchlist DELETE API", False, "Failed to delete from watchlist", data)
            elif response.status_code == 401:
                self.log_test("Watchlist DELETE API", False, "Authentication failed")
            elif response.status_code == 404:
                self.log_test("Watchlist DELETE API", False, "Watchlist item not found")
            else:
                self.log_test("Watchlist DELETE API", False, f"HTTP {response.status_code}", response.text)
                
        except Exception as e:
            self.log_test("Watchlist DELETE API", False, f"Exception: {str(e)}")
    
    def test_error_handling(self):
        """Test error handling for invalid requests"""
        try:
            # Test 404 for invalid crypto
            response = requests.get(f"{BACKEND_URL}/crypto/INVALID", timeout=10)
            if response.status_code == 404:
                self.log_test("Error handling (404 crypto)", True, "Correctly returns 404 for invalid crypto")
            else:
                self.log_test("Error handling (404 crypto)", False, f"Expected 404, got {response.status_code}")
            
            # Test 404 for invalid stock
            response = requests.get(f"{BACKEND_URL}/stocks/INVALID", timeout=10)
            if response.status_code == 404:
                self.log_test("Error handling (404 stock)", True, "Correctly returns 404 for invalid stock")
            else:
                self.log_test("Error handling (404 stock)", False, f"Expected 404, got {response.status_code}")
            
            # Test 401 for protected route without auth
            response = requests.get(f"{BACKEND_URL}/auth/me", timeout=10)
            if response.status_code == 401:
                self.log_test("Error handling (401 auth)", True, "Correctly returns 401 for unauthenticated request")
            else:
                self.log_test("Error handling (401 auth)", False, f"Expected 401, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Error handling tests", False, f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting comprehensive backend API testing...")
        print(f"Backend URL: {BACKEND_URL}")
        print("=" * 60)
        
        # Create test user and session first
        if not self.create_test_user_and_session():
            print("❌ Failed to create test user. Skipping auth-protected tests.")
        
        # Public API tests
        print("\n📊 Testing Public APIs...")
        self.test_health_check()
        self.test_crypto_prices()
        self.test_crypto_detail()
        self.test_stock_prices()
        self.test_stock_detail()
        self.test_news_api()
        self.test_news_categories()
        self.test_daily_decision()
        self.test_education_tips()
        
        # Auth-protected API tests
        if self.session_token:
            print("\n🔐 Testing Auth-Protected APIs...")
            self.test_auth_me()
            self.test_simulator_portfolio()
            self.test_simulator_trade()
            self.test_portfolio()
            self.test_portfolio_trade()
            self.test_watchlist_get()
            self.test_watchlist_add()
            self.test_watchlist_delete()
        
        # Error handling tests
        print("\n🛡️ Testing Error Handling...")
        self.test_error_handling()
        
        # Summary
        return self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results if result["success"])
        failed = len(self.test_results) - passed
        
        print(f"Total Tests: {len(self.test_results)}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/len(self.test_results)*100):.1f}%")
        
        if failed > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  • {result['test']}: {result['details']}")
        
        print(f"\n🔧 Test User Created:")
        print(f"  • User ID: {self.user_id}")
        print(f"  • Email: {TEST_USER_EMAIL}")
        print(f"  • Session Token: {self.session_token}")
        
        return passed, failed

if __name__ == "__main__":
    tester = BackendTester()
    passed, failed = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)