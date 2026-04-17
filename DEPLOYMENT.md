# Deployment Information

## Public URL
https://lab-complete-chatbot-production.up.railway.app

## Platform
Railway

## Additional Routes
- Chat UI: https://lab-complete-chatbot-production.up.railway.app/chat
- Swagger Docs: https://lab-complete-chatbot-production.up.railway.app/docs
- Health Check: https://lab-complete-chatbot-production.up.railway.app/health

## Test Commands

### Health Check
```bash
curl https://lab-complete-chatbot-production.up.railway.app/health
# Expected: {"status":"ok", ...}
```

### API Test (with authentication)
```bash
curl -X POST https://lab-complete-chatbot-production.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

### Browser Chat UI
Open this URL in a browser:

```text
https://lab-complete-chatbot-production.up.railway.app/chat
```

## Environment Variables Set
- OPENAI_API_KEY
- AGENT_API_KEY
- JWT_SECRET
- LLM_MODEL
- APP_NAME
- APP_VERSION
- ALLOWED_ORIGINS
- RATE_LIMIT_PER_MINUTE
- DAILY_BUDGET_USD
- ENABLE_DOCS
- ENVIRONMENT
- DEBUG

## Deployment Notes
- Service root used for deploy: `06-lab-complete`
- Platform config file: `06-lab-complete/railway.toml`
- Dockerized deployment with a multi-stage Dockerfile
- Public chatbot UI and API are both running on the same Railway service

## Screenshots
- Not added yet
