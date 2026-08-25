from typing import Literal

from pydantic import BaseModel, Field

MemoryType = Literal["short_term", "long_term", "vector"]


class MemoryCategory(BaseModel):
    id: str
    title: str
    description: str
    type: MemoryType
    count: str
    usage: int = Field(ge=0, le=100)


class MemoryResponse(BaseModel):
    categories: list[MemoryCategory]
    policies: list[str]
