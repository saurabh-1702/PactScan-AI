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
    monkeypatch.setattr(settings, "gemini_api_keys", "key1,key2,key3")
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
