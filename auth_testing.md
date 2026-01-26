# Auth-Gated App Testing Playbook

## Step 1: Create Test User & Session
```bash
mongosh --eval "
use('test_database');
var visitorId = 'user_' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: visitorId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date(),
  capital: 100000.0,
  risk_profile: 'moderate'
});
db.user_sessions.insertOne({
  user_id: visitorId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + visitorId);
"
```

## Step 2: Test Backend API
```bash
# Test auth endpoint
curl -X GET "http://localhost:8001/api/auth/me" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Test market data endpoints
curl -X GET "http://localhost:8001/api/crypto/prices"
curl -X GET "http://localhost:8001/api/stocks/prices"
curl -X GET "http://localhost:8001/api/news"
curl -X GET "http://localhost:8001/api/decision/today"

# Test protected endpoints
curl -X GET "http://localhost:8001/api/simulator/portfolio" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

curl -X GET "http://localhost:8001/api/portfolio" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

curl -X GET "http://localhost:8001/api/watchlist" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Step 3: Browser Testing
```python
# Set cookie and navigate
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "localhost",
    "path": "/",
    "httpOnly": True,
    "secure": False,
    "sameSite": "Lax"
}]);
await page.goto("http://localhost:3000");
```

## Checklist
- [ ] User document has `user_id` field
- [ ] Session `user_id` matches `users.user_id` exactly
- [ ] All queries exclude `_id` with `{"_id": 0}`
- [ ] API returns user data (not 401/404)
- [ ] Dashboard loads without redirect

## Success Indicators
- /api/auth/me returns user data with `user_id` field
- Dashboard loads without redirect
- CRUD operations work
