"""Profile endpoints (Phase 1D).

GET  /api/profile  → {configured, profile, created_at, updated_at}
PUT  /api/profile  → upserts the single-tenant identity row.

No seeded profile: a fresh install reports configured=false and the UI
opens in setup state. 422 responses come from the model validators.
"""

from fastapi import APIRouter

from memory.profile_store import get_default_profile_store
from models.profile import Profile, ProfileResponse, slugify

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile() -> ProfileResponse:
    row = get_default_profile_store().get_profile()
    if row is None:
        return ProfileResponse(configured=False)
    return ProfileResponse(
        configured=True,
        profile=Profile(**row),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.put("/profile", response_model=ProfileResponse)
async def put_profile(payload: Profile) -> ProfileResponse:
    data = payload.model_dump()
    # Empty username is derived from the display name — one canonical slug.
    data["username"] = data["username"] or slugify(data["display_name"]) or "owner"
    row = get_default_profile_store().upsert_profile(data)
    return ProfileResponse(
        configured=True,
        profile=Profile(**row),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
