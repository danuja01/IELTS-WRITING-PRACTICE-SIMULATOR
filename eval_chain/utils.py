"""Shared utilities and schemas for the evaluation chain."""
from __future__ import annotations

import base64
import math
import mimetypes
import os
import re
from typing import Any, Literal

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


class CorrectionItem(BaseModel):
    original: str = Field(..., description="Incorrect word or short phrase from the student's text")
    corrected: str = Field(..., description="Corrected version")
    note: str = Field(default="", description="Optional brief note")


class SentenceComment(BaseModel):
    status: Literal["accurately_hit", "slightly_off", "off_key"] = Field(
        ...,
        description="accurately_hit = good; slightly_off = minor issues; off_key = significant problem",
    )
    sentence: str = Field(..., description="Exact sentence from the student's writing")
    comment: str = Field(..., description="Brief constructive explanation")


class CriterionComment(BaseModel):
    summary: str = Field(..., description="One paragraph of feedback for this criterion")
    corrections_title: str = Field(
        default="",
        description="Subsection title e.g. 'Misspelling', 'Grammatical Errors', 'Linking Issues'",
    )
    corrections: list[CorrectionItem] = Field(default_factory=list)
    sentence_comments: list[SentenceComment] = Field(
        default_factory=list,
        description="Sentence-level comments — mainly for Task Achievement/Response",
    )


class WritingEvaluationAnalysis(BaseModel):
    criterion_scores: CriterionScores
    band_score: float = Field(..., ge=0, le=9)
    task_comment: CriterionComment
    coherence_comment: CriterionComment
    lexical_comment: CriterionComment
    grammar_comment: CriterionComment
    corrections: list[CorrectionItem] = Field(
        default_factory=list,
        description="Task 2: top corrections list shown before criterion comments",
    )
    overall_review: str = Field(
        ...,
        description="One balanced paragraph summarising strengths, weaknesses, and overall impression",
    )


class WritingRewriteResult(BaseModel):
    rewritten_essay: str = Field(
        ...,
        description="Complete optimized composition — plain text, no markup or highlights",
    )


class WritingEvaluationResult(BaseModel):
    band_score: float
    criterion_scores: CriterionScores
    overall_review: str
    task_comment: CriterionComment
    coherence_comment: CriterionComment
    lexical_comment: CriterionComment
    grammar_comment: CriterionComment
    corrections: list[CorrectionItem]
    rewritten_essay: str
    question_subtype: str = ""
    format_version: int = 2


# Legacy aliases for imports
MistakeItem = CorrectionItem


def evaluation_to_dict(result: WritingEvaluationResult, *, model: str) -> dict:
    return {
        "format_version": result.format_version,
        "band_score": result.band_score,
        "criterion_scores": result.criterion_scores.model_dump(),
        "overall_review": result.overall_review,
        "task_comment": result.task_comment.model_dump(),
        "coherence_comment": result.coherence_comment.model_dump(),
        "lexical_comment": result.lexical_comment.model_dump(),
        "grammar_comment": result.grammar_comment.model_dump(),
        "corrections": [c.model_dump() for c in result.corrections],
        "optimized_composition": result.rewritten_essay,
        "rewritten_essay": result.rewritten_essay,
        "question_subtype": result.question_subtype,
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
    text = re.sub(r"<<([^>]+)>>", r"\1", text)
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
