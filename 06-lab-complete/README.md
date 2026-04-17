# Lab 12 - Complete Production Agent

This folder contains a simple chatbot API built with FastAPI and OpenAI.

## Features

- `POST /ask` for chatbot responses
- `GET /health` and `GET /ready` for platform checks
- `GET /docs` for Swagger UI
- API key protection with `X-API-Key`
- Basic rate limit and budget tracking
- Railway-ready config

## Local Run

1. Make sure `OPENAI_API_KEY` is filled in `.env`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Test the chatbot:

```bash
curl http://localhost:8000/ask ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: dev-key-change-me-in-production" ^
  -d "{\"question\":\"Hello, introduce yourself briefly.\"}"
```

## Request Format

You can send a simple one-turn message:

```json
{
  "question": "What is Railway?"
}
```

Or include short history:

```json
{
  "question": "Can you explain it in simpler terms?",
  "history": [
    { "role": "user", "content": "What is Railway?" },
    { "role": "assistant", "content": "Railway is a platform for deploying apps quickly." }
  ]
}
```

## Deploy to Railway

Use this folder as the service root: `06-lab-complete`

```bash
railway login
railway init
railway up
railway domain
```

Set these variables in Railway before or after the first deploy:

- `OPENAI_API_KEY`
- `AGENT_API_KEY`
- `JWT_SECRET`
- `ENVIRONMENT=production`
- `ENABLE_DOCS=true`

If you connect the whole repository in Railway Dashboard, set:

- `Root Directory` -> `/06-lab-complete`
- `Config File Path` -> `/06-lab-complete/railway.toml`

## Production Check

```bash
python check_production_ready.py
```
