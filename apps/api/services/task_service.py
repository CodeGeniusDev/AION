"""Task API service.

Provides a real, persistent task registry (SQLite-backed via
:class:`memory.task_store.SQLiteTaskStore`) alongside AION's Cognitive
Memory. Every tool call, browser action, scheduled post, or desktop
operation gets its own task record with a status:

    pending → running → completed / failed

Tasks are the unit of work the dashboard's "Desktop" tab and the scheduler
consume. They are durable (survive process restarts when backed by a real
SQLite file, as the Docker Compose deployment does).

Unlike the legacy ``services/tasks_service.py`` (which derived Task items
from episodic Cognitive Memory records because no task entity existed),
this service uses the real task store — no derivation tricks.
"""

import re

from memory.task_store import TaskStoreInterface, get_default_task_store
from models.tasks import Task, TasksResponse


class TaskService:
    """Mediates task CRUD between API routes and the task store."""

    def __init__(self, store: TaskStoreInterface | None = None) -> None:
        self.store = store or get_default_task_store()

    def create(
        self,
        title: str,
        *,
        agent: str = "aion",
        status: str = "pending",
        confidence: int = 0,
        task_id: str | None = None,
    ) -> Task:
        """Create a new task and return the stored record."""
        if task_id is None:
            from uuid import uuid4
            task_id = f"task-{uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            title=title,
            agent=agent,
            status=status,
            confidence=confidence,
            created=self._now_iso(),
        )
        return self.store.create(task)

    def get(self, task_id: str) -> Task | None:
        return self.store.get(task_id)

    def list_all(self, status: str | None = None) -> list[Task]:
        return self.store.list_all(status)

    def update_status(self, task_id: str, status: str) -> Task | None:
        """Update task status. Special handling for pending_approval -> approved transition."""
        if status == "approved":
            # Auto-transition to running when approved
            return self.store.update_status(task_id, "running")
        return self.store.update_status(task_id, status)

    def update_output(self, task_id: str, output) -> Task | None:
        return self.store.update_output(task_id, output)

    def delete(self, task_id: str) -> bool:
        return self.store.delete(task_id)

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def get_tasks(cls, store: TaskStoreInterface, memory_store=None) -> TasksResponse:
        """List all tasks, returning a real task list from the task store.

        Backward compatibility: if the task store is empty, fall back to
        deriving tasks from episodic Cognitive Memory records (via the old
        tasks_service). This ensures existing tests and frontend continue
        working while the dedicated task store is being populated.

        Args:
            store: The task store (SQLite-backed via memory.task_store)
            memory_store: Optional cognitive memory store for fallback
        """
        service = cls(store)
        tasks = service.list_all()

        # Fall back to episodic memory if task store is empty (backward compat)
        if not tasks and memory_store is not None:
            try:
                from services.tasks_service import get_tasks as get_episodic_tasks
                return get_episodic_tasks(memory_store)
            except Exception:
                pass

        items = []
        for task in tasks:
            items.append(Task(
                id=task.id,
                title=task.title,
                agent=task.agent,
                status=task.status,
                confidence=task.confidence,
                created=task.created,
                output=task.output,
                updated=task.updated,
            ))
        return TasksResponse(items=items, total=len(items))


# Singleton for convenience
_default_service = TaskService()


def get_tasks(store: TaskStoreInterface, memory_store=None) -> TasksResponse:
    return _default_service.get_tasks(store, memory_store)


def get_task(task_id: str, memory_store=None) -> Task | None:
    """Get a task by ID, with backward compatibility fallback to episodic memory.

    Args:
        task_id: The task ID to look up
        memory_store: Optional cognitive memory store for fallback
    """
    found = _default_service.get(task_id)
    if found is not None:
        return found

    # Fall back to episodic memory if not found in task store
    if memory_store is not None:
        try:
            from services.tasks_service import get_tasks as get_episodic_tasks
            response = get_episodic_tasks(memory_store)
            for task in response.items:
                if task.id == task_id:
                    return task
        except Exception:
            pass

    return None


def create_task(title: str, **kwargs) -> Task:
    return _default_service.create(title, **kwargs)


def update_task_status(task_id: str, status: str) -> Task | None:
    return _default_service.update_status(task_id, status)


def update_task_output(task_id: str, output) -> Task | None:
    return _default_service.update_output(task_id, output)
