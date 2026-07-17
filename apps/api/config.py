"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "AION API"
    app_version: str = "0.1.0"
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    model_calls_enabled: bool = os.getenv("AION_DISABLE_MODEL_CALLS", "0") != "1"


settings = Settings()
