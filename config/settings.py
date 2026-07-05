"""Global settings and configuration for the ACH Forecasting Agent."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # LLM Configuration
    llm_model: str = Field(
        default="llama3.3",
        description="Local LLM model name (e.g., 'llama3.3', 'mistral'); must support llm_context_window",
    )
    llm_endpoint: str = Field(
        default="http://localhost:11434",
        description="Local LLM service endpoint (Ollama/vLLM)",
    )
    llm_temperature: float = Field(
        default=0.7,
        description="Temperature for hypothesis evaluation (multi-pass sampling)",
    )
    llm_num_passes: int = Field(
        default=10,
        description="Number of temperature-sampled passes for confidence scoring",
    )
    llm_context_window: int = Field(
        default=8192,
        description=(
            "Ollama num_ctx (prompt context window in tokens). Full article "
            "bodies can be long, so this must be large enough — and the chosen "
            "model must support it (e.g. llama3.1) — or Ollama truncates the "
            "prompt. Set 0 to use the model default."
        ),
    )
    llm_max_tokens: int = Field(
        default=512,
        description="Max tokens to generate per LLM call (Ollama num_predict)",
    )

    # Storage Configuration
    data_dir: Path = Field(
        default=Path("data"),
        description="Base directory for data storage",
    )
    logs_dir: Path = Field(
        default=Path("logs"),
        description="Directory for agent interaction logs",
    )

    # Web Scraping Configuration
    #
    # Articles are sourced from The Guardian Open Platform Content API rather
    # than by crawling reuters.com: Reuters prohibits scraping and licenses its
    # full text, whereas the Guardian's official developer API returns the full
    # article body for free. The literal "test" key works for development; for
    # production, register a free key at https://open-platform.theguardian.com/
    # and set GUARDIAN_API_KEY in .env.
    guardian_api_url: str = Field(
        default="https://content.guardianapis.com/search",
        description="The Guardian Content API search endpoint",
    )
    guardian_api_key: str = Field(
        default="test",
        description="Guardian API key ('test' for dev; set GUARDIAN_API_KEY for production)",
    )
    guardian_section: str = Field(
        default="world",
        description="Guardian section to restrict to (e.g. 'world'); empty string for all sections",
    )
    guardian_from_days: int = Field(
        default=150,
        description="Only fetch articles published within this many days (0 to disable)",
    )
    guardian_order_by: str = Field(
        default="relevance",
        description="Guardian result ordering: 'relevance', 'newest', or 'oldest'",
    )
    scraper_max_articles: int = Field(
        default=25,
        description="Max articles to ingest per run (Guardian page-size, max 200)",
    )
    use_system_truststore: bool = Field(
        default=True,
        description=(
            "Use the OS trust store for TLS verification (via the `truststore` "
            "package) instead of certifi's bundle. Required behind a "
            "TLS-inspecting corporate proxy whose CA is installed in the OS but "
            "not in certifi. Keeps certificate verification enabled."
        ),
    )
    scraper_timeout_seconds: int = Field(
        default=30,
        description="HTTP request timeout for web scraping",
    )
    scraper_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for failed scrape requests",
    )
    scraper_backoff_factor: float = Field(
        default=2.0,
        description="Exponential backoff multiplier for retries",
    )

    # Assessment Agent Configuration
    confidence_threshold: float = Field(
        default=0.6,
        description="Confidence threshold for human escalation (< threshold flags for review)",
    )
    evidence_marks: list[str] = Field(
        default=["++", "+", "N/A", "-", "--"],
        description="Valid evidence marks for hypothesis scoring",
    )

    # Hypothesis Configuration (to be loaded from hypothesis_config.yaml)
    hypotheses: Optional[list[str]] = Field(
        default=None,
        description="Target hypotheses for assessment (loaded from config file)",
    )

    # Agent Communication Configuration
    agent_timeout_seconds: int = Field(
        default=300,
        description="Timeout for agent state transitions (in seconds)",
    )
    enable_debug_logging: bool = Field(
        default=False,
        description="Enable verbose debug logging for agent interactions",
    )
    auto_git_sync: bool = Field(
        default=True,
        description=(
            "Commit and push data/matrix/ to origin/master after each run "
            "(set AUTO_GIT_SYNC=false to disable for local/experimental runs)"
        ),
    )

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Ensure required directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "matrix").mkdir(parents=True, exist_ok=True)
(settings.data_dir / "articles").mkdir(parents=True, exist_ok=True)
