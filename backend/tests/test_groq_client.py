import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.groq_client import GroqLLMClient, LLMError, RateLimiter, classify_exception, clean_model_text


class StatusErr(Exception):
    def __init__(self, status, msg="err", retry_after=None):
        super().__init__(msg)
        self.status_code = status
        self.response = SimpleNamespace(headers={"retry-after": str(retry_after)} if retry_after else {})


def _resp(text="ok", pt=10, ct=5):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                           usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct))


class ScriptedClient(GroqLLMClient):
    def __init__(self, settings, script):
        self.sleeps = []

        async def fake_sleep(s):
            self.sleeps.append(s)
        super().__init__(settings, sleep=fake_sleep)
        self.script = list(script)
        self.kwargs = []

    async def _raw_call(self, **kwargs):
        self.kwargs.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def s():
    return Settings(groq_api_key=SecretStr("gsk_abc"), model_1="a", model_2="b", model_3="c", max_retries=3,
                    backoff_base_seconds=1.0, backoff_max_seconds=8.0, requests_per_minute=1000)


def run(coro):
    return asyncio.run(coro)


def test_retries_rate_limit_then_succeeds(s):
    c = ScriptedClient(s, [StatusErr(429), StatusErr(503), _resp("hello")])
    res = run(c.complete("a", [{"role": "user", "content": "x"}]))
    assert res.text == "hello" and res.attempts == 3
    assert res.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert len(c.sleeps) == 2 and c.sleeps[1] > c.sleeps[0] * 1.1  # exponential growth


def test_retry_after_header_respected(s):
    c = ScriptedClient(s, [StatusErr(429, retry_after=4), _resp()])
    run(c.complete("a", []))
    assert c.sleeps == [4.0]


def test_gives_up_after_max_retries(s):
    c = ScriptedClient(s, [StatusErr(429)] * 4)
    with pytest.raises(LLMError) as ei:
        run(c.complete("a", []))
    assert ei.value.attempts == 4 and ei.value.kind == "rate_limited" and ei.value.retryable


def test_non_retryable_fails_fast(s):
    c = ScriptedClient(s, [StatusErr(404, "model not found")])
    with pytest.raises(LLMError) as ei:
        run(c.complete("missing-model", []))
    assert ei.value.kind == "model_not_found" and ei.value.attempts == 1 and not c.sleeps


def test_reasoning_effort_sent_and_dropped_if_rejected(s):
    c = ScriptedClient(s, [_resp("a")])
    run(c.complete("m", [], reasoning_effort="low"))
    assert c.kwargs[0]["reasoning_effort"] == "low"
    c = ScriptedClient(s, [StatusErr(400, "reasoning_effort is not supported with this model"), _resp("b")])
    res = run(c.complete("m", [], reasoning_effort="low"))
    assert res.text == "b" and "reasoning_effort" not in c.kwargs[1]
    assert "reasoning_effort_rejected_fallback_to_default" in res.notes
    c = ScriptedClient(s, [_resp("c")])
    run(c.complete("m", []))
    assert "reasoning_effort" not in c.kwargs[0]


def test_json_mode_rejection_falls_back_once(s):
    c = ScriptedClient(s, [StatusErr(400, "json_validate_failed"), _resp("{}")])
    res = run(c.complete("a", [], json_mode=True))
    assert "response_format" in c.kwargs[0] and "response_format" not in c.kwargs[1]
    assert res.json_mode is False and "json_mode_rejected_fallback_to_plain" in res.notes


def test_api_key_is_redacted_from_errors(s):
    c = ScriptedClient(s, [StatusErr(401, "invalid key gsk_SECRET123")])
    with pytest.raises(LLMError) as ei:
        run(c.complete("a", []))
    assert "SECRET123" not in str(ei.value)


def test_classify_and_clean():
    assert classify_exception(asyncio.TimeoutError())[0] is True
    assert classify_exception(StatusErr(500))[3] == "server_error"
    assert clean_model_text("<think>hmm</think>\n{\"a\":1}") == '{"a":1}'


def test_rate_limiter_waits_when_window_full():
    t = [0.0]
    slept = []

    async def sleep(d):
        slept.append(d)
        t[0] += d

    async def go():
        rl = RateLimiter(2, clock=lambda: t[0], sleep=sleep)
        for _ in range(3):
            await rl.acquire()
    run(go())
    assert slept and slept[0] == pytest.approx(60.0)
