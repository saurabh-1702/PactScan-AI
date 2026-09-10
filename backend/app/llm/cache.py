"""Layer 1 of the LLM abstraction — a local file-based response cache.

Checked before any API call. A hit means the model-tier / account fallback
logic never runs at all, which is the single most effective quota-conservation
measure during iterative development (the same fixture contracts are otherwise
re-processed identically on every restart).

The cache key deliberately includes ``LLM_PROMPT_VERSION``: bump that value in
``backend\\.env`` whenever prompt/schema/extraction logic changes, and every old
cache entry becomes a miss — a stale answer computed under outdated logic is
never silently served.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("pactscan.llm.cache")


def compute_cache_key(prompt: str, schema_name: str, prompt_version: str) -> str:
    """Stable SHA-256 of ``prompt + schema_name + prompt_version``."""
    joined = f"{prompt}\x1f{schema_name}\x1f{prompt_version}"
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _cache_dir() -> Path:
    d = Path(settings.llm_cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file(cache_key: str) -> Path:
    return _cache_dir() / f"{cache_key}.json"


def get_cached_response(cache_key: str) -> str | None:
    """Return the cached response text, or ``None`` on a miss / when disabled."""
    if not settings.llm_cache_enabled:
        return None
    path = _cache_file(cache_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload["response_text"]
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Ignoring unreadable cache entry %s: %s", path.name, exc)
        return None


def set_cached_response(cache_key: str, response_text: str) -> None:
    """Persist a response. No-op when caching is disabled."""
    if not settings.llm_cache_enabled:
        return
    path = _cache_file(cache_key)
    try:
        path.write_text(
            json.dumps({"cache_key": cache_key, "response_text": response_text}),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write cache entry %s: %s", path.name, exc)
