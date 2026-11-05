"""Phase 5 scheduler tests: fire time creates PENDING approvals — never more.

The whole security story of the scheduler fits in one assertion set:
after a fire there is a pending_approval ledger row, and the bridge
client recorded ZERO calls. A fake clock drives every timing branch;
the background thread is never started in tests.
"""

import sqlite3  # noqa: F401  (kept for tmp db-file debugging)
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import services.schedule_runner as runner_module
from main import app
from memory.approval_store import ApprovalStore
from memory.schedule_store import SQLiteScheduleStore, new_schedule
from services import approval_service as approval_service_module
from services.schedule_runner import ScheduleRunner
from tests.test_desktop_approvals import MockBridgeClient  # reuse the mock

client = TestClient(app)

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture()
def ledger(monkeypatch) -> ApprovalStore:
    fresh = ApprovalStore(":memory:")
    monkeypatch.setattr(approval_service_module._default_approval_service, "store", fresh)
    return fresh


@pytest.fixture()
def bridge(monkeypatch) -> MockBridgeClient:
    mock = MockBridgeClient()
    monkeypatch.setattr(
        approval_service_module._default_approval_service, "_bridge_client", mock,
    )
    return mock


@pytest.fixture()
def schedules() -> SQLiteScheduleStore:
    return SQLiteScheduleStore(":memory:")


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def runner(schedules, clock, monkeypatch) -> ScheduleRunner:
    # schedule_runner binds settings at import; swap the whole binding.
    monkeypatch.setattr(
        runner_module, "settings", replace(runner_module.settings, scheduler_enabled=False),
    )
    return ScheduleRunner(
        schedules, approval_service_module._default_approval_service, now_fn=clock,
    )


def _make(tool="file_write", interval=60, params=None, delay=0, now=None):
    return new_schedule(
        name="Nightly export", tool=tool,
        parameters=params if params is not None else {"path": "out.txt", "content": "x"},
        interval_seconds=interval, delay_seconds=delay, now=now,
    )


# ---------------------------------------------------------------------------
# Fire-time semantics
# ---------------------------------------------------------------------------

def test_fire_creates_pending_approval_and_never_touches_bridge(
    schedules, runner, clock, ledger, bridge,
):
    schedules.create(_make(now=clock.now))
    fired = runner.tick()

    assert len(fired) == 1
    rows = ledger.list(tenant_id="default")
    assert len(rows) == 1
    assert rows[0].status == "pending_approval"
    assert rows[0].tool == "file_write"
    # The scheduler's entire existence must not put a call on the bridge.
    assert bridge.register_calls == [] and bridge.execute_calls == []
    # ...and the fire is accounted for on the schedule row.
    record = schedules.get(fired[0].id)
    assert record.fire_count == 1 and record.last_approval_id == rows[0].id
    assert record.status == "active"  # recurring stays armed


def test_one_shot_completes_after_single_fire(schedules, runner, clock, ledger):
    schedules.create(_make(interval=0, now=clock.now))
    fired = runner.tick()
    record = schedules.get(fired[0].id)
    assert record.status == "completed"
    assert record.next_run_at is None
    assert runner.tick() == []  # nothing left to fire
    assert len(ledger.list(tenant_id="default")) == 1


def test_recurring_reschedules_one_interval_ahead(schedules, runner, clock, ledger):
    schedules.create(_make(interval=90, now=clock.now))
    fired = runner.tick()
    record = schedules.get(fired[0].id)
    assert datetime.fromisoformat(record.next_run_at) == clock.now + timedelta(seconds=90)

    # Settle the outstanding human decision, then let the clock arrive.
    ledger.reject(record.last_approval_id, tenant_id="default")
    clock.advance(90)
    again = runner.tick()
    assert len(again) == 1
    assert schedules.get(record.id).fire_count == 2
    assert len(ledger.list(tenant_id="default")) == 2


def test_backpressure_skips_while_previous_approval_pending(schedules, runner, clock, ledger):
    schedules.create(_make(interval=30, now=clock.now))
    first = runner.tick()
    clock.advance(30)
    assert runner.tick() == []          # still awaiting the human: skipped
    clock.advance(30)
    assert runner.tick() == []          # and again, and again...
    assert len(ledger.list(tenant_id="default")) == 1  # never piled up
    assert schedules.get(first[0].id).fire_count == 1


def test_fire_with_unknown_tool_pauses_schedule_no_spin(schedules, runner, clock, ledger):
    record = _make(tool="file_write", now=clock.now)
    schedules.create(record)
    # Tool vanishes from the registry between create and fire.
    import services.approval_service as asm
    original = asm.known_desktop_tools
    asm.known_desktop_tools = lambda: {"file_read"}
    try:
        fired = runner.tick()
    finally:
        asm.known_desktop_tools = original
    assert len(fired) == 1
    after = schedules.get(record.id)
    assert after.status == "paused" and "Unknown desktop tool" in (after.last_error or "")
    assert runner.tick() == []          # paused: no failure loop
    assert ledger.list(tenant_id="default") == []


# ---------------------------------------------------------------------------
# Lifecycle + fake clock
# ---------------------------------------------------------------------------

def test_not_yet_due_does_not_fire(schedules, runner, clock, ledger):
    schedules.create(_make(interval=0, delay=3600, now=clock.now))
    assert runner.tick() == []
    assert ledger.list(tenant_id="default") == []


def test_pause_stops_fires_resume_rearms(schedules, runner, clock, ledger):
    record = schedules.create(_make(interval=60, now=clock.now))
    schedules.set_status(record.id, "paused")
    clock.advance(600)
    assert runner.tick() == []
    schedules.rearm(record.id, next_run_at=(clock.now + timedelta(seconds=60)).isoformat())
    clock.advance(60)
    assert len(runner.tick()) == 1
    assert len(ledger.list(tenant_id="default")) == 1


def test_schedules_survive_store_restart(tmp_path, ledger):
    db = str(tmp_path / "schedules.db")
    first_store = SQLiteScheduleStore(db)
    record = new_schedule(
        name="Persisted", tool="file_write",
        parameters={"path": "p", "content": "c"}, interval_seconds=0, delay_seconds=0,
        now=T0,
    )
    first_store.create(record)

    # "Restart": a brand-new store object over the same file.
    reopened = SQLiteScheduleStore(db)
    rows = reopened.list_all()
    assert len(rows) == 1 and rows[0].id == record.id and rows[0].fire_count == 0

    clock = FakeClock()
    runner = ScheduleRunner(reopened, approval_service_module._default_approval_service, now_fn=clock)
    fired = runner.tick()
    assert len(fired) == 1
    assert reopened.get(record.id).fire_count == 1


def test_tenant_scope_isolates_listing_and_fire_lands_on_owner(
    schedules, runner, clock, ledger,
):
    mine = schedules.create(_make(now=clock.now))
    theirs = schedules.create(
        new_schedule(
            name="Other tenant", tool="file_write",
            parameters={"path": "x", "content": "y"}, interval_seconds=60,
            now=clock.now, tenant_id="tenant-b",
        ),
    )
    assert [r.id for r in schedules.list_all("default")] == [mine.id]
    assert [r.id for r in schedules.list_all("tenant-b")] == [theirs.id]

    fired = runner.tick()  # both due; both fire into their own tenants
    assert len(fired) == 2
    rows = ledger.list(tenant_id="default")
    assert len(rows) == 1 and rows[0].task_id  # only mine visible here
    rows_b = ledger.list(tenant_id="tenant-b")
    assert len(rows_b) == 1 and rows_b[0].status == "pending_approval"


# ---------------------------------------------------------------------------
# Route contract
# ---------------------------------------------------------------------------

def test_create_schedule_route_validates_tool_and_params(monkeypatch):
    fresh = SQLiteScheduleStore(":memory:")
    import routes.schedules as routes_schedules
    monkeypatch.setattr(routes_schedules, "get_default_schedule_store", lambda: fresh)

    ok = client.post("/api/schedules", json={
        "name": "Screenshot", "tool": "desktop_screenshot", "parameters": {},
        "interval_seconds": 3600,
    })
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["status"] == "active" and body["fire_count"] == 0

    bad_tool = client.post("/api/schedules", json={"name": "x", "tool": "rm_rf"})
    assert bad_tool.status_code == 404

    # Raw JSON body: a datetime value survives the wire but is not
    # JSON-serializable server-side — the store must refuse it (422).
    bad_params = client.request(
        "POST", "/api/schedules",
        content=b'{"name": "x", "tool": "file_write", "parameters": {"bad": "2026-11-01T00:00:00"}, "interval_seconds": -5}',
        headers={"Content-Type": "application/json"},
    )
    assert bad_params.status_code == 422  # caught by the interval bound


def test_schedule_routes_lifecycle(monkeypatch):
    fresh = SQLiteScheduleStore(":memory:")
    import routes.schedules as routes_schedules
    monkeypatch.setattr(routes_schedules, "get_default_schedule_store", lambda: fresh)

    created = client.post("/api/schedules", json={
        "name": "Write", "tool": "file_write",
        "parameters": {"path": "a", "content": "b"}, "interval_seconds": 120,
    }).json()
    sid = created["id"]

    assert client.get("/api/schedules").json()["items"][0]["id"] == sid
    assert client.get(f"/api/schedules/{sid}").status_code == 200
    assert client.get("/api/schedules/sched-nope").status_code == 404

    assert client.post(f"/api/schedules/{sid}/pause").json()["status"] == "paused"
    assert client.post(f"/api/schedules/{sid}/pause").json()["status"] == "paused"
    resumed = client.post(f"/api/schedules/{sid}/resume").json()
    assert resumed["status"] == "active"
    # Resume never bursts: next fire is one interval ahead of *now*.
    assert datetime.fromisoformat(resumed["next_run_at"]) > datetime.now(timezone.utc)

    canceled = client.delete(f"/api/schedules/{sid}").json()
    assert canceled["status"] == "canceled"
    # Terminal rows stay readable for history.
    assert client.get(f"/api/schedules/{sid}").json()["status"] == "canceled"
