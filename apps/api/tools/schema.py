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
