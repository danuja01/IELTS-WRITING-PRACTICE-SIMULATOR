"""IELTS writing evaluation via LangGraph pipeline."""
from __future__ import annotations

from eval_chain.graph import (
    DEFAULT_MODEL,
    REWRITE_MODEL,
    ProgressCallback,
    run_evaluation_chain,
)
from eval_chain.utils import (
    ChartImage,
    CorrectionItem,
    CriterionComment,
    CriterionScores,
    SentenceComment,
    WritingEvaluationAnalysis,
    WritingEvaluationResult,
    WritingRewriteResult,
    chart_image_from_path,
    evaluation_to_dict as _base_evaluation_to_dict,
)

__all__ = [
    "DEFAULT_MODEL",
    "REWRITE_MODEL",
    "ChartImage",
    "CorrectionItem",
    "CriterionComment",
    "CriterionScores",
    "SentenceComment",
    "WritingEvaluationAnalysis",
    "WritingEvaluationResult",
    "WritingRewriteResult",
    "evaluate_writing",
    "evaluation_to_dict",
]


def evaluate_writing(
    *,
    api_key: str,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None = None,
    elapsed_ms: int | None = None,
    model: str | None = None,
    on_progress: ProgressCallback = None,
    chart_image_path: str | None = None,
    upload_root: str | None = None,
) -> WritingEvaluationResult:
    chart = None
    if (task_type or "task2").lower() == "task1" and chart_image_path and upload_root:
        chart = chart_image_from_path(chart_image_path, upload_root)

    return run_evaluation_chain(
        api_key=api_key,
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        elapsed_ms=elapsed_ms,
        model=model,
        on_progress=on_progress,
        chart=chart,
    )


def evaluation_to_dict(result: WritingEvaluationResult, *, model: str) -> dict:
    return _base_evaluation_to_dict(result, model=model)
