"""The phone line to the AI provider. Kept tiny on purpose: one method, one place
that knows about the provider. Groq and OpenRouter both speak the OpenAI
request format, so switching provider means changing .env, not code.

Tests replace this class with a fake, so they run without a key or network.
"""
from openai import OpenAI

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT_SECONDS


class LLMUnavailable(Exception):
    """Raised for anything that means 'no usable answer from the provider'."""


class LLMClient:
    def __init__(self):
        if not LLM_API_KEY:
            self._client = None
        else:
            self._client = OpenAI(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
                timeout=LLM_TIMEOUT_SECONDS,  # give up instead of hanging
                max_retries=1,  # one quick retry on network blips / 429, then fail over to the fallback text
            )

    def chat(self, messages: list[dict], tools: list[dict]):
        if self._client is None:
            raise LLMUnavailable("LLM_API_KEY is not set")
        try:
            extra = {"tools": tools, "tool_choice": "auto"} if tools else {}
            resp = self._client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.3,  # low: consistent, less 'creative' wording
                max_tokens=1200,   # reasoning models spend some tokens thinking before replying
                **extra,
            )
        except Exception as exc:  # timeout, 401 bad key, 429 rate limit, 5xx, network...
            raise LLMUnavailable(type(exc).__name__) from exc
        if not resp.choices:
            raise LLMUnavailable("empty response")
        return resp.choices[0].message
