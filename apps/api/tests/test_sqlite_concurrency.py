"""SQLite concurrency/thread-safety tests for memory/store.py.

Context: a shared `sqlite3.Connection` (required for `:memory:` mode — see
SQLiteMemoryStore's docstring) accessed via `asyncio.to_thread()` from
concurrent requests can genuinely dispatch to different thread-pool
threads touching the same connection simultaneously.
`check_same_thread=False` only disables Python's same-thread safety CHECK;
per the sqlite3 documentation it does not make concurrent multi-thread use
of one Connection object actually safe. `SQLiteMemoryStore._lock`
(threading.Lock) serializes the actual SQL execution to close this gap.

These tests exercise real, high-concurrency `asyncio.gather()` execution —
not mocks — against the real WorkflowRunner/SQLiteMemoryStore, to give
genuine confidence rather than an assumption.
"""

import asyncio
import threading

import pytest

from memory.store import SQLiteMemoryStore
from models.chat import ChatRequest
from models.cognitive_memory import MemoryRecord
from orchestration.workflow_runner import WorkflowRunner


def test_store_has_a_lock_serializing_connection_access() -> None:
    store = SQLiteMemoryStore(":memory:")
    assert isinstance(store._lock, type(threading.Lock()))


def test_concurrent_writes_from_multiple_real_threads_never_raise() -> None:
    """Directly exercises the hazard: many real OS threads (not asyncio
    tasks on one thread) writing to the same shared connection at once."""
    store = SQLiteMemoryStore(":memory:")
    errors: list[Exception] = []

    def _write(i: int) -> None:
        try:
            store.write(MemoryRecord(
                type="semantic", content=f"Concurrent write number {i} about a shared topic.",
                task_id=f"task-{i}", source_agent="x", verification_state="verified",
                tags=[], provenance="x",
            ))
        except Exception as exc:  # noqa: BLE001 — we want to see and report any failure, not swallow it
            errors.append(exc)

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.count() == 50


def test_concurrent_reads_and_writes_from_multiple_threads_never_raise() -> None:
    store = SQLiteMemoryStore(":memory:")
    store.write(MemoryRecord(
        type="semantic", content="A baseline shared fact about the launch budget.",
        task_id="seed", source_agent="x", verification_state="verified", tags=[], provenance="x",
    ))
    errors: list[Exception] = []

    def _mixed_operation(i: int) -> None:
        try:
            if i % 2 == 0:
                store.write(MemoryRecord(
                    type="semantic", content=f"Additional shared fact number {i}.",
                    task_id=f"task-{i}", source_agent="x", verification_state="verified", tags=[], provenance="x",
                ))
            else:
                store.search(query="launch budget shared fact", limit=5)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_mixed_operation, args=(i,)) for i in range(60)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []


def test_heavy_concurrent_chat_requests_never_raise_sqlite_errors() -> None:
    """Real end-to-end stress: many concurrent chat requests on one shared
    WorkflowRunner, each doing real memory retrieval + consolidation
    through asyncio.to_thread(). This is the exact scenario the reported
    'sqlite3.InterfaceError: bad parameter or other API misuse' concerns.
    """
    runner = WorkflowRunner()

    async def _run_many():
        requests = [ChatRequest(message=f"Research and compare option {i}") for i in range(40)]
        return await asyncio.gather(*(runner.run(request) for request in requests), return_exceptions=True)

    results = asyncio.run(_run_many())
    errors = [result for result in results if isinstance(result, Exception)]
    assert errors == [], f"Unexpected errors under concurrency: {errors}"
    assert all(result.status == "completed" for result in results)


def test_concurrent_requests_produce_correct_isolated_data_not_just_no_crash() -> None:
    """A correctness check beyond "didn't raise": every concurrent
    request's data must be genuinely intact and correctly attributed,
    confirming the lock didn't just suppress errors while corrupting data."""
    runner = WorkflowRunner()

    async def _run_many():
        requests = [ChatRequest(message=f"Create a roadmap and steps for project {i}") for i in range(30)]
        return await asyncio.gather(*(runner.run(request) for request in requests))

    responses = asyncio.run(_run_many())
    task_ids = [response.task_id for response in responses]
    assert len(set(task_ids)) == len(task_ids)  # every task_id genuinely unique, none dropped/duplicated

    for response in responses:
        records = runner.memory_store.list_for_task(response.task_id)
        assert len(records) >= 1
        assert all(record.task_id == response.task_id for record in records)
