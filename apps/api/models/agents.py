from typing import Literal

from pydantic import BaseModel, Field

AgentStatus = Literal["online", "standby", "offline"]


class Agent(BaseModel):
    id: str
    name: str
    description: str
    status: AgentStatus
    confidence: int = Field(ge=0, le=100)
    specialty: str


class AgentsResponse(BaseModel):
    items: list[Agent]
    total: int
