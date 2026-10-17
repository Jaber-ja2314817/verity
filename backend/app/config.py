from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

StructuredMode = Literal["tool_forced", "tool_auto", "text_json"]


class Settings(BaseSettings):
    """All runtime settings. Defaults match .env.example for every non-secret value."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Nebius Token Factory
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    model_fast: str = ""
    model_judge: str = ""
    structured_mode_fast: StructuredMode = "tool_forced"
    structured_mode_judge: StructuredMode = "tool_forced"
    # Nemotron reasoning on/off per model. Off for FAST: its reasoning can use the whole token
    # budget before it calls the submit tool (see docs/FEEDBACK.md).
    thinking_fast: bool = False
    thinking_judge: bool = True

    # Tavily
    tavily_api_key: str = ""
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = 5

    # Pipeline limits
    max_input_chars: int = 5000
    max_claims: int = 3
    queries_per_claim: int = 3
    max_sources_per_claim: int = 8
    max_sources_per_domain: int = 2
    source_chars: int = 1500
    max_extra_queries: int = 2
    check_timeout_seconds: int = 240
    search_cache_hours: int = 24

    # Protection
    rate_limit_per_ip: int = 5
    rate_limit_window_seconds: int = 600
    daily_check_cap: int = 150
    max_concurrent_checks: int = 3

    # Cost display (USD per 1M tokens)
    price_fast_in: float = 0.06
    price_fast_out: float = 0.24
    price_judge_in: float = 1.0
    price_judge_out: float = 3.0

    # App
    data_dir: str = "./data"
    log_level: str = "INFO"

    @property
    def structured_modes(self) -> dict[str, StructuredMode]:
        return {
            self.model_fast: self.structured_mode_fast,
            self.model_judge: self.structured_mode_judge,
        }

    @property
    def thinking(self) -> dict[str, bool]:
        return {self.model_fast: self.thinking_fast, self.model_judge: self.thinking_judge}

    @property
    def prices(self) -> dict[str, tuple[float, float]]:
        return {
            self.model_fast: (self.price_fast_in, self.price_fast_out),
            self.model_judge: (self.price_judge_in, self.price_judge_out),
        }


def startup_problems(s: Settings) -> list[str]:
    """Return every reason the app must refuse to start. Empty list means OK."""
    problems = [
        f"{name} is not set"
        for name, value in [
            ("NEBIUS_API_KEY", s.nebius_api_key),
            ("TAVILY_API_KEY", s.tavily_api_key),
            ("MODEL_FAST", s.model_fast),
            ("MODEL_JUDGE", s.model_judge),
        ]
        if not value.strip()
    ]
    if s.model_fast and s.model_fast == s.model_judge:
        problems.append("MODEL_FAST and MODEL_JUDGE must be different models (independent jury)")
    for name, value in [("MODEL_FAST", s.model_fast), ("MODEL_JUDGE", s.model_judge)]:
        if value and "nvidia" not in value.lower():
            problems.append(f"{name} must be an NVIDIA model (got {value!r})")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
