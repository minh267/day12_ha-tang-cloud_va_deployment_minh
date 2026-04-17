from __future__ import annotations

from openai import OpenAI

from app.config import settings

SYSTEM_PROMPT = (
    "You are a helpful chatbot for students learning cloud deployment. "
    "Answer clearly, keep things practical, and explain technical terms simply."
)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def chat(question: str, history: list[dict[str, str]] | None = None) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    input_items: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        input_items.extend(history)
    input_items.append({"role": "user", "content": question})

    response = get_client().responses.create(
        model=settings.llm_model,
        input=input_items,
    )
    return (response.output_text or "").strip()
