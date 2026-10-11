from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_EMBEDDING_MODEL: str = "qwen3-embedding:0.6b"
    OLLAMA_EMBEDDING_DIMENSIONS: int = 1024
    OLLAMA_GENERATION_MODEL: str = "qwen3.5:4b"
    OLLAMA_GENERATION_TIMEOUT_SECONDS: float = 120.0
    BOQ_IMPORT_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024
    RAG_MAX_COSINE_DISTANCE: float = 0.55

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


settings = Settings()