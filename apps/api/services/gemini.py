import contextvars
import logging

import httpx

from config import settings

logger = logging.getLogger("aion.gemini")

# Per-request flag: whether a live Gemini call succeeded during the current
# async task.  Using contextvars eliminates the race condition that existed
# when this was a shared instance attribute — two concurrent requests no
# longer interfere with each other's development_mode determination.
live_response_generated: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "live_response_generated", default=False,
)


class GeminiService:
    """Single gateway for Gemini calls; agents remain provider-independent."""

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        # gemini-2.5-flash returns 404 "no longer available to new users" for
        # keys issued since its deprecation; Google's error directs new keys to
        # gemini-3.6-flash.
        self.model = "gemini-3.6-flash"

    def is_configured(self) -> bool:
        return bool(self.api_key) and settings.model_calls_enabled

    async def generate(self, role_instruction: str, prompt: str) -> str | None:
        if not self.is_configured():
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": role_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params={"key": self.api_key}, json=payload)
                response.raise_for_status()
            data = response.json()
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            live_response_generated.set(True)
            return result
        except httpx.HTTPError as exc:
            logger.warning("gemini_http_error model=%s status=%s detail=%s", self.model, getattr(exc, "response", None) and exc.response.status_code, exc)
            return None
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("gemini_parse_error model=%s detail=%s", self.model, exc)
            return None
