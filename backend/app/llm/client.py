"""Provider-agnostic LLM client.

Fallback order for every call (a cache miss):

    cache  ->  for each provider in LLM_PROVIDER_ORDER (default: groq, then gemini):
                   for each API key (account):
                       for each model tier:
                           call; on 429 / 5xx -> cooldown that (provider, account,
                           model) tuple and advance; on success -> return.

Groq's free tier is far larger than Gemini's, so it leads; Gemini is the
documented fallback (and Claude / a funded provider is the further upgrade path).

Cooldown memory means once a tier returns 429 in a run, later calls skip it for
``LLM_TIER_COOLDOWN_SECONDS`` instead of re-probing it every time.

This is the only module that imports a provider SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import settings
from app.llm.cache import compute_cache_key, get_cached_response, set_cached_response
from app.llm.errors import (
    AllLLMTiersExhaustedError,
    QuotaOrRateLimitError,
    TransientServerError,
)

logger = logging.getLogger("pactscan.llm")

TModel = TypeVar("TModel", bound=BaseModel)
_TEXT_SCHEMA_NAME = "__text__"

_groq_clients: dict[str, Any] = {}
_gemini_clients: dict[str, Any] = {}

# (provider, account_index, model) -> monotonic time the cooldown expires
_cooldowns: dict[tuple[str, int, str], float] = {}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def generate_structured(
    prompt: str, schema: type[TModel], system_prompt: str | None = None
) -> TModel:
    schema_name = schema.__name__
    cache_key = compute_cache_key(prompt, schema_name, settings.llm_prompt_version)

    cached = get_cached_response(cache_key)
    if cached is not None:
        logger.info("Cache hit (%s)", schema_name)
        return schema.model_validate_json(cached)

    raw = await _resolve(prompt, system_prompt, schema.model_json_schema(), schema_name)
    raw = _strip_json_fences(raw)
    result = schema.model_validate_json(raw)
    set_cached_response(cache_key, raw)
    return result


async def generate_text(prompt: str, system_prompt: str | None = None) -> str:
    cache_key = compute_cache_key(prompt, _TEXT_SCHEMA_NAME, settings.llm_prompt_version)

    cached = get_cached_response(cache_key)
    if cached is not None:
        logger.info("Cache hit (text)")
        return cached

    raw = await _resolve(prompt, system_prompt, None, _TEXT_SCHEMA_NAME)
    set_cached_response(cache_key, raw)
    return raw


# --------------------------------------------------------------------------- #
# Fallback resolution
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Attempt:
    provider: str
    account_index: int
    api_key: str
    model: str

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.provider, self.account_index, self.model)


def _attempt_plan() -> list[_Attempt]:
    plan: list[_Attempt] = []
    for provider in settings.provider_order:
        if provider == "groq":
            keys, tiers = settings.groq_api_key_list, settings.groq_model_tiers
        elif provider == "gemini":
            keys, tiers = settings.gemini_api_key_list, settings.gemini_model_tiers
        else:
            logger.warning("Unknown LLM provider %r in LLM_PROVIDER_ORDER — skipping", provider)
            continue
        for account_index, api_key in enumerate(keys):
            for model in tiers:
                plan.append(_Attempt(provider, account_index, api_key, model))
    return plan


def _cooldown_remaining(attempt: _Attempt) -> float:
    return max(0.0, _cooldowns.get(attempt.key, 0.0) - time.monotonic())


def _put_on_cooldown(attempt: _Attempt) -> None:
    _cooldowns[attempt.key] = time.monotonic() + settings.llm_tier_cooldown_seconds


async def _resolve(
    prompt: str,
    system_prompt: str | None,
    json_schema: dict | None,
    schema_name: str,
) -> str:
    plan = _attempt_plan()
    if not plan:
        raise RuntimeError(
            "No LLM providers configured — set GROQ_API_KEYS and/or GEMINI_API_KEYS in backend\\.env"
        )

    for round_index in range(2):  # one extra pass after a bounded wait
        skipped = 0
        tried: list[str] = []
        last_error: Exception | None = None

        for attempt in plan:
            if _cooldown_remaining(attempt) > 0:
                skipped += 1
                continue
            caller = _call_groq if attempt.provider == "groq" else _call_gemini
            try:
                result = await asyncio.to_thread(
                    caller, attempt.api_key, attempt.model, prompt, system_prompt, json_schema
                )
                logger.info(
                    "LLM: %s / acct %d / %s answered [%s]%s",
                    attempt.provider,
                    attempt.account_index + 1,
                    attempt.model,
                    schema_name,
                    f"  (skipped {skipped} on cooldown)" if skipped else "",
                )
                return result
            except (QuotaOrRateLimitError, TransientServerError) as exc:
                _put_on_cooldown(attempt)
                last_error = exc
                tried.append(f"{attempt.provider}/{attempt.model}")
                logger.warning(
                    "%s on %s / acct %d / %s — advancing",
                    type(exc).__name__,
                    attempt.provider,
                    attempt.account_index + 1,
                    attempt.model,
                )
                continue
            # any other exception propagates immediately (real bug, not quota)

        remaining = [_cooldown_remaining(a) for a in plan]
        soonest = min((r for r in remaining if r > 0), default=0.0)
        if round_index == 0 and 0 < soonest <= 20:
            logger.warning(
                "All LLM tiers on cooldown — waiting %.0fs for the soonest to clear", soonest
            )
            await asyncio.sleep(soonest + 0.5)
            continue
        raise AllLLMTiersExhaustedError(
            f"All LLM tiers exhausted or on cooldown. Tried this round: {tried or '(all cooled)'}. "
            f"Last error: {last_error}"
        )
    raise AllLLMTiersExhaustedError("All LLM tiers exhausted after retry pass")


# --------------------------------------------------------------------------- #
# Provider call sites (monkeypatched in tests)
# --------------------------------------------------------------------------- #
def _call_groq(
    api_key: str, model: str, prompt: str, system_prompt: str | None, json_schema: dict | None
) -> str:
    from groq import Groq

    client = _groq_clients.get(api_key)
    if client is None:
        client = _groq_clients[api_key] = Groq(api_key=api_key, max_retries=0)

    system = system_prompt or ""
    if json_schema is not None:
        system = (system + "\n\n" if system else "") + (
            "Respond with ONLY one JSON object — no prose, no markdown fences — that "
            "conforms to this JSON schema:\n" + json.dumps(json_schema)
        )
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_completion_tokens": 8000,
    }
    if json_schema is not None:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - classified below
        _raise_classified(exc)

    content = resp.choices[0].message.content if resp.choices else None
    if not content:
        raise RuntimeError(f"Groq returned empty content (model={model})")
    return content


def _call_gemini(
    api_key: str, model: str, prompt: str, system_prompt: str | None, json_schema: dict | None
) -> str:
    from google.genai import interactions as genai_interactions

    client = _gemini_clients.get(api_key)
    if client is None:
        from google import genai
        from google.genai import types as genai_types

        client = _gemini_clients[api_key] = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                retry_options=genai_types.HttpRetryOptions(attempts=1)  # no SDK-internal retry
            ),
        )

    kwargs: dict[str, Any] = {"model": model, "input": prompt}
    if system_prompt:
        kwargs["system_instruction"] = system_prompt
    if json_schema is not None:
        kwargs["response_format"] = genai_interactions.TextResponseFormat(
            type="text", mime_type="application/json", schema_=json_schema
        )

    try:
        interaction = client.interactions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - classified below
        _raise_classified(exc)

    output = getattr(interaction, "output_text", None)
    if not output:
        raise RuntimeError(
            f"Gemini returned no output_text (model={model}, "
            f"status={getattr(interaction, 'status', '?')}, "
            f"errors={getattr(interaction, 'errors', None)})"
        )
    return output


# --------------------------------------------------------------------------- #
# Error classification
# --------------------------------------------------------------------------- #
_QUOTA_NAMES = {"RateLimitError", "ResourceExhausted", "ResourceExhaustedError"}
_QUOTA_MARKERS = ("RESOURCE_EXHAUSTED", "RATE LIMIT", "QUOTA", "TOO MANY REQUESTS", "TOO_MANY_REQUESTS")
_TRANSIENT_NAMES = {"InternalServerError", "ServiceUnavailableError", "APIConnectionError", "APITimeoutError"}
_TRANSIENT_MARKERS = (
    "HIGH DEMAND",
    "OVERLOADED",
    "TRY AGAIN LATER",
    "TEMPORARILY UNAVAILABLE",
    "SERVICE UNAVAILABLE",
    "INTERNAL ERROR",
    "INTERNAL SERVER ERROR",
    "502 ",
    "503 ",
    "504 ",
)


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def _is_quota_error(exc: Exception) -> bool:
    if type(exc).__name__ in _QUOTA_NAMES:
        return True
    if _status_code(exc) == 429:
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status", None)
    if code in ("RESOURCE_EXHAUSTED", "too_many_requests"):
        return True
    text = str(exc).upper()
    return any(m in text for m in _QUOTA_MARKERS)


def _is_transient_error(exc: Exception) -> bool:
    sc = _status_code(exc)
    if sc is not None and 500 <= sc <= 599:
        return True
    if type(exc).__name__ in _TRANSIENT_NAMES:
        return True
    text = str(exc).upper()
    return any(m in text for m in _TRANSIENT_MARKERS)


def _raise_classified(exc: Exception):
    """Translate a provider SDK exception into our fallback-control exceptions,
    or re-raise it unchanged if it is a real (non-transient) error."""
    if _is_quota_error(exc):
        raise QuotaOrRateLimitError(str(exc)[:300]) from exc
    if _is_transient_error(exc):
        raise TransientServerError(str(exc)[:300]) from exc
    raise exc


# --------------------------------------------------------------------------- #
def _strip_json_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _reset_clients_for_tests() -> None:
    _groq_clients.clear()
    _gemini_clients.clear()
    _cooldowns.clear()
