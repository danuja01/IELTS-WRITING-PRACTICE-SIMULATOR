"""Pydantic schemas for classification and evaluation chain."""
from __future__ import annotations

from pydantic import BaseModel, Field

from eval_chain.types import Task1VisualType, Task2EssayType


class Task1Classification(BaseModel):
    visual_type: Task1VisualType = Field(
        ...,
        description="Primary visual type shown in the chart/image or implied by the prompt",
    )
    is_dynamic: bool = Field(
        ...,
        description="True if data changes over time (line graph, time-series); False for static comparisons",
    )
    time_period: str = Field(
        default="",
        description="Time range shown, e.g. '1990-2020', or empty if not applicable",
    )
    key_data_needed: list[str] = Field(
        ...,
        description="Key figures, trends, or features the student should reference",
    )
    tense_guidance: str = Field(
        ...,
        description="Recommended tenses for intro, overview, and body paragraphs",
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this visual type was chosen",
    )


class Task2Classification(BaseModel):
    essay_type: Task2EssayType = Field(
        ...,
        description="Essay question subtype derived from the prompt wording",
    )
    requires_opinion: bool = Field(
        ...,
        description="Whether the student must state a personal position",
    )
    prompt_parts: list[str] = Field(
        ...,
        description="Distinct parts of the question that must each be answered",
    )
    structure_guidance: str = Field(
        ...,
        description="Recommended paragraph structure for this essay type",
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this essay type was chosen",
    )
