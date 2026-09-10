"""Provider-agnostic LLM client.

Three layers, checked in this exact order for every call:

    1. local response cache          (app/llm/cache.py)
    2. 7-tier model fallback chain    (per account, quality-first)
    3. multi-account fallback         (walks the full tier chain per account
                                       before advancing to the next account)

Only quota / rate-limit errors advance the loop. Every other error propagates
immediately so real bugs are never masked as quota problems.

Provider: Google Gemini, via ``google-genai``'s Interactions API
(``client.interactions.create``) — the Gemini equivalent of tool-use / structured
output. This is the only file that imports the Gemini SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import settings
from app.llm.cache import compute_cache_key, get_cached_response, set_cached_response
from app.llm.errors import AllLLMTiersExhaustedError, QuotaOrRateLimitError

logger = logging.getLogger("pactscan.llm")

TModel = TypeVar("TModel", bound=BaseModel)

_TEXT_SCHEMA_NAME = "__text__"

# Memoised Gemini clients, one per API key.
_clients: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def generate_structured(
    prompt: str,
    schema: type[TModel],
    system_prompt: str | None = None,
) -> TModel:
    """Call the LLM and return a validated instance of ``schema``."""
    schema_name = schema.__name__
    cache_key = compute_cache_key(prompt, schema_name, settings.llm_prompt_version)

    cached = get_cached_response(cache_key)
    if cached is not None:
        logger.info("Cache hit (%s)", schema_name)
        return schema.model_validate_json(cached)

    raw = await _resolve(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=schema.model_json_schema(),
        schema_name=schema_name,
    )
    result = schema.model_validate_json(raw)
    set_cached_response(cache_key, raw)
    return result


async def generate_text(prompt: str, system_prompt: str | None = None) -> str:
    """Call the LLM and return plain text."""
    cache_key = compute_cache_key(prompt, _TEXT_SCHEMA_NAME, settings.llm_prompt_version)

    cached = get_cached_response(cache_key)
    if cached is not None:
        logger.info("Cache hit (text)")
        return cached

    raw = await _resolve(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=None,
        schema_name=_TEXT_SCHEMA_NAME,
    )
    set_cached_response(cache_key, raw)
    return raw


# --------------------------------------------------------------------------- #
# Layer 2 + 3 — model-tier chain wrapped in multi-account fallback
# --------------------------------------------------------------------------- #
async def _resolve(
    prompt: str,
    system_prompt: str | None,
    json_schema: dict | None,
    schema_name: str,
) -> str:
    api_keys = settings.gemini_api_key_list
    if not api_keys:
        raise RuntimeError(
            "GEMINI_API_KEYS is empty — set it in backend\\.env before making live LLM calls."
        )
    tiers = settings.gemini_model_tiers

    for account_index, api_key in enumerate(api_keys):
        for tier_index, model_name in enumerate(tiers):
            try:
                result = await asyncio.to_thread(
                    _call_gemini,
                    api_key=api_key,
                    model=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    json_schema=json_schema,
                )
                logger.info(
                    "Answered by Account %d, Tier %d (%s) [%s]",
                    account_index + 1,
                    tier_index + 1,
                    model_name,
                    schema_name,
                )
                return result
            except QuotaOrRateLimitError:
                logger.warning(
                    "Quota/rate-limit on Account %d, Tier %d (%s) — advancing",
                    account_index + 1,
                    tier_index + 1,
                    model_name,
                )
                continue
            # any other exception propagates immediately — not caught here
        logger.warning(
            "All %d tiers exhausted for Account %d — advancing to next account",
            len(tiers),
            account_index + 1,
        )

    raise AllLLMTiersExhaustedError(
        "All tiers exhausted across all configured accounts"
    )


# --------------------------------------------------------------------------- #
# The single point where the Gemini SDK is called. Tests monkeypatch this.
# --------------------------------------------------------------------------- #
def _get_client(api_key: str) -> Any:
    if api_key not in _clients:
        from google import genai  # imported lazily so tests never need the SDK path

        _clients[api_key] = genai.Client(api_key=api_key)
    return _clients[api_key]


def _call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str | None,
    json_schema: dict | None,
) -> str:
    """Make one Gemini Interactions API call. Returns the raw output text.

    Translates quota / rate-limit failures into ``QuotaOrRateLimitError`` so the
    fallback loop can advance; every other failure propagates unchanged.
    """
    from google.genai import errors as genai_errors
    from google.genai import interactions as genai_interactions

    client = _get_client(api_key)

    kwargs: dict[str, Any] = {"model": model, "input": prompt}
    if system_prompt:
        kwargs["system_instruction"] = system_prompt
    if json_schema is not None:
        kwargs["response_format"] = genai_interactions.TextResponseFormat(
            type="text",
            mime_type="application/json",
            schema_=json_schema,
        )

    try:
        interaction = client.interactions.create(**kwargs)
    except genai_errors.APIError as exc:
        if _is_quota_error(exc):
            raise QuotaOrRateLimitError(str(exc)) from exc
        raise

    output = getattr(interaction, "output_text", None)
    if not output:
        raise RuntimeError(
            f"Gemini returned no output_text (model={model}, "
            f"status={getattr(interaction, 'status', '?')}, "
            f"errors={getattr(interaction, 'errors', None)})"
        )
    return output


def _is_quota_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status", None)
    if code == 429 or code == "RESOURCE_EXHAUSTED":
        return True
    text = str(exc).upper()
    return "RESOURCE_EXHAUSTED" in text or "RATE LIMIT" in text or "QUOTA" in text


def _reset_clients_for_tests() -> None:
    _clients.clear()
