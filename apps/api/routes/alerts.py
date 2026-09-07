"""Notification / alert endpoints.

Persistent alerts backed by SQLite. Alerts are auto-generated from
system events (task completions, failures) and survive page refresh
and server restarts when AION_MEMORY_DB_PATH is configured.
"""

from fastapi import APIRouter, HTTPException

from models.notifications import AlertItem, AlertsResponse, MarkReadRequest
from routes.chat import alert_store

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=AlertsResponse)
async def list_alerts(unread_only: bool = False, limit: int = 50) -> AlertsResponse:
    """List alerts, newest first. Pass unread_only=true to filter to unread only."""
    items = alert_store.list_all(unread_only=unread_only, limit=limit)
    unread_count = alert_store.count_unread()
    return AlertsResponse(
        items=[AlertItem(**item) for item in items],
        total=len(items),
        unread_count=unread_count,
    )


@router.post("/alerts/mark-read")
async def mark_alerts_read(payload: MarkReadRequest) -> dict:
    """Mark specific alerts as read by their IDs."""
    updated = alert_store.mark_read(payload.alert_ids)
    return {"updated": updated}


@router.post("/alerts/mark-all-read")
async def mark_all_alerts_read() -> dict:
    """Mark all alerts as read."""
    updated = alert_store.mark_all_read()
    return {"updated": updated}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str) -> dict:
    """Delete a single alert."""
    deleted = alert_store.delete(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"deleted": True, "alert_id": alert_id}
