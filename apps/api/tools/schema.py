"""Converts ToolIdentity objects to Gemini function calling declarations.

Gemini expects this format:
{
    "name": "calculator",
    "description": "Evaluates arithmetic...",
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "The arithmetic expression"}
        },
        "required": ["expression"]
    }
}

Each tool's ToolIdentity already has name, description, and capabilities.
We infer parameter schemas from the tool's documented usage.
"""

import re
from typing import Any

from models.tool import ToolIdentity

# Parameter schemas for each built-in tool. This is the mapping that
# makes function calling work — Gemini needs to know what parameters
# each function accepts so it can generate correct calls.
_TOOL_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "calculator": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A numeric arithmetic expression to evaluate, e.g. '2 + 3 * 4'.",
            }
        },
        "required": ["expression"],
    },
    "text_analysis": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to analyze for word count, character count, and sentence count.",
            }
        },
        "required": ["text"],
    },
    "current_datetime": {
        "type": "object",
        "properties": {},
    },
}


def tool_identity_to_declaration(identity: ToolIdentity) -> dict[str, Any]:
    """Convert a ToolIdentity to a Gemini function declaration dict."""
    declaration: dict[str, Any] = {
        "name": identity.id,
        "description": identity.description,
    }
    params = _TOOL_PARAMETER_SCHEMAS.get(identity.id)
    if params:
        declaration["parameters"] = params
    return declaration


def tools_to_declarations(identities: list[ToolIdentity]) -> list[dict[str, Any]]:
    """Convert a list of ToolIdentity objects to Gemini function declarations."""
    return [tool_identity_to_declaration(identity) for identity in identities]


# ---------------------------------------------------------------------------
# Lightweight heuristic: does this message look like it needs a tool?
# Avoids an expensive Gemini function-calling round-trip for messages that
# clearly don't need computation, text analysis, or time lookup.
# ---------------------------------------------------------------------------

# Arithmetic: digits with operators, or explicit calculation requests
_MATH_PATTERN = re.compile(
    r"(\d+\s*[+\-*/^%]\s*\d+|"          # 2 + 3, 100 * 5
    r"\b(calculate|compute|evaluate|solve|math)\b|"
    r"\b(how much is|what is|what's)\s+\d)",
    re.IGNORECASE,
)

# Time/date questions
_TIME_PATTERN = re.compile(
    r"\b(what time|current time|what'?s the time|today'?s date|"
    r"what day|current date|what date|now in utc|"
    r"kitne baje|kya time|abhi time|current utc)\b",
    re.IGNORECASE,
)

# Text analysis requests
_TEXT_ANALYSIS_PATTERN = re.compile(
    r"\b(count|how many)\s*(the\s*)?(words|characters|sentences|letters)\b|"
    r"\b(word count|character count|text analysis|analyze this text)\b",
    re.IGNORECASE,
)


def message_needs_tools(message: str) -> bool:
    """Return True if the message heuristically matches a tool-capable intent.

    This is a fast, zero-cost filter: a regex check that avoids making an
    extra Gemini API call (with function declarations) for the vast majority
    of messages that don't need computation, text analysis, or time lookup.

    False positives (message matches heuristic but Gemini wouldn't call a
    tool) are harmless — Gemini simply returns a text response. False
    negatives (message needs a tool but heuristic misses it) are also
    acceptable — the agent pipeline still handles the request, just without
    pre-computed tool results.
    """
    return bool(
        _MATH_PATTERN.search(message)
        or _TIME_PATTERN.search(message)
        or _TEXT_ANALYSIS_PATTERN.search(message)
    )
