import json
import logging
import signal
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.llm import chat as llm_chat

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0
_rate_windows: dict[str, deque] = defaultdict(deque)
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def check_rate_limit(key: str) -> None:
    now = time.time()
    window = _rate_windows[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )
    window.append(now)


def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(status_code=503, detail="Daily budget exhausted. Try tomorrow.")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    _daily_cost += cost


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _is_ready
    logger.info(
        json.dumps(
            {
                "event": "startup",
                "app": settings.app_name,
                "version": settings.app_version,
                "environment": settings.environment,
            }
        )
    )
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))
    yield
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.time() - start) * 1000, 1),
                }
            )
        )
        return response
    except Exception:
        _error_count += 1
        raise


class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"user", "assistant"}:
            raise ValueError("history roles must be 'user' or 'assistant'")
        return value


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str


CHAT_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Deployment Chatbot</title>
  <style>
    :root {
      --bg: #f5efe4;
      --panel: rgba(255, 252, 246, 0.92);
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #d6c8b3;
      --brand: #b45309;
      --brand-dark: #7c2d12;
      --user: #1d4ed8;
      --assistant: #fff7ed;
      --shadow: 0 20px 60px rgba(124, 45, 18, 0.12);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180, 83, 9, 0.18), transparent 30%),
        radial-gradient(circle at bottom right, rgba(29, 78, 216, 0.14), transparent 28%),
        linear-gradient(160deg, #fffaf1 0%, #f1e4cf 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }

    .app {
      width: min(960px, 100%);
      background: var(--panel);
      border: 1px solid rgba(124, 45, 18, 0.12);
      border-radius: 24px;
      overflow: hidden;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }

    .hero {
      padding: 28px 28px 18px;
      border-bottom: 1px solid rgba(124, 45, 18, 0.1);
      background: linear-gradient(135deg, rgba(180, 83, 9, 0.08), rgba(255, 255, 255, 0.2));
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.6rem);
      line-height: 1.05;
      letter-spacing: -0.03em;
    }

    .hero p {
      margin: 12px 0 0;
      max-width: 680px;
      color: var(--muted);
      line-height: 1.6;
    }

    .layout {
      display: grid;
      grid-template-columns: 280px 1fr;
      min-height: 72vh;
    }

    .sidebar {
      border-right: 1px solid rgba(124, 45, 18, 0.1);
      padding: 24px;
      background: rgba(255, 255, 255, 0.55);
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(180, 83, 9, 0.08);
      color: var(--brand-dark);
      font-size: 0.92rem;
      margin-bottom: 20px;
    }

    .sidebar h2 {
      margin: 0 0 12px;
      font-size: 1.05rem;
    }

    .sidebar p,
    .sidebar li {
      color: var(--muted);
      line-height: 1.55;
    }

    .sidebar ul {
      margin: 0;
      padding-left: 18px;
    }

    .chat-shell {
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.25), transparent 18%),
        repeating-linear-gradient(
          180deg,
          transparent,
          transparent 31px,
          rgba(214, 200, 179, 0.16) 31px,
          rgba(214, 200, 179, 0.16) 32px
        );
    }

    .message {
      max-width: min(720px, 90%);
      padding: 14px 16px;
      border-radius: 18px;
      line-height: 1.55;
      white-space: pre-wrap;
      animation: rise 180ms ease-out;
      border: 1px solid rgba(17, 24, 39, 0.06);
    }

    .message.user {
      align-self: flex-end;
      background: rgba(29, 78, 216, 0.1);
      color: #102a56;
      border-bottom-right-radius: 6px;
    }

    .message.assistant {
      align-self: flex-start;
      background: var(--assistant);
      border-bottom-left-radius: 6px;
    }

    .meta {
      display: block;
      margin-bottom: 6px;
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--brand-dark);
    }

    .composer {
      padding: 18px;
      border-top: 1px solid rgba(124, 45, 18, 0.1);
      background: rgba(255, 252, 246, 0.96);
    }

    .form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: end;
    }

    textarea {
      width: 100%;
      resize: vertical;
      min-height: 72px;
      max-height: 220px;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      font: inherit;
      outline: none;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    textarea:focus {
      border-color: rgba(29, 78, 216, 0.45);
      box-shadow: 0 0 0 4px rgba(29, 78, 216, 0.08);
    }

    button {
      border: 0;
      border-radius: 16px;
      padding: 14px 18px;
      font: inherit;
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--brand), var(--brand-dark));
      cursor: pointer;
      min-width: 124px;
      min-height: 56px;
      transition: transform 0.14s ease, opacity 0.14s ease;
    }

    button:hover {
      transform: translateY(-1px);
    }

    button:disabled {
      opacity: 0.62;
      cursor: wait;
      transform: none;
    }

    .footer {
      margin-top: 10px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 0.92rem;
    }

    .status {
      min-height: 1.4em;
    }

    @keyframes rise {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @media (max-width: 860px) {
      .layout {
        grid-template-columns: 1fr;
      }

      .sidebar {
        border-right: 0;
        border-bottom: 1px solid rgba(124, 45, 18, 0.1);
      }
    }

    @media (max-width: 640px) {
      body {
        padding: 10px;
      }

      .hero,
      .sidebar,
      .messages,
      .composer {
        padding-left: 16px;
        padding-right: 16px;
      }

      .form {
        grid-template-columns: 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <section class="hero">
      <h1>Deployment Chatbot</h1>
      <p>Ask quick questions about cloud deployment, Railway, Docker, APIs, or your lab tasks. This page talks directly to your deployed FastAPI chatbot.</p>
    </section>

    <div class="layout">
      <aside class="sidebar">
        <div class="pill">Live OpenAI Chat</div>
        <h2>What this page can do</h2>
        <ul>
          <li>Chat with the deployed agent in your browser.</li>
          <li>Keep short conversation history on this device.</li>
          <li>Use the same backend you already deployed to Railway.</li>
        </ul>
        <h2 style="margin-top: 22px;">Useful routes</h2>
        <p><strong>/docs</strong> for Swagger UI</p>
        <p><strong>/health</strong> for platform health checks</p>
        <p><strong>/ask</strong> for API calls with header auth</p>
      </aside>

      <main class="chat-shell">
        <div class="messages" id="messages"></div>
        <div class="composer">
          <form class="form" id="chat-form">
            <textarea id="prompt" placeholder="Ask something like: How do I deploy a FastAPI app on Railway?" required></textarea>
            <button id="send-button" type="submit">Send</button>
          </form>
          <div class="footer">
            <div class="status" id="status">Ready.</div>
            <div>Route: <code>/chat/ask</code></div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <script>
    const messagesEl = document.getElementById("messages");
    const formEl = document.getElementById("chat-form");
    const promptEl = document.getElementById("prompt");
    const sendButtonEl = document.getElementById("send-button");
    const statusEl = document.getElementById("status");
    const storageKey = "deployment-chat-history";

    function loadHistory() {
      try {
        return JSON.parse(localStorage.getItem(storageKey) || "[]");
      } catch {
        return [];
      }
    }

    function saveHistory(history) {
      localStorage.setItem(storageKey, JSON.stringify(history.slice(-12)));
    }

    function renderMessage(role, content) {
      const item = document.createElement("article");
      item.className = `message ${role}`;
      const label = role === "user" ? "You" : "Assistant";
      item.innerHTML = `<span class="meta">${label}</span>${content}`;
      messagesEl.appendChild(item);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderHistory() {
      messagesEl.innerHTML = "";
      const history = loadHistory();
      if (history.length === 0) {
        renderMessage("assistant", "Hello. I am your deployment chatbot. Ask me anything about Railway, Docker, APIs, or this lab.");
        return;
      }
      history.forEach((entry) => renderMessage(entry.role, entry.content));
    }

    async function sendMessage(question) {
      const history = loadHistory();
      const response = await fetch("/chat/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Request failed");
      }

      return response.json();
    }

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = promptEl.value.trim();
      if (!question) return;

      const history = loadHistory();
      history.push({ role: "user", content: question });
      saveHistory(history);
      renderHistory();

      promptEl.value = "";
      promptEl.focus();
      sendButtonEl.disabled = true;
      statusEl.textContent = "Thinking...";

      try {
        const payload = await sendMessage(question);
        const updated = loadHistory();
        updated.push({ role: "assistant", content: payload.answer });
        saveHistory(updated);
        renderHistory();
        statusEl.textContent = "Answered.";
      } catch (error) {
        const updated = loadHistory();
        updated.push({ role: "assistant", content: "Sorry, something went wrong while contacting the chatbot." });
        saveHistory(updated);
        renderHistory();
        statusEl.textContent = error.message.slice(0, 180);
      } finally {
        sendButtonEl.disabled = false;
      }
    });

    renderHistory();
  </script>
</body>
</html>
"""


def _build_answer(body: AskRequest, bucket_key: str, request: Request) -> AskResponse:
    check_rate_limit(bucket_key)

    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(
        json.dumps(
            {
                "event": "agent_call",
                "q_len": len(body.question),
                "history_len": len(body.history),
                "client": str(request.client.host) if request.client else "unknown",
                "bucket": bucket_key,
            }
        )
    )

    try:
        answer = llm_chat(
            body.question,
            [message.model_dump() for message in body.history],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("OpenAI request failed")
        raise HTTPException(status_code=502, detail="OpenAI request failed") from exc

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask",
            "chat": "GET /chat",
            "health": "GET /health",
            "ready": "GET /ready",
            "docs": "GET /docs",
        },
    }


@app.get("/chat", response_class=HTMLResponse, tags=["Chat UI"])
def chat_page():
    return HTMLResponse(CHAT_PAGE_HTML)


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    return _build_answer(body, _key[:8], request)


@app.post("/chat/ask", response_model=AskResponse, tags=["Chat UI"])
async def chat_ask(body: AskRequest, request: Request):
    client_host = str(request.client.host) if request.client else "browser"
    return _build_answer(body, f"chat:{client_host}", request)


@app.get("/health", tags=["Operations"])
def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": {
            "llm": "configured" if settings.openai_api_key else "missing_api_key",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(_daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(_daily_cost / settings.daily_budget_usd * 100, 1),
    }


def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
