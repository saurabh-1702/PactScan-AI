"""Provider-agnostic LLM abstraction.

Every agent call goes through ``generate_structured`` / ``generate_text`` in
``client.py``. No agent module instantiates a Gemini client directly, so swapping
the provider, model chain, or account count is a one-file change.
"""

from app.llm.client import generate_structured, generate_text
from app.llm.errors import AllLLMTiersExhaustedError, QuotaOrRateLimitError

__all__ = [
    "generate_structured",
    "generate_text",
    "AllLLMTiersExhaustedError",
    "QuotaOrRateLimitError",
]
