"""Global configuration settings for InvestManager."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    log_level: str = "INFO"

    # Database - SQLite (new default)
    database_backend: Literal["sqlite", "postgresql"] = "sqlite"
    sqlite_db_path: str = Field(
        default="./data/investmanager.db",
        description="SQLite database file path",
    )

    # Database - PostgreSQL (optional)
    database_url: str = Field(
        default="postgresql://investuser:investpass@localhost:5432/investmanager",
        description="PostgreSQL database connection URL",
    )
    database_pool_size: int = 10

    # Local Cache (replaces Redis)
    local_cache_enabled: bool = True
    local_cache_max_size: int = 1000
    local_cache_ttl: int = 300  # 5 minutes

    # Redis (optional, for backward compatibility)
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # API Keys
    tushare_token: str = ""
    alpha_vantage_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # LLM Provider Settings
    llm_provider: Literal["openai", "anthropic", "alibaba_bailian"] = "openai"
    llm_model: str = ""  # Model name, provider-specific defaults used if empty

    # Alibaba Bailian (阿里百炼 / DashScope)
    alibaba_bailian_api_key: str = ""
    alibaba_bailian_model: str = "qwen-turbo"  # qwen-turbo, qwen-plus, qwen-max, etc.

    # Scheduler
    scheduler_enabled: bool = True
    daily_analysis_time: str = "18:00"

    # Report
    report_output_dir: str = "./reports"

    # Email - SMTP (legacy, for backward compatibility)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""

    # Email - OAuth2 (recommended)
    email_provider: Literal["gmail", "outlook", "qq", "custom"] = "gmail"
    email_oauth2_client_id: str = ""
    email_oauth2_client_secret: str = ""
    email_oauth2_refresh_token: str = ""
    email_oauth2_token_url: str = ""
    email_from_address: str = ""
    email_to_addresses: list[str] = Field(default_factory=list)

    # Feishu Integration
    feishu_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_encrypt_key: str = ""
    feishu_verification_token: str = ""
    feishu_bitable_token: str = ""
    feishu_bitable_table_id: str = ""
    feishu_folder_token: str = ""

    # Cache settings
    cache_ttl_seconds: int = 300  # 5 minutes default
    cache_max_size: int = 1000

    # Backtest settings
    default_initial_capital: float = 1_000_000.0
    default_commission: float = 0.0003  # 0.03%

    # Web Search Settings
    web_search_enabled: bool = True
    web_search_engine: Literal["duckduckgo", "tavily", "bing"] = "duckduckgo"
    web_search_max_results: int = 5
    web_search_timeout: int = 10  # seconds

    # Optional API keys for premium search engines
    tavily_api_key: str = ""
    bing_search_api_key: str = ""
    bing_search_endpoint: str = ""

    # Claude Code Integration (for DEV mode)
    claude_code_enabled: bool = False
    claude_code_working_dir: str = ""  # Working directory for Claude Code, defaults to current dir

    # Multi-model Configuration
    multi_model_enabled: bool = True
    consensus_min_models: int = 3
    consensus_max_rounds: int = 3
    consensus_timeout_seconds: int = 60

    # Model routing preferences (should sum to 1.0)
    routing_quality_weight: float = 0.5
    routing_latency_weight: float = 0.3
    routing_cost_weight: float = 0.2
    routing_exploration_rate: float = 0.1  # 10% of requests explore lower-ranked models

    # Available models on Alibaba Bailian
    alibaba_available_models: list[str] = [
        "qwen3.5-plus",
        "qwen3-max-2026-01-23",
        "qwen3-coder-next",
        "qwen3-coder-plus",
        "glm-5",
        "kimi-k2.5",
        "MiniMax-M2.5",
    ]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def async_database_url(self) -> str:
        """Get async database URL for asyncpg."""
        if self.database_backend == "sqlite":
            return f"sqlite+aiosqlite:///{self.sqlite_db_path}"
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://")

    @property
    def sqlite_path(self) -> Path:
        """Get SQLite database path as Path object."""
        return Path(self.sqlite_db_path)

    def ensure_sqlite_directory(self) -> None:
        """Ensure SQLite database directory exists."""
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()