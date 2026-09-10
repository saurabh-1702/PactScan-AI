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

    # --- LLM provider (Google Gemini, free tier, multi-account) ---
    gemini_api_keys: str = ""
    llm_provider: str = "gemini"

    gemini_model_tier_1: str = "gemini-3.8-flash"
    gemini_model_tier_2: str = "gemini-3.7-flash"
    gemini_model_tier_3: str = "gemini-3.6-flash"
    gemini_model_tier_4: str = "gemini-3.5-flash"
    gemini_model_tier_5: str = "gemini-3.5-flash-lite"
    gemini_model_tier_6: str = "gemini-3.1-flash-lite"
    gemini_model_tier_7: str = "gemma-4-31b"

    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_model_if_billing_enabled: str = "gemini-3.1-pro-preview"

    # --- LLM response cache ---
    llm_cache_enabled: bool = True
    llm_cache_dir: str = ".llm_cache"
    llm_prompt_version: str = "v2"  # bump on any prompt/schema change (Phase 1: batched NLI = v2)

    # --- Optional secondary provider ---
    anthropic_api_key: str = ""

    # --- LlamaParse (Phase 1+) ---
    llama_cloud_api_key: str = ""
    llama_parse_tier: str = "fast"  # fast | cost_effective | agentic | agentic_plus

    # --- App ---
    environment: str = "development"

    @property
    def gemini_api_key_list(self) -> list[str]:
        """Parsed, priority-ordered list of Google AI Studio API keys."""
        return [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]

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
