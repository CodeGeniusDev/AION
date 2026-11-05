"""Schedule runner: turns due schedules into PENDING approvals — nothing more.

The runner is deliberately the *least powerful* actor in the system. At
fire time it calls ``ApprovalService.request_execution`` — the exact
create-only path chat uses (Phase 2) — which writes a task, a pending
ledger row, an alert and an audit entry, and provably never touches the
bridge. It holds no secret, builds no grant, and calls no dispatch:
a scheduled action executes only if a human approves the approval it
produces.

The clock is injectable (``now_fn``) so tests drive every branch with a
fake clock and no sleeps; production runs a daemon thread ticking every
second, started only when ``AION_SCHEDULER_ENABLED=1``.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from config import settings
from memory.schedule_store import ScheduleRecord, ScheduleStoreInterface, get_default_schedule_store
from services.approval_service import ApprovalError, ApprovalService, get_approval_service

logger = logging.getLogger("aion.schedules")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class ScheduleRunner:
    """Ticks the schedule store's clock. ``tick`` is pure and clock-
    injected; ``start`` merely repeats it on a daemon thread."""

    def __init__(
        self,
        store: ScheduleStoreInterface | None = None,
        approval_service: ApprovalService | None = None,
        *,
        now_fn: Callable[[], datetime] | None = None,
        tick_seconds: float = 1.0,
    ) -> None:
        self.store = store or get_default_schedule_store()
        self.approvals = approval_service or get_approval_service()
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.tick_seconds = tick_seconds
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Fire-time logic (the only public behavior that matters)
    # ------------------------------------------------------------------

    def tick(self) -> list[ScheduleRecord]:
        """Fire every due active schedule once. Returns the fired (or
        skipped-with-backpressure) records for observability/tests.

        Never raises: a failing fire pauses its schedule with the error
        recorded, so one bad schedule can neither crash the thread nor
        loop forever creating doomed approvals."""
        now = self.now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        fired: list[ScheduleRecord] = []
        for schedule in self.store.get_due(_iso(now)):
            if self._previous_still_pending(schedule):
                logger.info(
                    "schedule %s skipped: approval %s still awaiting a human",
                    schedule.id, schedule.last_approval_id,
                )
                continue
            try:
                record = self.approvals.request_execution(
                    tool=schedule.tool,
                    parameters=dict(schedule.parameters),
                    tenant_id=schedule.tenant_id,
                    actor_key_id="scheduler",
                    title=f"Scheduled: {schedule.name}",
                )
            except ApprovalError as exc:
                # Unknown/invalid tool at fire time: pause, don't spin.
                self.store.set_status(schedule.id, "paused", error=exc.detail)
                logger.warning("schedule %s paused at fire time: %s", schedule.id, exc.detail)
                fired.append(schedule)
                continue
            except Exception as exc:
                self.store.set_status(
                    schedule.id, "paused", error=f"{type(exc).__name__}: {exc}",
                )
                logger.exception("schedule %s fire failed", schedule.id)
                fired.append(schedule)
                continue

            if schedule.interval_seconds > 0:
                next_run = _iso(now + timedelta(seconds=schedule.interval_seconds))
                status = "active"
            else:
                next_run = None
                status = "completed"
            updated = self.store.record_fire(
                schedule.id, approval_id=record.id,
                next_run_at=next_run, status=status,
            )
            logger.info(
                "schedule %s fired -> pending approval %s (status %s)",
                schedule.id, record.id, status,
            )
            # Phase 2B: notify SSE subscribers of schedule fire.
            try:
                from realtime.publishers import publish_schedule_fired
                publish_schedule_fired(schedule.tenant_id, schedule_id=schedule.id, approval_id=record.id)
            except Exception:
                pass
            fired.append(updated or schedule)
        return fired

    def _previous_still_pending(self, schedule: ScheduleRecord) -> bool:
        """Backpressure: one outstanding human decision per schedule.
        A recurring schedule does not pile up approvals while its last
        fire is still awaiting (or running) — the human catches up, then
        the next tick fires again."""
        if not schedule.last_approval_id:
            return False
        prior = self.approvals.store.get(schedule.last_approval_id)
        return prior is not None and prior.status in ("pending_approval", "running")

    # ------------------------------------------------------------------
    # Thread lifecycle (opt-in; tests never start it)
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="aion-scheduler")
        self._thread.start()
        logger.info("Schedule runner started (tick=%.1fs)", self.tick_seconds)

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _loop(self) -> None:
        while self._running:
            try:
                self.tick()
            except Exception:
                logger.exception("scheduler tick failed")
            # Event.wait gives an interruptible sleep: stop() is prompt.
            self._stop_event.wait(self.tick_seconds)


_default_runner: ScheduleRunner | None = None


def get_default_runner() -> ScheduleRunner:
    global _default_runner
    if _default_runner is None:
        _default_runner = ScheduleRunner()
    return _default_runner


def start_scheduler_if_enabled() -> None:
    """Called from app startup. No-op unless AION_SCHEDULER_ENABLED=1 —
    so the default deployment behavior (and every existing test) is
    exactly unchanged."""
    if settings.scheduler_enabled:
        get_default_runner().start()
