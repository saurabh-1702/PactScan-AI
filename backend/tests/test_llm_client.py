"""LLM abstraction tests — cache, 7-tier model fallback, multi-account fallback.

All mocked: `_call_gemini` (the single SDK call site) is monkeypatched, so no
real API calls and no network.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.config import settings
from app.llm import client as llm
from app.llm.errors import AllLLMTiersExhaustedError, QuotaOrRateLimitError

pytestmark = pytest.mark.asyncio


class _Answer(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def llm_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_enabled", True)
    monkeypatch.setattr(settings, "llm_cache_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(settings, "llm_prompt_version", "v1")
    monkeypatch.setattr(settings, "llm_tier_cooldown_seconds", 60)
    monkeypatch.setattr(settings, "llm_provider_order", "gemini")
    monkeypatch.setattr(settings, "gemini_api_keys", "key1,key2,key3")
    monkeypatch.setattr(settings, "groq_api_keys", "")
    llm._reset_clients_for_tests()
    yield


def _make_call_recorder(behaviour):
    """behaviour(api_key, model) -> str  (return) or raises."""
    calls: list[dict] = []

    def _call(api_key, model, prompt, system_prompt, json_schema):
        calls.append({"api_key": api_key, "model": model})
        return behaviour(api_key, model)

    _call.calls = calls
    return _call


async def test_tier_fallback_advances_on_quota_error(monkeypatch):
    tiers = settings.gemini_model_tiers

    def behaviour(api_key, model):
        if model == tiers[0]:
            raise QuotaOrRateLimitError("429")
        return '{"value": "from-tier-2"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    result = await llm.generate_structured("q", _Answer)
    assert result.value == "from-tier-2"
    assert [c["model"] for c in rec.calls] == [tiers[0], tiers[1]]
    assert rec.calls[-1]["api_key"] == "key1"


async def test_is_quota_error_recognises_sdk_ratelimit_shapes():
    # google-genai raises compat_errors.RateLimitError (own class hierarchy) with
    # status_code=429 and a RESOURCE_EXHAUSTED message — none of which is
    # google.genai.errors.APIError. All three signals must be recognised.
    class RateLimitError(Exception):
        status_code = 429

    assert llm._is_quota_error(RateLimitError("boom"))

    class Weird(Exception):
        pass

    assert llm._is_quota_error(
        Weird("... Quota exceeded for metric: generate_content_free_tier_requests ...")
    )
    assert not llm._is_quota_error(ValueError("invalid schema field"))


async def test_sdk_ratelimit_error_advances_fallback(monkeypatch):
    """A raw SDK-style RateLimitError from _call_gemini must advance the chain,
    not kill the run (regression: the 429 class isn't errors.APIError)."""
    from app.llm.errors import QuotaOrRateLimitError

    tiers = settings.gemini_model_tiers

    class RateLimitError(Exception):
        status_code = 429

    def behaviour(api_key, model):
        if model == tiers[0]:
            # simulate what _call_gemini does with a real SDK 429
            raise QuotaOrRateLimitError("429 RESOURCE_EXHAUSTED")
        return '{"value": "recovered"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)
    result = await llm.generate_structured("q", _Answer)
    assert result.value == "recovered"


async def test_non_quota_error_raises_immediately(monkeypatch):
    def behaviour(api_key, model):
        raise ValueError("malformed request")

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    with pytest.raises(ValueError, match="malformed request"):
        await llm.generate_structured("q", _Answer)
    assert len(rec.calls) == 1  # no fallback advancement


async def test_multi_account_fallback(monkeypatch):
    tiers = settings.gemini_model_tiers

    def behaviour(api_key, model):
        if api_key == "key1":
            raise QuotaOrRateLimitError("RESOURCE_EXHAUSTED")
        if api_key == "key2" and model == tiers[0]:
            return '{"value": "account-2-tier-1"}'
        raise AssertionError(f"unexpected call {api_key}/{model}")

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    result = await llm.generate_structured("q", _Answer)
    assert result.value == "account-2-tier-1"
    # all 7 tiers tried under key1, then key2 tier 1
    assert [c["model"] for c in rec.calls if c["api_key"] == "key1"] == tiers
    assert rec.calls[-1] == {"api_key": "key2", "model": tiers[0]}


async def test_all_tiers_all_accounts_exhausted(monkeypatch):
    def behaviour(api_key, model):
        raise QuotaOrRateLimitError("429")

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    with pytest.raises(AllLLMTiersExhaustedError):
        await llm.generate_text("q")
    assert len(rec.calls) == 3 * len(settings.gemini_model_tiers)


async def test_cache_hit_skips_second_call(monkeypatch):
    def behaviour(api_key, model):
        return '{"value": "computed-once"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    first = await llm.generate_structured("same prompt", _Answer)
    second = await llm.generate_structured("same prompt", _Answer)
    assert first.value == second.value == "computed-once"
    assert len(rec.calls) == 1  # second served from cache


async def test_transient_5xx_advances_like_a_quota_error(monkeypatch):
    from app.llm.errors import TransientServerError

    tiers = settings.gemini_model_tiers

    def behaviour(api_key, model):
        if model == tiers[0]:
            raise TransientServerError("500 gemini-3.8-flash is currently experiencing high demand")
        return '{"value": "past-the-500"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)
    result = await llm.generate_structured("q", _Answer)
    assert result.value == "past-the-500"
    assert [c["model"] for c in rec.calls] == [tiers[0], tiers[1]]


async def test_is_transient_error_classification():
    class InternalServerError(Exception):
        status_code = 503

    assert llm._is_transient_error(InternalServerError("boom"))
    assert llm._is_transient_error(Exception("The model is currently overloaded, try again later"))
    assert not llm._is_transient_error(Exception("invalid json schema"))
    assert not llm._is_transient_error(ValueError("400 bad request"))


async def test_cooldown_skips_dead_tier_on_next_call(monkeypatch):
    tiers = settings.gemini_model_tiers
    seen: list[str] = []

    def behaviour(api_key, model):
        seen.append(model)
        if model in (tiers[0], tiers[1]):
            raise QuotaOrRateLimitError("429")
        return '{"value": "ok"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    await llm.generate_structured("first", _Answer)
    first_call_count = len(rec.calls)
    assert tiers[0] in seen and tiers[1] in seen  # probed once

    seen.clear()
    await llm.generate_structured("second", _Answer)
    # tiers 0 and 1 are on cooldown now — the second call must NOT re-probe them
    assert tiers[0] not in seen
    assert tiers[1] not in seen
    assert seen[0] == tiers[2]


async def test_groq_leads_then_gemini_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider_order", "groq,gemini")
    monkeypatch.setattr(settings, "groq_api_keys", "gk1")
    monkeypatch.setattr(settings, "groq_model_tiers_raw", "llama-3.3-70b-versatile,llama-3.1-8b-instant")

    calls: list[tuple[str, str]] = []

    def groq_call(api_key, model, prompt, system_prompt, json_schema):
        calls.append(("groq", model))
        raise QuotaOrRateLimitError("groq 429")

    def gemini_call(api_key, model, prompt, system_prompt, json_schema):
        calls.append(("gemini", model))
        return '{"value": "from-gemini"}'

    monkeypatch.setattr(llm, "_call_groq", groq_call)
    monkeypatch.setattr(llm, "_call_gemini", gemini_call)

    result = await llm.generate_structured("q", _Answer)
    assert result.value == "from-gemini"
    # both groq tiers tried first, then gemini tier 1
    assert calls[0] == ("groq", "llama-3.3-70b-versatile")
    assert calls[1] == ("groq", "llama-3.1-8b-instant")
    assert calls[2][0] == "gemini"


async def test_strip_json_fences():
    assert llm._strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm._strip_json_fences('{"a": 1}') == '{"a": 1}'


async def test_cache_invalidated_by_prompt_version_bump(monkeypatch):
    def behaviour(api_key, model):
        return '{"value": "v"}'

    rec = _make_call_recorder(behaviour)
    monkeypatch.setattr(llm, "_call_gemini", rec)

    await llm.generate_structured("stable prompt", _Answer)
    assert len(rec.calls) == 1

    monkeypatch.setattr(settings, "llm_prompt_version", "v2")
    await llm.generate_structured("stable prompt", _Answer)
    assert len(rec.calls) == 2  # version bump forced a fresh call
