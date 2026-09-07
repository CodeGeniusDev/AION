from fastapi import APIRouter, Body, HTTPException, Query

from models.cognitive_memory import MemoryRecord
from models.memory import MemoryRecordOut, MemoryRecordsListResponse, MemoryResponse
from routes.chat import workflow_runner  # the same live singleton /api/chat writes to
from services.memory_service import get_memory

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=MemoryResponse)
async def memory() -> MemoryResponse:
    return get_memory(workflow_runner.memory_store)


@router.get("/memories/records", response_model=MemoryRecordsListResponse)
async def list_memory_records(
    memory_type: str | None = Query(default=None, description="Filter by type: episodic, semantic, task_context"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MemoryRecordsListResponse:
    """Browse memory records, newest first."""
    store = workflow_runner.memory_store
    all_records = store.list_recent(memory_type=memory_type, limit=2000)
    total = len(all_records)
    page = all_records[offset : offset + limit]
    return MemoryRecordsListResponse(
        items=[_record_to_out(r) for r in page],
        total=total,
    )


@router.get("/memories/records/search", response_model=MemoryRecordsListResponse)
async def search_memory_records(
    q: str = Query(min_length=1, max_length=200, description="Search query"),
    memory_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> MemoryRecordsListResponse:
    """Search memory records by relevance."""
    store = workflow_runner.memory_store
    results = store.search(query=q, memory_type=memory_type, limit=limit)
    return MemoryRecordsListResponse(
        items=[_record_to_out(r.record) for r in results],
        total=len(results),
    )


@router.delete("/memories/records/{memory_id}")
async def delete_memory_record(memory_id: str) -> dict:
    """Delete a single memory record."""
    deleted = workflow_runner.memory_store.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return {"deleted": True, "memory_id": memory_id}


def _record_to_out(record) -> MemoryRecordOut:
    return MemoryRecordOut(
        memory_id=record.memory_id,
        type=record.type,
        content=record.content,
        task_id=record.task_id,
        source_agent=record.source_agent,
        verification_state=record.verification_state,
        tags=record.tags,
        created_at=record.created_at.isoformat(),
    )


@router.post("/memories/save-content")
async def save_to_memory(
    content: str = Body(min_length=1, max_length=8000, embed=True),
    task_id: str = Body(default="manual-save", embed=True),
) -> dict:
    """Save arbitrary content (e.g. a chat response) as a memory record.

    Wired to the 'Save to Memory' button in the chat UI. Writes a semantic
    record so it appears in memory search and browse results.
    """
    store = workflow_runner.memory_store
    record = MemoryRecord(
        type="semantic",
        content=content,
        task_id=task_id,
        source_agent="user",
        verification_state="unverified",
        tags=["user-saved"],
        provenance="user-save-to-memory",
    )
    store.write(record)
    return {"saved": True, "memory_id": record.memory_id}
