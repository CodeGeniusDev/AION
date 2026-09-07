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


class FunctionCall:
    """Parsed function call from a Gemini response."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args


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
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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

            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    response = await client.post(url, params={"key": self.api_key}, json=payload)
                    response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.warning("gemini_tools_http_error round=%d status=%s", round_idx, getattr(exc, "response", None) and exc.response.status_code)
                return None
            except (KeyError, IndexError, TypeError) as exc:
                logger.warning("gemini_tools_parse_error round=%d detail=%s", round_idx, exc)
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
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(url, params={"key": self.api_key}, json=final_payload)
                response.raise_for_status()
            data = response.json()
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            live_response_generated.set(True)
            return result
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            logger.warning("gemini_tools_final_error detail=%s", exc)
            return None
