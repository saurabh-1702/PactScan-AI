"""Application configuration.

Loads environment variables via pydantic-settings.

IMPORTANT: ``env_file=".env"`` resolves relative to the working directory the
backend process is started from, which is always ``backend\\``. The real ``.env``
file therefore must live at ``backend\\.env`` (copied from ``backend\\.env.example``).
Do NOT create a ``.env`` file at the project root — it will be silently ignored.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "testpassword123"

    # --- PostgreSQL (note host port 5433, not 5432) ---
    database_url: str = "postgresql://pactscan:testpassword123@localhost:5433/pactscan_dev"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM providers ---
    # Order the fallback walks: every account+tier of the first provider, then
    # the next. Groq's free tier is far larger than Gemini's, so it leads.
    llm_provider_order: str = "groq,gemini"
    llm_provider: str = "groq"  # legacy alias; provider_order is authoritative
    llm_tier_cooldown_seconds: int = 60

    # --- Groq (primary) ---
    groq_api_keys: str = ""
    # Verified against GET /openai/v1/models for the project's Groq account
    # (2026-09) — llama-3.3-70b-versatile / llama-3.1-8b-instant have been
    # retired from Groq. Re-check with `curl.exe https://api.groq.com/openai/v1/models
    # -H "Authorization: Bearer $GROQ_API_KEY"` if a tier ever 404s again.
    groq_model_tiers_raw: str = (
        "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b,"
        "qwen/qwen3.6-27b,openai/gpt-oss-safeguard-20b"
    )

    # --- Google Gemini (fallback, free tier, multi-account) ---
    gemini_api_keys: str = ""

    gemini_model_tier_1: str = "gemini-3.8-flash"
    gemini_model_tier_2: str = "gemini-3.7-flash"
    gemini_model_tier_3: str = "gemini-3.6-flash"
    gemini_model_tier_4: str = "gemini-3.5-flash"
    gemini_model_tier_5: str = "gemini-3.5-flash-lite"
    gemini_model_tier_6: str = "gemini-3.1-flash-lite"
    gemini_model_tier_7: str = "gemma-4-31b"

    gemini_embedding_model: str = "gemini-embedding-001"
    # Forced via EmbedContentConfig.output_dimensionality so the Neo4j vector index's
    # fixed dimension never mismatches the model's own default output size.
    embedding_dimensions: int = 768
    gemini_model_if_billing_enabled: str = "gemini-3.1-pro-preview"

    # --- LLM response cache ---
    llm_cache_enabled: bool = True
    llm_cache_dir: str = ".llm_cache"
    llm_prompt_version: str = "v3"  # bump on any prompt/schema change (v3: conservative NLI prompt + Groq)

    # --- Optional secondary provider ---
    anthropic_api_key: str = ""

    # --- LlamaParse (Phase 1+) ---
    llama_cloud_api_key: str = ""
    llama_parse_tier: str = "fast"  # fast | cost_effective | agentic | agentic_plus

    # --- Ask agent (Phase 4) ---
    # Cosine-similarity floor below which a content question abstains instead
    # of answering from weak/irrelevant matches. Not verified against a live
    # key at build time (like Phase 2's embedding dimension) — tune in .env if
    # live testing shows it's too strict (over-abstaining) or too loose
    # (answering from irrelevant clauses).
    ask_similarity_threshold: float = 0.35
    ask_top_k: int = 6

    # --- App ---
    environment: str = "development"

    @staticmethod
    def _csv(value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @property
    def provider_order(self) -> list[str]:
        return self._csv(self.llm_provider_order) or ["groq", "gemini"]

    @property
    def groq_api_key_list(self) -> list[str]:
        return self._csv(self.groq_api_keys)

    @property
    def groq_model_tiers(self) -> list[str]:
        return self._csv(self.groq_model_tiers_raw)

    @property
    def gemini_api_key_list(self) -> list[str]:
        """Parsed, priority-ordered list of Google AI Studio API keys."""
        return self._csv(self.gemini_api_keys)

    @property
    def gemini_model_tiers(self) -> list[str]:
        """The 7-tier model fallback chain, in order."""
        return [
            self.gemini_model_tier_1,
            self.gemini_model_tier_2,
            self.gemini_model_tier_3,
            self.gemini_model_tier_4,
            self.gemini_model_tier_5,
            self.gemini_model_tier_6,
            self.gemini_model_tier_7,
        ]


settings = Settings()
