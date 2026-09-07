import asyncio
import contextvars
import logging
from typing import Any

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

# Maximum function-calling round trips before forcing a text response.
_MAX_TOOL_ROUNDS = 3
_HTTP_TIMEOUT = 30.0

# Retry configuration: transient errors (429, 503, 500) are retried up to
# _MAX_RETRIES times with exponential backoff. 429 (rate limit) gets a
# longer base delay since Gemini's rate-limit window is typically 60s.
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5  # seconds (doubles each attempt: 0.5, 1, 2)
_429_BASE_DELAY = 2.0  # seconds for rate-limit (doubles: 2, 4, 8)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


class FunctionCall:
    """Parsed function call from a Gemini response."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args


async def _post_with_retry(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST to Gemini API with retry for transient errors.

    Returns the parsed JSON response, or None if all retries failed.
    429 (rate limit) uses a longer base delay to respect the rate window.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(url, params={"key": api_key}, json=payload)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                    # 429 gets longer delays; also honour Retry-After if present
                    if response.status_code == 429:
                        retry_after = response.headers.get("retry-after")
                        if retry_after and retry_after.isdigit():
                            delay = float(retry_after)
                        else:
                            delay = _429_BASE_DELAY * (2 ** attempt)
                    else:
                        delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.info("gemini_retry attempt=%d status=%d delay=%.1fs", attempt, response.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            status = getattr(exc, "response", None) and exc.response.status_code
            if attempt < _MAX_RETRIES:
                if status == 429:
                    delay = _429_BASE_DELAY * (2 ** attempt)
                else:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("gemini_retry attempt=%d error=%s delay=%.1fs", attempt, exc, delay)
                await asyncio.sleep(delay)
                continue
            logger.warning("gemini_http_error model_status=%s detail=%s", status, exc)
            return None
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("gemini_parse_error detail=%s", exc)
            return None
    return None


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
        data = await _post_with_retry(url, self.api_key, payload)
        if data is None:
            return None
        try:
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            live_response_generated.set(True)
            return result
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("gemini_parse_error model=%s detail=%s", self.model, exc)
            return None

    async def generate_with_tools(
        self,
        role_instruction: str,
        prompt: str,
        tool_declarations: list[dict[str, Any]],
        execute_fn: Any,
    ) -> str | None:
        """Generate text with Gemini function calling.

        Sends the request with function declarations. If Gemini responds with
        function calls, executes them via execute_fn(name, args) and feeds
        results back for up to _MAX_TOOL_ROUNDS. Returns final text or None.

        Args:
            role_instruction: System prompt.
            prompt: User message.
            tool_declarations: Gemini-format function declarations.
            execute_fn: async callable(name: str, args: dict) -> str result text.
        """
        if not self.is_configured() or not tool_declarations:
            return await self.generate(role_instruction, prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        contents: list[dict[str, Any]] = [
            {"role": "user", "parts": [{"text": prompt}]},
        ]

        for round_idx in range(_MAX_TOOL_ROUNDS + 1):
            payload: dict[str, Any] = {
                "system_instruction": {"parts": [{"text": role_instruction}]},
                "contents": contents,
                "tools": [{"function_declarations": tool_declarations}],
            }

            data = await _post_with_retry(url, self.api_key, payload)
            if data is None:
                return None

            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])

            # Check for text response (no function calls)
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            function_calls = [p.get("functionCall") for p in parts if "functionCall" in p]

            if text_parts and not function_calls:
                live_response_generated.set(True)
                return "\n".join(text_parts).strip()

            if not function_calls:
                # Neither text nor function calls — unexpected response shape
                logger.warning("gemini_tools_empty_response round=%d", round_idx)
                return None

            # Process function calls
            model_response_parts = []
            function_response_parts = []

            for fc in function_calls:
                if fc is None:
                    continue
                name = fc.get("name", "")
                args = fc.get("args", {})
                model_response_parts.append({"functionCall": {"name": name, "args": args}})

                try:
                    result_text = await execute_fn(name, args)
                except Exception as exc:
                    result_text = f"Tool '{name}' failed: {exc}"

                function_response_parts.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": result_text},
                    }
                })

            # Append model's function call response and our function results
            contents.append({"role": "model", "parts": model_response_parts})
            contents.append({"role": "user", "parts": function_response_parts})

        # Final attempt without tools to force a text response
        final_payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": role_instruction}]},
            "contents": contents,
        }
        data = await _post_with_retry(url, self.api_key, final_payload)
        if data is None:
            return None
        try:
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            live_response_generated.set(True)
            return result
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("gemini_tools_final_error detail=%s", exc)
            return None
