"""Shared utilities for the evaluation chain."""
from __future__ import annotations

import base64
import math
import mimetypes
import os
import re
from typing import Any

from pydantic import BaseModel, Field


class ChartImage:
    def __init__(self, *, b64: str, media_type: str):
        self.b64 = b64
        self.media_type = media_type


class CriterionScores(BaseModel):
    task: float = Field(..., ge=0, le=9, description="Task Achievement (T1) or Task Response (T2)")
    coherence_cohesion: float = Field(..., ge=0, le=9)
    lexical_resource: float = Field(..., ge=0, le=9)
    grammatical_range: float = Field(..., ge=0, le=9)


class MistakeItem(BaseModel):
    category: str = Field(..., description="Mistake category from the allowed list")
    wrong_text: str = Field(
        ...,
        description=(
            "ONLY the incorrect word or short phrase (e.g. 'competetion', 'more better'). "
            "Not a full sentence unless the entire sentence is wrong."
        ),
    )
    corrected_text: str = Field(
        ...,
        description="The corrected word or short phrase matching wrong_text scope",
    )
    issue: str = Field(..., description="Brief explanation of why this is wrong")
    suggestion: str = Field(..., description="One practical tip to avoid this in future")


class WritingEvaluationAnalysis(BaseModel):
    band_score: float = Field(..., ge=0, le=9)
    criterion_scores: CriterionScores
    overall_feedback: list[str] = Field(
        ...,
        min_length=3,
        max_length=8,
        description=(
            "Bullet-point summary of strengths and weaknesses. "
            "Each item is one concise point (no paragraphs)."
        ),
    )
    mistakes: list[MistakeItem]
    areas_for_improvement: list[str] = Field(..., min_length=2)


class WritingRewriteResult(BaseModel):
    rewritten_essay: str = Field(
        ...,
        description=(
            "Complete model answer. Wrap ONLY changed words or short phrases in <<>> — "
            "never an entire sentence. Most sentences should have zero highlights."
        ),
    )


class WritingEvaluationResult(BaseModel):
    band_score: float
    criterion_scores: CriterionScores
    overall_feedback: list[str]
    mistakes: list[MistakeItem]
    areas_for_improvement: list[str]
    rewritten_essay: str
    question_subtype: str = ""
    classification_reasoning: str = ""


def evaluation_to_dict(result: WritingEvaluationResult, *, model: str) -> dict:
    return {
        "band_score": result.band_score,
        "criterion_scores": result.criterion_scores.model_dump(),
        "overall_feedback": result.overall_feedback,
        "mistakes": [m.model_dump() for m in result.mistakes],
        "areas_for_improvement": result.areas_for_improvement,
        "rewritten_essay": result.rewritten_essay,
        "model": model,
    }


def is_task1(task_type: str) -> bool:
    return (task_type or "task2").lower() == "task1"


def task_label(task_type: str) -> str:
    return "IELTS Academic Writing Task 1" if is_task1(task_type) else "IELTS Academic Writing Task 2"


def target_word_count(task_type: str, word_count: int | None) -> int:
    if is_task1(task_type):
        original = word_count or 150
        return min(180, max(150, original))
    original = word_count or 280
    return max(280, original, int(original * 1.05))


def chart_image_from_path(image_path: str | None, upload_root: str | None) -> ChartImage | None:
    if not image_path or not upload_root:
        return None
    rel = os.path.normpath(image_path)
    if rel.startswith("..") or os.path.isabs(rel):
        return None
    full = os.path.abspath(os.path.join(upload_root, rel))
    root = os.path.abspath(upload_root)
    if full != root and not full.startswith(root + os.sep):
        return None
    if not os.path.isfile(full):
        return None
    media_type = mimetypes.guess_type(full)[0] or "image/png"
    with open(full, "rb") as fh:
        return ChartImage(b64=base64.standard_b64encode(fh.read()).decode("ascii"), media_type=media_type)


def user_message_content(text: str, chart: ChartImage | None) -> str | list[dict[str, Any]]:
    if not chart:
        return text
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:{chart.media_type};base64,{chart.b64}"}},
    ]


def clean_rewrite(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def round_band_average(scores: CriterionScores) -> float:
    avg = (
        scores.task
        + scores.coherence_cohesion
        + scores.lexical_resource
        + scores.grammatical_range
    ) / 4.0
    return math.floor(avg * 2 + 0.5) / 2


def looks_truncated(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.endswith((".", "!", "?", '"', "»", ")")):
        return False
    tail = stripped[-120:]
    if re.search(r"[.!?][\s\"')\]]*$", tail):
        return False
    return True
