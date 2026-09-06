"""KnowledgeProviderTool: a specialized Tool for retrieving evidence with
source provenance.

Built directly on the existing Tool System (BaseTool) rather than a
parallel mechanism — a knowledge provider IS a tool. ToolExecutor's timeout
enforcement and exception isolation (tools/executor.py) apply to knowledge
providers for free, with zero additional code.
"""

from abc import abstractmethod
from typing import Any

from models.knowledge import EvidenceSource
from models.tool import ToolOutput
from tools.base import BaseTool


class KnowledgeProviderTool(BaseTool):
    @abstractmethod
    async def search(self, query: str) -> list[EvidenceSource]:
        """Return real evidence sources for `query`. Must never fabricate
        results — an empty list is a valid, honest answer, not a failure."""

    async def execute(self, task_id: str, parameters: dict[str, Any]) -> ToolOutput:
        query = str(parameters.get("query", "")).strip()
        if not query:
            return ToolOutput(tool_id=self.id, task_id=task_id, success=False, error="No 'query' parameter provided.")

        sources = await self.search(query)
        return ToolOutput(
            tool_id=self.id, task_id=task_id, success=True,
            content=f"{len(sources)} source(s) found." if sources else "No sources found.",
            data={"sources": [source.model_dump(mode="json") for source in sources]},
        )
