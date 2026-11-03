from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ChatMode = Literal["auto", "quick", "research", "manual"]
AgentId = Literal["planner", "researcher", "critic", "memory"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: ChatMode = "auto"
    selected_agents: list[AgentId] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, max_length=120)
    memory_enabled: bool = True
    verification_enabled: bool = True

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        return value

    @model_validator(mode="after")
    def manual_mode_requires_agents(self) -> "ChatRequest":
        if self.mode == "manual" and not self.selected_agents:
            raise ValueError("Manual mode requires at least one selected agent")
        if self.mode != "manual" and self.selected_agents:
            self.selected_agents = []
        return self


class UsedAgent(BaseModel):
    id: AgentId
    name: str
    status: Literal["completed", "failed"]
    summary: str


class PendingApprovalInfo(BaseModel):
    """Public, token-free summary of a chat-created pending approval.
    The chat path can only ever create pending rows — nothing here
    grants, executes or exposes approval state beyond what a human can
    already see in the approval queue."""

    approval_id: str
    task_id: str
    tool: str
    status: Literal["pending_approval"]
    expires_at: str
    requires: Literal["human_approval"]
    queue_path: str


class ChatResponse(BaseModel):
    task_id: str
    conversation_id: str
    author: Literal["AION"] = "AION"
    answer: str
    mode: ChatMode
    status: Literal["completed", "failed"]
    used_agents: list[UsedAgent] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time_ms: int = Field(ge=0)
    selection_summary: str
    sources: list[str] = Field(default_factory=list)
    error: str | None = None
    development_mode: bool = False
    revision_count: int = Field(default=0, ge=0, le=1)
    # Phase 2: set when the chat message created a pending desktop
    # approval. Optional + additive — existing clients ignore it.
    pending_approval: PendingApprovalInfo | None = None
    # Phase 1F: Secret Guard. Kinds of credentials removed from the
    # message before it reached any store, log or model call. Optional +
    # additive — existing clients ignore it.
    warnings: list[str] = Field(default_factory=list)
