"""Groq LLM client with bounded concurrency, RPM limiting and exponential backoff.

The rest of the application depends only on the ``LLMClient`` protocol, so
tests inject a mock client and never touch the network.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import Settings

log = logging.getLogger("n2.groq")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int
    attempts: int
    usage: dict[str, int] = field(default_factory=dict)
    json_mode: bool = False
    notes: list[str] = field(default_factory=list)


class LLMError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None,
                 attempts: int = 1, kind: str = "error"):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.attempts = attempts
        self.kind = kind


class LLMClient(Protocol):
    async def complete(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False,
                       max_tokens: int | None = None, temperature: float | None = None,
                       reasoning_effort: str | None = None) -> LLMResult: ...

    async def list_models(self) -> list[str]: ...


class RateLimiter:
    """Sliding-window requests-per-minute limiter."""

    def __init__(self, rpm: int, clock=time.monotonic, sleep=asyncio.sleep):
        self.rpm = rpm
        self._clock = clock
        self._sleep = sleep
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._events and now - self._events[0] >= 60:
                    self._events.popleft()
                if len(self._events) < self.rpm:
                    self._events.append(now)
                    return
                await self._sleep(max(0.05, 60 - (now - self._events[0])))


def classify_exception(exc: Exception) -> tuple[bool, int | None, float | None, str]:
    """Return (retryable, status_code, retry_after_seconds, kind)."""
    status = getattr(exc, "status_code", None)
    retry_after = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        try:
            retry_after = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            retry_after = None
    name = type(exc).__name__.lower()
    if status == 429 or "ratelimit" in name:
        return True, status or 429, retry_after, "rate_limited"
    if "timeout" in name or isinstance(exc, asyncio.TimeoutError):
        return True, status, retry_after, "timeout"
    if "connection" in name:
        return True, status, retry_after, "connection"
    if isinstance(status, int) and (status >= 500 or status == 408):
        return True, status, retry_after, "server_error"
    if status == 404 or "notfound" in name:
        return False, status, None, "model_not_found"
    if status in (401, 403) or "authentication" in name or "permission" in name:
        return False, status, None, "auth"
    if status == 400 or "badrequest" in name:
        return False, status, None, "bad_request"
    return False, status, None, "error"


def clean_model_text(text: str | None) -> str:
    return _THINK_RE.sub("", text or "").strip()


class GroqLLMClient:
    """Async wrapper around the official Groq Python SDK."""

    def __init__(self, settings: Settings, *, sleep=asyncio.sleep):
        self.settings = settings
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._limiter = RateLimiter(settings.requests_per_minute, sleep=sleep)
        self._client: Any = None

    # -- SDK plumbing -------------------------------------------------
    def _sdk(self) -> Any:
        if self._client is None:
            if not self.settings.api_key_configured:
                raise LLMError("GROQ_API_KEY is not configured", kind="auth")
            try:
                from groq import AsyncGroq
            except ImportError as e:  # pragma: no cover - depends on environment
                raise LLMError("The 'groq' package is not installed (pip install groq)", kind="config") from e
            self._client = AsyncGroq(
                api_key=self.settings.groq_api_key.get_secret_value(),  # type: ignore[union-attr]
                timeout=self.settings.request_timeout_seconds,
                max_retries=0,  # we own retry policy
            )
        return self._client

    async def _raw_call(self, **kwargs: Any) -> Any:
        return await self._sdk().chat.completions.create(**kwargs)

    async def list_models(self) -> list[str]:
        resp = await self._sdk().models.list()
        return sorted(m.id for m in getattr(resp, "data", []) or [])

    def backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(self.settings.backoff_max_seconds, max(0.0, retry_after))
        base = self.settings.backoff_base_seconds * (2 ** (attempt - 1))
        return min(self.settings.backoff_max_seconds, base) * (0.75 + random.random() * 0.5)

    # -- Public API ----------------------------------------------------
    async def complete(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False,
                       max_tokens: int | None = None, temperature: float | None = None,
                       reasoning_effort: str | None = None) -> LLMResult:
        notes: list[str] = []
        use_json = json_mode
        effort = reasoning_effort
        attempt = 0
        max_attempts = self.settings.max_retries + 1
        async with self._semaphore:
            while True:
                attempt += 1
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.settings.temperature if temperature is None else temperature,
                    "max_tokens": max_tokens or self.settings.max_output_tokens,
                }
                if use_json:
                    kwargs["response_format"] = {"type": "json_object"}
                if effort:
                    kwargs["reasoning_effort"] = effort
                await self._limiter.acquire()
                started = time.perf_counter()
                try:
                    resp = await asyncio.wait_for(self._raw_call(**kwargs),
                                                  timeout=self.settings.request_timeout_seconds + 5)
                except Exception as exc:  # noqa: BLE001 - classified below
                    retryable, status, retry_after, kind = classify_exception(exc)
                    msg = _safe_message(exc)
                    if kind == "bad_request" and effort and "reasoning" in msg.lower():
                        # Model doesn't support this reasoning effort: retry once with its default.
                        notes.append("reasoning_effort_rejected_fallback_to_default")
                        effort = None
                        attempt -= 1
                        continue
                    if kind == "bad_request" and use_json and ("json" in msg.lower() or "response_format" in msg.lower()):
                        # Model rejected or failed JSON mode: retry once in plain mode; output
                        # is still parsed & validated strictly downstream.
                        notes.append("json_mode_rejected_fallback_to_plain")
                        use_json = False
                        attempt -= 1
                        continue
                    if retryable and attempt < max_attempts:
                        delay = self.backoff_delay(attempt, retry_after)
                        log.warning("groq %s on %s (attempt %d/%d); retrying in %.1fs",
                                    kind, model, attempt, max_attempts, delay)
                        notes.append(f"retry_{attempt}:{kind}")
                        await self._sleep(delay)
                        continue
                    raise LLMError(msg, retryable=retryable, status_code=status, attempts=attempt, kind=kind) from exc
                latency_ms = int((time.perf_counter() - started) * 1000)
                return LLMResult(
                    text=clean_model_text(_message_text(resp)),
                    model=model,
                    latency_ms=latency_ms,
                    attempts=attempt,
                    usage=_usage(resp),
                    json_mode=use_json,
                    notes=notes,
                )


def _message_text(resp: Any) -> str:
    try:
        return resp.choices[0].message.content or ""
    except (AttributeError, IndexError, KeyError, TypeError):
        if isinstance(resp, dict):
            return resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        return ""


def _usage(resp: Any) -> dict[str, int]:
    u = getattr(resp, "usage", None)
    if u is None and isinstance(resp, dict):
        u = resp.get("usage")
    if u is None:
        return {}
    get = (lambda k: u.get(k)) if isinstance(u, dict) else (lambda k: getattr(u, k, None))
    out = {k: int(get(k)) for k in ("prompt_tokens", "completion_tokens", "total_tokens") if get(k) is not None}
    return out


def _safe_message(exc: Exception) -> str:
    """Error text without any chance of echoing the API key."""
    msg = str(exc) or type(exc).__name__
    msg = re.sub(r"gsk_[A-Za-z0-9]+", "gsk_***", msg)
    return msg[:800]
