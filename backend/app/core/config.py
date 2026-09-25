from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Listing Factory API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # PostgreSQL Database URL
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/listing_factory"

    # JWT Authentication configuration
    JWT_SECRET: str = "replace-with-a-secure-random-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Firebase Authentication configuration
    FIREBASE_SERVICE_ACCOUNT_JSON: Union[str, None] = None
    FIREBASE_SERVICE_ACCOUNT_PATH: Union[str, None] = None
    # Verifying an ID token needs the project id to check the token's audience.
    # A service account carries it; without one it has to be given explicitly,
    # which is what lets a dev machine verify tokens with no secret at all.
    FIREBASE_PROJECT_ID: Union[str, None] = None

    # Media storage configuration
    MEDIA_STORAGE_DIR: str = "./media"
    MAX_MEDIA_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB in bytes

    # Pipeline configuration
    PIPELINE_MAX_STAGE_ATTEMPTS: int = 3

    # Demo deployment
    #
    # The public demo has no sign-in: a visitor opens the site and uses it.
    # With this on, a request carrying no Authorization header resolves to one
    # shared seller (app/core/demo.py) rather than being rejected — which is
    # also what lets a processed photo load in a plain <img src>, since an
    # <img> cannot carry a bearer token. Never turn it on where real artisans'
    # listings live.
    DEMO_MODE: bool = False
    DEMO_SELLER_NAME: str = "Kirtikar Demo"
    # Live runs the demo will start per IST calendar day, across every visitor
    # combined. The site is only for the SIH judges, and every run spends real
    # Sarvam and Gemini credit on an unauthenticated endpoint. Past the cap the
    # site falls back to a recorded run. 0 is no limit.
    DEMO_MAX_RUNS_PER_DAY: int = 10
    # Where today's count is mirrored so a restart doesn't reset it. Only
    # durable if this is on storage that outlives the container.
    DEMO_LIMIT_STATE_PATH: Union[str, None] = None

    # AI & Speech Service configuration
    SARVAM_API_KEY: Union[str, None] = None
    GEMINI_API_KEY: Union[str, None] = None
    GEMINI_MODEL: str = "gemini-3.5-flash"
    # A multimodal extraction on the preferred model measures around 25s, so a
    # 30s ceiling trips its own read timeout on healthy calls.
    GEMINI_TIMEOUT_SECONDS: float = 90.0
    # Tried in order when the preferred model is overloaded. A listing written
    # by a lighter model beats one written from canned facts, so the chain is
    # exhausted before any synthetic fallback.
    GEMINI_FALLBACK_MODELS: Union[List[str], str] = [
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
    ]

    # CORS origins
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    @property
    def gemini_fallback_models(self) -> List[str]:
        """The fallback chain as a list, however it was configured."""
        configured = self.GEMINI_FALLBACK_MODELS
        if isinstance(configured, str):
            return [m.strip() for m in configured.split(",") if m.strip()]
        return list(configured)

    @field_validator("GEMINI_FALLBACK_MODELS", mode="before")
    @classmethod
    def assemble_gemini_fallback_models(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(v, str) and not v.startswith("["):
            return [m.strip() for m in v.split(",") if m.strip()]
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
