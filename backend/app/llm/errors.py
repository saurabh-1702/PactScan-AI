"""LLM abstraction error types."""

from __future__ import annotations


class QuotaOrRateLimitError(Exception):
    """A quota / rate-limit error (HTTP 429, RESOURCE_EXHAUSTED).

    Advances the model-tier / account / provider fallback loop and puts that
    (provider, account, model) tuple on cooldown.
    """


class TransientServerError(Exception):
    """A transient upstream error (HTTP 5xx, "model overloaded", "try again
    later"). Treated like a rate-limit for fallback purposes — advance and put
    the tuple on a short cooldown rather than failing the whole request.
    """


class AllLLMTiersExhaustedError(Exception):
    """Every provider / account / model tier was exhausted or on cooldown for a
    single call."""
