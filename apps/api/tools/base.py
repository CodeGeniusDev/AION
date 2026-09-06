"""Tool execution interface.

Mirrors agents/base.py's shape deliberately: a tool is behavior
(`execute()`), its declarative identity lives separately in
models/tool.py + the registration call in tools/builtin.py, exactly the
same separation Cognitive DNA established for agents (identity is data,
execution is code, and the two are never conflated).
"""

from abc import ABC, abstractmethod
from typing import Any

from models.tool import ToolOutput


class BaseTool(ABC):
    id: str
    name: str

    @abstractmethod
    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput: ...
