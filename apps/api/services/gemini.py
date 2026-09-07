import httpx

from config import settings


class GeminiService:
    """Single gateway for Gemini calls; agents remain provider-independent."""

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        # gemini-2.5-flash returns 404 "no longer available to new users" for
        # keys issued since its deprecation; Google's error directs new keys to
        # gemini-3.6-flash.
        self.model = "gemini-3.6-flash"
        self.generated_live_response = False

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
            self.generated_live_response = True
            return result
        except (httpx.HTTPError, KeyError, IndexError, TypeError):
            return None
