"""Lightweight RAG + OpenAI evaluation for IELTS writing attempts (LangGraph pipeline)."""
from __future__ import annotations

from eval_chain.graph import (
    DEFAULT_MODEL,
    REWRITE_MODEL,
    ProgressCallback,
    run_evaluation_chain,
)
from eval_chain.utils import (
    ChartImage,
    CriterionScores,
    MistakeItem,
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
    "CriterionScores",
    "MistakeItem",
    "WritingEvaluationAnalysis",
    "WritingEvaluationResult",
    "WritingRewriteResult",
    "evaluate_writing",
    "evaluation_to_dict",
    "retrieve_rag_context",
]

MISTAKE_CATEGORIES_TASK2 = (
    "Grammar",
    "Spelling",
    "Vocabulary",
    "Word choice",
    "Sentence structure",
    "Awkward phrasing",
    "Cohesion",
    "Punctuation",
    "Task response",
    "Other",
)

MISTAKE_CATEGORIES_TASK1 = (
    "Grammar",
    "Spelling",
    "Vocabulary",
    "Word choice",
    "Sentence structure",
    "Awkward phrasing",
    "Cohesion",
    "Punctuation",
    "Task achievement",
    "Data accuracy",
    "Overview",
    "Other",
)


def retrieve_rag_context(task_type: str) -> str:
    """Legacy hook — RAG is now loaded per question subtype inside the LangGraph chain."""
    from eval_chain.retriever import retrieve_task1_context, retrieve_task2_context
    from eval_chain.types import Task1VisualType, Task2EssayType

    if (task_type or "task2").lower() == "task1":
        return retrieve_task1_context(Task1VisualType.LINE_GRAPH)
    return retrieve_task2_context(Task2EssayType.OPINION)


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
    data = _base_evaluation_to_dict(result, model=model)
    if result.question_subtype:
        data["question_subtype"] = result.question_subtype
    if result.classification_reasoning:
        data["classification_reasoning"] = result.classification_reasoning
    return data
