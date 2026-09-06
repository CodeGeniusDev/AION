"""Built-in deterministic tools.

Per this phase's explicit scope: safe internal tools only, no external
services, to prove the Tool System architecture end-to-end honestly.
Every tool here does genuine, real computation — none returns fabricated
or placeholder data.
"""

import ast
import operator
import re
from datetime import datetime, timezone
from typing import Any

from models.cognitive_dna import CapabilityTag, Domain
from models.tool import ToolIdentity, ToolOutput
from tools.base import BaseTool
from tools.registry import registry

# --- Calculator: a genuinely safe arithmetic evaluator ---------------------
# Uses Python's `ast` module to parse the expression into a syntax tree and
# only evaluates a small, explicit whitelist of numeric operators — this is
# NOT eval()/exec(), and no arbitrary code (function calls, attribute
# access, imports, comprehensions) can execute through it.

_ALLOWED_BINARY_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPS:
        return _ALLOWED_BINARY_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPS:
        return _ALLOWED_UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


class CalculatorTool(BaseTool):
    id = "calculator"
    name = "Calculator"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        expression = str(parameters.get("expression", "")).strip()
        if not expression:
            return ToolOutput(tool_id=self.id, task_id=task_id, success=False, error="No 'expression' parameter provided.")
        try:
            tree = ast.parse(expression, mode="eval")
            result = _safe_eval(tree)
        except Exception as exc:
            return ToolOutput(tool_id=self.id, task_id=task_id, success=False, error=f"Could not evaluate expression: {exc}")
        return ToolOutput(
            tool_id=self.id, task_id=task_id, success=True,
            content=f"{expression} = {result}", data={"result": result},
        )


# --- Text analysis: real, computed statistics -------------------------------

_WORD_PATTERN = re.compile(r"\S+")
_SENTENCE_PATTERN = re.compile(r"[.!?]+")


class TextAnalysisTool(BaseTool):
    id = "text_analysis"
    name = "Text Analysis"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        text = str(parameters.get("text", ""))
        if not text.strip():
            return ToolOutput(tool_id=self.id, task_id=task_id, success=False, error="No 'text' parameter provided.")
        word_count = len(_WORD_PATTERN.findall(text))
        char_count = len(text)
        sentence_count = len([s for s in _SENTENCE_PATTERN.split(text) if s.strip()])
        return ToolOutput(
            tool_id=self.id, task_id=task_id, success=True,
            content=f"{word_count} words, {char_count} characters, {sentence_count} sentence(s).",
            data={"word_count": word_count, "char_count": char_count, "sentence_count": sentence_count},
        )


# --- Current time: the real system clock, not a fabricated value -----------

class DateTimeTool(BaseTool):
    id = "current_datetime"
    name = "Current Date/Time"

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        _ = parameters
        now = datetime.now(timezone.utc)
        return ToolOutput(
            tool_id=self.id, task_id=task_id, success=True,
            content=f"Current UTC time is {now.isoformat()}.",
            data={"iso8601": now.isoformat()},
        )


def _register_builtin_tools() -> None:
    registry.register(
        ToolIdentity(
            id=CalculatorTool.id, name=CalculatorTool.name,
            description="Evaluates a numeric arithmetic expression using a restricted, safe parser (no arbitrary code execution).",
            capabilities=[CapabilityTag(name="arithmetic_evaluation", domain=Domain.COMPUTATION, declared_proficiency=0.95)],
            domains=[Domain.COMPUTATION], timeout_seconds=2.0,
        ),
        CalculatorTool(),
    )
    registry.register(
        ToolIdentity(
            id=TextAnalysisTool.id, name=TextAnalysisTool.name,
            description="Computes real word/character/sentence counts for a piece of text.",
            capabilities=[CapabilityTag(name="text_statistics", domain=Domain.COMPUTATION, declared_proficiency=0.9)],
            domains=[Domain.COMPUTATION], timeout_seconds=2.0,
        ),
        TextAnalysisTool(),
    )
    registry.register(
        ToolIdentity(
            id=DateTimeTool.id, name=DateTimeTool.name,
            description="Returns the current UTC date and time from the system clock.",
            capabilities=[CapabilityTag(name="current_time_lookup", domain=Domain.GENERAL, declared_proficiency=1.0)],
            domains=[Domain.GENERAL], timeout_seconds=1.0, requires_verification=False,
            # A system clock reading isn't a claim that could be
            # contradicted or corroborated by other evidence — it's a
            # direct, unambiguous measurement. Verification is meaningfully
            # inapplicable here, unlike the other two tools' outputs, which
            # do go through the standard verified-only memory gate.
        ),
        DateTimeTool(),
    )


_register_builtin_tools()
