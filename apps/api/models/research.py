from typing import Literal

from pydantic import BaseModel

ResearchType = Literal["Architecture note", "Experiment", "Working draft"]


class ResearchNote(BaseModel):
    id: str
    title: str
    type: ResearchType
    date: str


class ResearchResponse(BaseModel):
    items: list[ResearchNote]
    total: int
