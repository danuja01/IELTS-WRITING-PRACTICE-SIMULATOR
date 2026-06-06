"""Lightweight RAG + OpenAI evaluation for IELTS writing attempts."""
from __future__ import annotations

import os
from pathlib import Path

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
RAG_DIR = APP_DIR / "ielts_rag"
DEFAULT_MODEL = os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")

MISTAKE_CATEGORIES = (
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
        description="One of: Grammar, Spelling, Vocabulary, Word choice, Sentence structure, Awkward phrasing, Cohesion, Punctuation, Task response, Other",
    )
    wrong_text: str = Field(
        ...,
        description="Exact incorrect phrase or sentence from the student's essay",
    )
    corrected_text: str = Field(
        ...,
        description="Corrected version of wrong_text",
    )
    issue: str = Field(..., description="Why this is wrong and how it affects the band score")
    suggestion: str = Field(..., description="Clear advice to avoid this mistake in future")


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
        description="Exhaustive list of every language and content error found in the essay",
    )
    areas_for_improvement: list[str] = Field(
        ...,
        min_length=2,
        description="Actionable improvement areas for the candidate",
    )
    rewritten_essay: str = Field(
        ...,
        description=(
            "Band 7.5+ rewrite preserving the student's ideas. "
            "Wrap every improved word or phrase in double angle brackets, e.g. <<improved phrase>>"
        ),
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
    categories = ", ".join(MISTAKE_CATEGORIES)
    return f"""You are a certified IELTS Writing examiner with years of experience scoring Academic module scripts.

Evaluate the student's essay strictly using official IELTS band descriptors and the reference material below.
Apply the four criteria ({task_criterion}, Coherence and Cohesion, Lexical Resource, Grammatical Range and Accuracy).
Calculate the overall band as the average of the four criteria, rounded to the nearest 0.5.

Reference material (RAG context):
{rag}

Mistake identification rules (CRITICAL):
- List EVERY error in the essay — do not skip or summarise. Be exhaustive.
- Include all grammar errors, spelling mistakes, wrong word forms, awkward or unnatural sentences, weak vocabulary, cohesion problems, punctuation issues, and task-response gaps.
- Each mistake must have wrong_text (exact excerpt from the essay) and corrected_text (the fix).
- Use category from: {categories}
- Short essays may have 10+ mistakes; longer essays often have 20–40+. Include them all.

Rewrite rules:
- Keep the student's original ideas and argument.
- Upgrade to Band 7.5+ standard.
- Wrap EVERY improved word or phrase in double angle brackets: <<like this>>
- Mark vocabulary upgrades, grammar fixes, and stronger collocations with <<>>.

Scoring rules:
- Be fair but rigorous — mirror how real examiners score.
- For Task 1, the rewrite must include a clear overview and accurate data language.
- For Task 2, the rewrite must fully address the prompt with developed body paragraphs."""


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

Return a complete evaluation with every mistake identified individually."""


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
        raise ValueError("OpenAI API key is not configured")
    if not (essay or "").strip():
        raise ValueError("Essay content is empty")

    elapsed_minutes = (elapsed_ms / 60000.0) if elapsed_ms is not None else None
    client = instructor.from_openai(
        OpenAI(api_key=api_key),
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
