"""LLM abstraction error types."""

from __future__ import annotations


class QuotaOrRateLimitError(Exception):
    """A quota / rate-limit error (HTTP 429, RESOURCE_EXHAUSTED).

    This is the *only* error type that advances the model-tier / account
    fallback loop. Every other exception propagates immediately so real bugs
    (malformed request, invalid schema, auth failure) are never masked as
    quota problems.
    """


class AllLLMTiersExhaustedError(Exception):
    """Raised when every model tier under every configured account returned a
    quota / rate-limit error for a single call."""
