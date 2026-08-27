"""Application configuration management using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # PostgreSQL Core / Read-Write
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "fraud_detection"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fraud_detection"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/fraud_detection"

    # Dedicated Read-Only DB Role for Agent SQL execution
    AGENT_DB_USER: str = "agent_reader"
    AGENT_DB_PASSWORD: str = "agent_reader_password"
    AGENT_DATABASE_URL: str = (
        "postgresql+asyncpg://agent_reader:agent_reader_password@localhost:5432/fraud_detection"
    )

    # LLM Settings
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
