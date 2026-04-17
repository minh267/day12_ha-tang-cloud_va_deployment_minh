# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. API key was hardcoded directly in source code, which is unsafe and hard to rotate.
2. The app used a fixed port instead of reading `PORT` from environment variables.
3. Debug-style behavior was mixed into runtime code, which is risky in production.
4. There was no proper health check endpoint for platforms to verify liveness.
5. There was no graceful shutdown handling for `SIGTERM`.
6. Configuration was tied to local defaults instead of a clear 12-factor config pattern.
7. Logging was basic and not structured for cloud log aggregation.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcoded values | Environment variables | Makes deploys portable and safer across dev, staging, and production |
| Secrets | Embedded in code | Injected via `.env` or platform variables | Prevents secret leaks and makes rotation easier |
| Port | Fixed `8000` | Reads `PORT` from platform | Required for Railway/Render/container platforms |
| Health check | Missing or minimal | `/health` and `/ready` endpoints | Lets orchestrators detect healthy and ready instances |
| Logging | `print()` style | Structured JSON logging | Easier monitoring, debugging, and alerting in cloud logs |
| Shutdown | Abrupt stop | Graceful shutdown with signal handling | Helps finish in-flight requests cleanly |
| Error handling | Minimal | Explicit HTTP errors and validation | Improves reliability and observability |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: `python:3.11-slim`
2. Working directory: `/app` in runtime containers, `/build` in builder stage
3. `COPY requirements.txt` is done first to maximize Docker layer caching, so dependency install is skipped if only app code changes.
4. `CMD` provides the default command and can be overridden more easily, while `ENTRYPOINT` makes the container behave like a fixed executable.

### Exercise 2.3: Image size comparison
- Develop: not measured exactly in this final submission, but larger because it is single-stage and keeps more build context
- Production: smaller because it uses a multi-stage build and a slim runtime image
- Difference: meaningful reduction due to separating build dependencies from runtime dependencies

Notes:
- Stage 1 installs dependencies and prepares the Python environment.
- Stage 2 copies only the runtime artifacts and application code.
- The image is smaller because compiler/build tooling is not kept in the final runtime image.

### Exercise 2.4: Docker Compose stack
- Services started: `agent` and `redis`
- Communication: the app talks to Redis using the internal service hostname, for example `redis://redis:6379/0`
- Architecture summary: client -> agent API -> Redis for shared state/limits/history

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://lab-complete-chatbot-production.up.railway.app
- Chat UI: https://lab-complete-chatbot-production.up.railway.app/chat
- Docs: https://lab-complete-chatbot-production.up.railway.app/docs
- Health: https://lab-complete-chatbot-production.up.railway.app/health
- Screenshot: not added in repo yet

### Exercise 3.2: Render vs Railway config
- `railway.toml` is compact and mainly defines build/deploy behavior for one service.
- `render.yaml` is closer to a broader infrastructure blueprint and is more explicit about service definitions.
- Railway was faster for this lab, while Render is useful when managing services in a more declarative way from a blueprint file.

## Part 4: API Security

### Exercise 4.1-4.3: Test results
- Without API key on protected route: server returns `401 Unauthorized`
- With correct API key on protected route: server returns `200 OK`
- Rate limiting approach: in-memory sliding-window style tracking using per-key request timestamps
- Rate limit in this final app: `20 req/min` by default from environment config
- Admin bypass concept from the advanced section: use different limiter policies or higher thresholds based on authenticated role

Example results:

```text
POST /ask without X-API-Key -> 401
POST /ask with X-API-Key -> 200
POST /chat/ask from UI -> 200
GET /health -> 200
```

### Exercise 4.4: Cost guard implementation
My approach was:
- estimate request cost from input and output token counts
- track accumulated cost in app state
- block requests when daily budget is exceeded
- make the budget configurable through `DAILY_BUDGET_USD`

The Redis-based monthly design shown in the lab is more production-ready because it survives restarts and works across multiple instances. In my final app, the guard is implemented in-process for simplicity, but the correct production extension would be storing per-user or per-month cost in Redis with TTL-based expiry.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

#### 5.1 Health checks
- Implemented `GET /health` for liveness
- Implemented `GET /ready` for readiness
- `/health` returns service metadata and whether the LLM API key is configured
- `/ready` returns `503` if the app is not yet marked ready

#### 5.2 Graceful shutdown
- Added `SIGTERM` handling
- The app logs shutdown signals and uses FastAPI lifespan hooks to switch readiness state on startup/shutdown
- This helps cloud platforms terminate the service more safely

#### 5.3 Stateless design
- The final browser UI stores short chat history in browser `localStorage`
- The backend accepts `history` in the request instead of relying on server memory for long-lived sessions
- This is more stateless than keeping per-user conversation state only in RAM on one instance
- For stronger production statelessness, Redis should be used for shared history, rate limits, and usage counters

#### 5.4 Load balancing
- The architecture is compatible with horizontal scaling because requests do not require sticky in-memory server session state
- In the lab context, Nginx would distribute traffic across multiple agent instances
- If one instance dies, other healthy replicas can continue serving requests

#### 5.5 Test stateless behavior
- Conversation context can be sent from the client to the backend through the `history` field
- The browser chat UI persists recent messages locally, so refreshing the page does not immediately lose context on that client
- The next production step would be moving shared state to Redis so multiple replicas can continue the same user conversation consistently

### Final notes
- Public service is deployed and reachable on Railway
- The chatbot works through API and browser UI
- Swagger docs are available
- Health checks pass in production
