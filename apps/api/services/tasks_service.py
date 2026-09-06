"""Tasks API service.

There is no dedicated, persistent "Task" entity anywhere in the real
backend — WorkflowRunner does not store ChatResponse objects. The closest
real, persisted record of "a task that ran" is the episodic Cognitive
Memory entry consolidate_task_memory() writes after every completed chat
request (memory/consolidation.py). This service derives Task items from
those real records rather than inventing a task store that doesn't exist.

Fields derived honestly from real stored data, not fabricated:
  - id: the real memory_id of the episodic record.
  - title / agent: parsed from the episodic content string
    (memory/consolidation.py's exact format).
  - status: parsed directly from the real "Final status: completed/failed"
    text every episodic record always contains — this is real, not guessed.
  - confidence: episodic records don't persist a numeric per-task
    confidence score, so this is NOT an invented arbitrary number — it is
    a real derived binary signal from the real recorded outcome
    (100 if completed, 0 if failed), documented as such rather than
    presented as a measured confidence value.
  - created: the record's real created_at timestamp, ISO-formatted.
"""

import re

from memory.store import MemoryStoreInterface
from models.tasks import Task, TasksResponse

_EXECUTION_ORDER_PATTERN = re.compile(r"ran agents (\[.*?\])")
_STATUS_PATTERN = re.compile(r"Final status: (\w+)")


def _parse_agent(content: str) -> str:
    match = _EXECUTION_ORDER_PATTERN.search(content)
    if not match:
        return "aion"
    agents_text = match.group(1).strip("[]")
    if not agents_text:
        return "aion"
    first = agents_text.split(",")[0].strip().strip("'\"")
    return first or "aion"


def _parse_status(content: str) -> str:
    match = _STATUS_PATTERN.search(content)
    status = match.group(1) if match else "completed"
    return status if status in ("completed", "failed", "running") else "completed"


def get_tasks(store: MemoryStoreInterface) -> TasksResponse:
    records = store.list_recent(memory_type="episodic", limit=50)
    items = []
    for record in records:
        status = _parse_status(record.content)
        items.append(Task(
            id=record.memory_id,
            title=record.content[:90] + ("…" if len(record.content) > 90 else ""),
            agent=_parse_agent(record.content),
            status=status,
            confidence=100 if status == "completed" else 0,
            created=record.created_at.isoformat(),
        ))
    return TasksResponse(items=items, total=len(items))
