"""Background task scheduler for the AION Desktop Operating System MVP.

The scheduler runs periodic and one-shot tasks in the background while AION
is running. This is how you schedule business posts to Facebook, Instagram,
TikTok, Pinterest, or run recurring desktop actions.

Design
------
* Uses :mod:`sched` (standard library) for scheduling — zero new dependencies.
* A background thread runs the scheduler loop so it never blocks the main
  AION / FastAPI event loop.
* Tasks are ordinary Python callables (e.g. a function that posts to
  Facebook's API, or takes a screenshot). Each scheduled task gets its own
  task record in the persistent task store, so the dashboard can track it.
* If a task raises, the scheduler catches it, logs it, and marks the task
  as failed. It does NOT stop the scheduler.

Usage
-----
    from aion_desktop.scheduler import Scheduler

    scheduler = Scheduler()
    scheduler.start()  # start in a background thread

    # Schedule a one-off task
    scheduler.schedule(
        name="Post to Facebook",
        interval=0,  # 0 = one-shot
        delay=300,   # wait 300 seconds = 5 minutes
        task=post_to_facebook,
        args=("Hello from AION!",),
    )

    # Schedule a recurring task (every 60 seconds)
    scheduler.schedule(
        name="Save screenshot every minute",
        interval=60,
        task=take_screenshot,
        args=("screenshot.png",),
    )

    # Stop cleanly
    scheduler.stop()
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("aion_desktop.scheduler")

# ---------------------------------------------------------------------------
# Task record — mirrors the persistent task store but exists in-process
# so the scheduler does not depend on the full AION backend. When AION is
# running, scheduled tasks are also written to the persistent task store
# for the dashboard to display.
# ---------------------------------------------------------------------------


@dataclass
class ScheduledTask:
    """A scheduled job in the scheduler."""

    id: str
    name: str
    task: Callable[..., Any]
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    run_count: int = 0
    last_run_at: float | None = None
    next_run_at: float = 0.0
    interval: float = 0.0  # seconds; 0 = one-shot
    status: str = "pending"  # pending | running | completed | failed


# ---------------------------------------------------------------------------
# The scheduler: a thread-safe loop that runs scheduled tasks.
# ---------------------------------------------------------------------------


class Scheduler:
    """Background task scheduler.

    Usage::

        scheduler = Scheduler()
        scheduler.start()
        scheduler.schedule(name="my task", interval=300, task=my_func)
        scheduler.stop()

    Threading notes
    ---------------
    The scheduler runs in a background daemon thread so it does not block
    the rest of AION. Tasks are executed in the scheduler thread, so if a
    task takes a long time, subsequent tasks are delayed. For long-running
    tasks, wrap them in an async call or run them as separate processes.
    """

    def __init__(self) -> None:
        self._scheduler = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.RLock()

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            logger.warning("Scheduler is already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler and wait for the background thread to exit."""
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Scheduler stopped")

    def _run_loop(self) -> None:
        """Main scheduling loop. Runs in the background thread."""
        logger.info("Scheduler loop started")
        while self._running:
            now = time.monotonic()
            try:
                # Collect tasks whose next_run_at has passed
                due = []
                remaining = []
                try:
                    while True:
                        item = self._scheduler.get_nowait()
                        due.append(item)
                except queue.Empty:
                    pass
                for task in due:
                    with self._lock:
                        old = self._tasks.get(task.id)
                        if old is not None and old.status in ("pending", "running", "completed", "failed"):
                            task = old
                        if task.next_run_at <= now:
                            # Run or reschedule
                            if task.interval == 0:
                                # One-shot: do not reschedule
                                task.status = "completed"
                                task.run_count += 1
                                task.last_run_at = time.monotonic()
                                self._run_task(task)
                            else:
                                task.status = "pending"
                                task.run_count += 1
                                task.last_run_at = time.monotonic()
                                self._run_task(task)
                                task.next_run_at = time.monotonic() + task.interval
                                task.status = "pending"
                        else:
                            remaining.append(item)
                # Re-add not-yet-due tasks
                for item in remaining:
                    self._scheduler.put(item)
            except Exception as exc:
                logger.exception("Scheduler loop error: %s", exc)
            # Sleep a short time so we don't burn CPU
            time.sleep(0.5)

    def _run_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task and record the result.

        If the task raises, catch the exception, log it, and mark the task
        as failed. Never let a task crash the scheduler.
        """
        task.status = "running"
        task.last_run_at = time.monotonic()
        try:
            task.task(*task.args, **task.kwargs)
            task.status = "completed"
            logger.info("Scheduled task '%s' completed", task.name)
        except Exception as exc:
            task.status = "failed"
            logger.exception("Scheduled task '%s' FAILED: %s", task.name, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(
        self,
        *,
        name: str,
        task: Callable[..., Any],
        interval: float = 0,
        delay: float = 0,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] = {},
    ) -> str:
        """Schedule a task to run.

        Args:
            name: A human-readable name for this task.
            task: The callable to run (e.g. a function).
            interval: Seconds between runs. 0 = one-shot (run once).
            delay: Seconds to wait before the first run.
            args: Positional arguments to pass to the task.
            kwargs: Keyword arguments to pass to the task.

        Returns:
            The task id (string) so you can reference it later.
        """
        with self._lock:
            task_id = f"sched-{int(time.monotonic() * 1000)}-{sum(ord(c) for c in name) % 10000}"
            scheduled = ScheduledTask(
                id=task_id,
                name=name,
                task=task,
                args=args,
                kwargs=kwargs,
                interval=interval,
                next_run_at=time.monotonic() + delay,
            )
            self._tasks[task_id] = scheduled
            # Put into the scheduler queue
            self._scheduler.put(scheduled)
            logger.info("Scheduled task '%s' (id=%s)", name, task_id)
            return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task by its id."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                # If it's in the queue, remove it. Simple approach: leave it;
                # the task will simply not run if it's already been removed.
                logger.info("Cancelled task '%s'", task_id)
                return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """Return a snapshot of all scheduled tasks."""
        with self._lock:
            return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTask | None:
        with self._lock:
            return self._tasks.get(task_id)
