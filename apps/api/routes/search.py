"""Global search endpoint (Phase 1E): GET /api/search?q=&limit=.

Additive and read-only. Lexical, case-insensitive matching over the
existing in-process stores with prefix / word-boundary ranking:

    score 5  title starts with the query
    score 4  a title word starts with the query (word-boundary prefix)
    score 3  title contains the query
    score 2  subtitle/body contains the query (snippet returned)
    score 1  weak body match past the windowed excerpt

Privacy contract: approval and schedule results expose only the tool
name, status and id — never parameter values, redacted or not. Memory,
conversation and alert bodies are searched exactly as the existing
browse endpoints expose them; tenant-scoped sources (approvals,
schedules) are filtered to the caller's tenant.
"""

import re

from fastapi import APIRouter, Depends, Query

from auth.dependency import get_current_principal, resolve_tenant_id
from models.search import SearchResponse, SearchResult

router = APIRouter(tags=["search"])

# Per-group cap before the global limit; keeps one noisy store from
# crowding everything else out of the dropdown.
PER_GROUP = 5
SNIPPET_WIDTH = 90


def _score(text: str, needle: str) -> int:
    """Prefix/word-boundary ranking for one haystack against the needle."""
    value = text.casefold()
    if not value or not needle:
        return 0
    if value.startswith(needle):
        return 5
    if any(token.startswith(needle) for token in re.split(r"\W+", value) if token):
        return 4
    if needle in value:
        return 3
    return 0


def _snippet(text: str, needle: str) -> str:
    """Windowed excerpt around the first case-insensitive match."""
    index = text.casefold().find(needle)
    if index < 0:
        return ""
    start = max(0, index - SNIPPET_WIDTH // 2)
    end = min(len(text), index + len(needle) + SNIPPET_WIDTH // 2)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"


def _match(
    needle: str,
    *,
    type_: str,
    id_: str,
    title: str,
    subtitle: str = "",
    body: str = "",
    href: str,
) -> SearchResult | None:
    title_score = _score(title, needle)
    subtitle_score = max(_score(subtitle, needle) - 1, 0)
    body_score = max(_score(body, needle) - 1, 0)
    score = max(title_score, subtitle_score, body_score)
    if score == 0:
        return None
    snippet = _snippet(body, needle) if body_score > 0 else ""
    return SearchResult(
        type=type_, id=id_, title=title.strip(), subtitle=subtitle.strip(),
        href=href, snippet=snippet, score=score,
    )


def _rank(candidates: list[SearchResult | None]) -> list[SearchResult]:
    found = [c for c in candidates if c is not None]
    found.sort(key=lambda r: (-r.score, r.title.casefold()))
    return found[:PER_GROUP]


# ---------------------------------------------------------------------------
# Per-source collectors — every one reads an existing store, never the DB
# schema directly, so search stays in sync with what each page already shows.
# ---------------------------------------------------------------------------


def _collect_tasks(needle: str) -> list[SearchResult]:
    from memory.task_store import get_default_task_store

    store = get_default_task_store()
    return _rank([
        _match(
            needle, type_="task", id_=task.id, title=task.title,
            subtitle=f"{task.status} · {task.agent}",
            href=f"/tasks?open={task.id}",
        )
        for task in store.list_all()
    ])


def _collect_approvals(needle: str, tenant_id: str) -> list[SearchResult]:
    from services.approval_service import get_approval_service

    records = get_approval_service().list_approvals(tenant_id=tenant_id, limit=200)
    # Deliberate: parameters are never part of title/subtitle/body, so no
    # parameter value — sanitized or not — can ever reach a search result.
    return _rank([
        _match(
            needle, type_="approval", id_=record.id, title=record.tool,
            subtitle=f"Approval · {record.status}",
            href=f"/desktop?approval={record.id}",
        )
        for record in records
    ])


def _collect_agents(needle: str) -> list[SearchResult]:
    from services.agents_service import get_agents

    return _rank([
        _match(
            needle, type_="agent", id_=agent.id, title=agent.name,
            subtitle=f"{agent.status} · {agent.specialty}",
            body=agent.description,
            href=f"/agents?open={agent.id}",
        )
        for agent in get_agents().items
    ])


def _collect_workflows(needle: str) -> list[SearchResult]:
    from memory.workflow_store import get_default_workflow_store
    from services.workflows_service import get_workflows

    response = get_workflows(get_default_workflow_store())
    return _rank([
        _match(
            needle, type_="workflow", id_=workflow.id, title=workflow.name,
            subtitle=f"{workflow.state} · {workflow.runs} runs",
            body=workflow.description,
            href=f"/workflows?open={workflow.id}",
        )
        for workflow in response.items
    ])


def _collect_memory(needle: str) -> list[SearchResult]:
    # Same visibility as GET /api/memories/records, which the Memory page
    # browses without a tenant filter.
    from routes.chat import workflow_runner

    records = workflow_runner.memory_store.list_recent(limit=500)
    return _rank([
        _match(
            needle, type_="memory", id_=record.memory_id,
            title=f"{record.type} memory",
            subtitle=f"Memory · {record.source_agent}",
            body=record.content,
            href=f"/memory?record={record.memory_id}",
        )
        for record in records
    ])


def _collect_conversations(needle: str) -> list[SearchResult]:
    from routes.chat import conversation_store

    candidates: list[SearchResult | None] = []
    for summary in conversation_store.list_conversations(limit=50):
        title_match = _match(
            needle, type_="conversation", id_=summary.conversation_id,
            title=summary.title,
            subtitle=f"{summary.message_count} messages",
            href=f"/chat?c={summary.conversation_id}",
        )
        body_match: SearchResult | None = None
        if title_match is None or title_match.score < 4:
            for message in conversation_store.get_messages(summary.conversation_id):
                candidate = _match(
                    needle, type_="conversation", id_=summary.conversation_id,
                    title=summary.title,
                    subtitle=f"{message.role} message",
                    body=message.content,
                    href=f"/chat?c={summary.conversation_id}",
                )
                if candidate is not None and (
                    body_match is None or candidate.score > body_match.score
                ):
                    body_match = candidate
        best = [c for c in (title_match, body_match) if c is not None]
        best.sort(key=lambda r: -r.score)
        candidates.append(best[0] if best else None)
    return _rank(candidates)


def _collect_alerts(needle: str) -> list[SearchResult]:
    from routes.chat import alert_store

    return _rank([
        _match(
            needle, type_="alert", id_=str(alert["id"]),
            title=str(alert.get("title", "")),
            subtitle=f"Alert · {alert.get('category', '')}",
            body=str(alert.get("description", "")),
            href=alert.get("link") or "/alert",
        )
        for alert in alert_store.list_all(limit=200)
    ])


def _collect_schedules(needle: str, tenant_id: str) -> list[SearchResult]:
    from memory.schedule_store import get_default_schedule_store

    records = get_default_schedule_store().list_all(tenant_id)
    # Parameters are excluded by design — same rule as approvals.
    return _rank([
        _match(
            needle, type_="schedule", id_=record.id, title=record.name,
            subtitle=f"Schedule · {record.status} · {record.tool}",
            href="/desktop",
        )
        for record in records
    ])


@router.get("/search", response_model=SearchResponse)
async def global_search(
    q: str = Query(min_length=2, max_length=100, description="Search query"),
    limit: int = Query(default=25, ge=1, le=50, description="Max total results"),
    principal=Depends(get_current_principal),
) -> SearchResponse:
    needle = q.casefold().strip()
    tenant_id = resolve_tenant_id(principal)

    ordered = [
        ("tasks", _collect_tasks(needle)),
        ("approvals", _collect_approvals(needle, tenant_id)),
        ("agents", _collect_agents(needle)),
        ("workflows", _collect_workflows(needle)),
        ("memory", _collect_memory(needle)),
        ("conversations", _collect_conversations(needle)),
        ("alerts", _collect_alerts(needle)),
        ("schedules", _collect_schedules(needle, tenant_id)),
    ]

    groups: dict[str, list[SearchResult]] = {}
    remaining = limit
    for name, results in ordered:
        if not results or remaining <= 0:
            continue
        take = results[:remaining]
        groups[name] = take
        remaining -= len(take)
    return SearchResponse(
        query=q, total=sum(len(v) for v in groups.values()), groups=groups,
    )
