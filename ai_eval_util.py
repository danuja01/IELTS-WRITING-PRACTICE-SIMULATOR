"""Lightweight RAG + OpenRouter evaluation for IELTS writing attempts."""
from __future__ import annotations

import os
from pathlib import Path

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
RAG_DIR = APP_DIR / "ielts_rag"
DEFAULT_MODEL = os.environ.get("OPENROUTER_EVAL_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class CriterionScores(BaseModel):
    task: float = Field(
        ...,
        ge=0,
        le=9,
        description="Task Achievement (Task 1) or Task Response (Task 2)",
    )
    coherence_cohesion: float = Field(..., ge=0, le=9)
    lexical_resource: float = Field(..., ge=0, le=9)
    grammatical_range: float = Field(..., ge=0, le=9)


class MistakeItem(BaseModel):
    category: str = Field(
        ...,
        description="Criterion area, e.g. Lexical Resource or Grammar",
    )
    excerpt: str = Field(..., description="Quoted phrase or sentence from the essay")
    issue: str = Field(..., description="What is wrong and why it limits the band score")
    suggestion: str = Field(..., description="How to fix or improve this point")


class WritingEvaluationResult(BaseModel):
    band_score: float = Field(
        ...,
        ge=0,
        le=9,
        description="Predicted overall IELTS band, rounded to nearest 0.5",
    )
    criterion_scores: CriterionScores
    overall_feedback: str = Field(
        ...,
        description="Holistic examiner-style feedback on strengths and weaknesses",
    )
    mistakes: list[MistakeItem] = Field(
        ...,
        min_length=1,
        description="Specific mistakes with excerpts from the essay",
    )
    areas_for_improvement: list[str] = Field(
        ...,
        min_length=2,
        description="Actionable improvement areas for the candidate",
    )
    rewritten_essay: str = Field(
        ...,
        description="A Band 7.5+ rewrite preserving the original ideas",
    )


def _read_rag_file(name: str) -> str:
    path = RAG_DIR / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def retrieve_rag_context(task_type: str) -> str:
    """Select predefined IELTS criteria chunks for the task type (lightweight RAG)."""
    task = (task_type or "task2").lower()
    chunks = [_read_rag_file("evaluation_guide.md")]
    if task == "task1":
        chunks.append(_read_rag_file("task1_criteria.md"))
    else:
        chunks.append(_read_rag_file("task2_criteria.md"))
    return "\n\n---\n\n".join(c for c in chunks if c)


def _task_label(task_type: str) -> str:
    return "IELTS Academic Writing Task 1" if (task_type or "").lower() == "task1" else "IELTS Academic Writing Task 2"


def _system_prompt(task_type: str) -> str:
    rag = retrieve_rag_context(task_type)
    task_criterion = "Task Achievement" if (task_type or "").lower() == "task1" else "Task Response"
    return f"""You are a certified IELTS Writing examiner with years of experience scoring Academic module scripts.

Evaluate the student's essay strictly using official IELTS band descriptors and the reference material below.
Apply the four criteria ({task_criterion}, Coherence and Cohesion, Lexical Resource, Grammatical Range and Accuracy).
Calculate the overall band as the average of the four criteria, rounded to the nearest 0.5.

Reference material (RAG context):
{rag}

Rules:
- Be fair but rigorous — mirror how real examiners score.
- Quote short excerpts from the student's essay when identifying mistakes.
- The rewritten essay must keep the student's ideas but demonstrate Band 7.5+ language, structure, and development.
- For Task 1, ensure the rewrite includes a clear overview and accurate data language.
- For Task 2, ensure the rewrite fully addresses the prompt with developed body paragraphs."""


def _user_prompt(
    *,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    elapsed_minutes: float | None,
) -> str:
    meta = []
    if word_count is not None:
        meta.append(f"Word count: {word_count}")
    if elapsed_minutes is not None:
        meta.append(f"Time spent: {elapsed_minutes:.1f} minutes")
    meta_block = "\n".join(meta) if meta else "Word count: unknown"

    return f"""{_task_label(task_type)} evaluation request

Question title: {question_title or "Untitled"}
Question prompt:
{question_prompt or "(not provided)"}

Attempt metadata:
{meta_block}

Student essay:
{essay}
"""


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
) -> WritingEvaluationResult:
    if not api_key:
        raise ValueError("OpenRouter API key is not configured")
    if not (essay or "").strip():
        raise ValueError("Essay content is empty")

    elapsed_minutes = (elapsed_ms / 60000.0) if elapsed_ms is not None else None
    client = instructor.from_openai(
        OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key),
        mode=instructor.Mode.JSON,
    )

    return client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(task_type)},
            {
                "role": "user",
                "content": _user_prompt(
                    task_type=task_type,
                    question_title=question_title,
                    question_prompt=question_prompt,
                    essay=essay,
                    word_count=word_count,
                    elapsed_minutes=elapsed_minutes,
                ),
            },
        ],
        response_model=WritingEvaluationResult,
        max_tokens=4096,
    )


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
