from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # AI Provider Configuration
    AI_PROVIDER: str = "gemini"  # "gemini" or "anthropic"

    # Google Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # Anthropic Claude (optional fallback)
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"

    # External APIs
    CROSSREF_BASE_URL: str = "https://api.crossref.org"
    OPENALEX_BASE_URL: str = "https://api.openalex.org"
    SEMANTIC_SCHOLAR_BASE_URL: str = "https://api.semanticscholar.org/graph/v1"
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = None

    # Processing
    MAX_FILE_SIZE_MB: int = 20
    CHUNK_SIZE: int = 4000
    MAX_CLAIMS_PER_DOC: int = 50

    # AI Request settings
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_RETRIES: int = 3
    AI_RETRY_BACKOFF_BASE: float = 2.0

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()