import asyncio
import contextvars
import hashlib
import logging
import time
from collections import OrderedDict
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

# Retry configuration: for 429 (rate limit), only 1 retry with a short
# delay — free-tier keys have a tiny daily quota (20 req/day), so burning
# 3 retries per failed call wastes 60% of the daily budget on doomed
# requests.  For server errors (500/502/503), keep 2 retries since those
# are usually transient and don't consume quota.
_MAX_RETRIES_429 = 1
_MAX_RETRIES_SERVER = 2
_429_BASE_DELAY = 2.0  # seconds for rate-limit
_RETRY_BASE_DELAY = 0.5  # seconds (doubles each attempt: 0.5, 1)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

# ── Circuit breaker ────────────────────────────────────────────────
# When a Gemini call returns 429 (rate/quota exhausted), every subsequent
# call for the next _CIRCUIT_COOLDOWN seconds returns None immediately
# without hitting the API. This prevents burning the remaining daily
# quota on requests that will also fail.
_circuit_open_until: float = 0.0
_CIRCUIT_COOLDOWN = 60.0  # seconds after a 429 before trying again

# ── Response cache ─────────────────────────────────────────────────
# Simple LRU cache keyed on (role_instruction_hash, prompt). Identical
# questions get instant cached answers — 0 API calls. Sized small to
# avoid stale data; 100 entries covers repeated demo usage patterns.
_MAX_CACHE_SIZE = 100
_response_cache: OrderedDict[str, str] = OrderedDict()


def is_circuit_open() -> bool:
    """Return True if the circuit breaker is open (skip API calls)."""
    return time.monotonic() < _circuit_open_until


def _trip_circuit() -> None:
    """Open the circuit breaker for _CIRCUIT_COOLDOWN seconds."""
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN
    logger.warning("circuit_breaker_opened cooldown=%.0fs reason=429_rate_limit", _CIRCUIT_COOLDOWN)


def _cache_key(role_instruction: str, prompt: str) -> str:
    """Short deterministic key for the response cache."""
    h = hashlib.sha256(f"{role_instruction}\n{prompt}".encode()).hexdigest()
    return h[:32]


def _cache_get(key: str) -> str | None:
    value = _response_cache.get(key)
    if value is not None:
        _response_cache.move_to_end(key)  # mark as recently used
    return value


def _cache_put(key: str, value: str) -> None:
    _response_cache[key] = value
    _response_cache.move_to_end(key)
    while len(_response_cache) > _MAX_CACHE_SIZE:
        _response_cache.popitem(last=False)  # evict oldest


class FunctionCall:
    """Parsed function call from a Gemini response."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args


async def _post_with_retry(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST to Gemini API with retry for transient errors.

    Returns the parsed JSON response, or None if all retries failed.
    429 (rate limit) trips the circuit breaker — no more calls for 60s.
    429 gets only 1 retry (free-tier quota is too small to waste on retries).
    Server errors (500/502/503) get 2 retries with exponential backoff.
    """
    if is_circuit_open():
        logger.info("gemini_call_skipped reason=circuit_breaker_open")
        return None

    is_429_failure = False
    max_retries = _MAX_RETRIES_SERVER  # default for server errors

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(url, params={"key": api_key}, json=payload)
                if response.status_code == 429:
                    # 429: trip circuit breaker immediately, minimal retry
                    is_429_failure = True
                    if attempt < _MAX_RETRIES_429:
                        retry_after = response.headers.get("retry-after")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else _429_BASE_DELAY
                        logger.info("gemini_429_retry attempt=%d delay=%.1fs", attempt, delay)
                        await asyncio.sleep(delay)
                        continue
                    # Exhausted 429 retries — trip circuit
                    _trip_circuit()
                    logger.warning("gemini_429_circuit_tripped status=429")
                    return None
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.info("gemini_retry attempt=%d status=%d delay=%.1fs", attempt, response.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            status = getattr(exc, "response", None) and exc.response.status_code
            if status == 429 or is_429_failure:
                _trip_circuit()
                logger.warning("gemini_429_circuit_tripped error=%s", exc)
                return None
            if attempt < max_retries:
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
        # Check circuit breaker — skip API call if 429 cooldown is active
        if is_circuit_open():
            logger.info("generate_skipped reason=circuit_breaker_open")
            return None
        # Check response cache — identical question = 0 API calls
        ck = _cache_key(role_instruction, prompt)
        cached = _cache_get(ck)
        if cached is not None:
            logger.info("generate_cache_hit key=%s", ck)
            return cached
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
            _cache_put(ck, result)  # cache the successful response
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
