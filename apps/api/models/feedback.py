"""Feedback submission model."""

from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=120)
    sentiment: Literal["up", "down"]
    comment: str = Field(default="", max_length=2000)
