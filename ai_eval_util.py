"""Lightweight RAG + OpenAI evaluation for IELTS writing attempts."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
RAG_DIR = APP_DIR / "ielts_rag"
DEFAULT_MODEL = os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")
REWRITE_MODEL = os.environ.get("OPENAI_REWRITE_MODEL", DEFAULT_MODEL)
ANALYSIS_MAX_TOKENS = int(os.environ.get("OPENAI_ANALYSIS_MAX_TOKENS", "16384"))
REWRITE_MAX_TOKENS = int(os.environ.get("OPENAI_REWRITE_MAX_TOKENS", "16384"))

ProgressCallback = Callable[[int, str], None] | None

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


class WritingEvaluationAnalysis(BaseModel):
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


class WritingRewriteResult(BaseModel):
    rewritten_essay: str = Field(
        ...,
        description=(
            "The COMPLETE Band 7.5+ essay from first word to last. "
            "Must include every paragraph fully developed. "
            "Use plain text with blank lines between paragraphs. "
            "Wrap improved words/phrases in <<double angle brackets>>. "
            "No HTML tags."
        ),
    )


class WritingEvaluationResult(BaseModel):
    band_score: float
    criterion_scores: CriterionScores
    overall_feedback: str
    mistakes: list[MistakeItem]
    areas_for_improvement: list[str]
    rewritten_essay: str


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


def _target_word_count(task_type: str, word_count: int | None) -> int:
    task = (task_type or "task2").lower()
    minimum = 170 if task == "task1" else 280
    original = word_count or minimum
    return max(minimum, original, int(original * 1.05))


def _clean_rewrite(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _analysis_system_prompt(task_type: str) -> str:
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

Do NOT write a rewritten essay in this response — scoring and mistakes only.

Scoring rules:
- Be fair but rigorous — mirror how real examiners score."""


def _rewrite_system_prompt(task_type: str) -> str:
    task = (task_type or "task2").lower()
    if task == "task1":
        structure = (
            "Introduction paraphrasing the task, clear overview sentence, "
            "body paragraphs with accurate data comparisons, formal academic tone."
        )
    else:
        structure = (
            "Introduction with clear thesis, two or three fully developed body paragraphs "
            "with examples/explanation, and a conclusion that summarises the position."
        )
    return f"""You are an expert IELTS Writing coach who produces authentic Band 7.5–8.0 model answers.

Your ONLY job is to write a COMPLETE rewritten essay. Requirements:

COMPLETENESS (CRITICAL):
- Write the ENTIRE essay from the opening sentence to the final concluding sentence.
- Never stop mid-paragraph, mid-sentence, or mid-thought.
- Cover every idea from the student's original essay and develop each one further.
- Meet or exceed the minimum word count given in the user message.

Band 7.5+ quality:
- {structure}
- Varied sentence structures: mix simple, compound, and complex sentences.
- Less common vocabulary and strong collocations used naturally.
- Clear cohesive devices (however, furthermore, consequently, in contrast).
- Formal academic register; no contractions or informal phrases.
- Fully address every part of the question prompt.

Highlighting:
- Wrap EVERY improved word or phrase in double angle brackets: <<like this>>
- Highlight grammar fixes, stronger vocabulary, and upgraded collocations.

Format:
- Plain text only. Use blank lines between paragraphs.
- NO HTML tags (no <br>, <p>, etc.)."""


def _analysis_user_prompt(
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

Return band scores, overall feedback, every mistake, and improvement areas. Do not rewrite the essay."""


def _rewrite_user_prompt(
    *,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    analysis: WritingEvaluationAnalysis,
) -> str:
    target = _target_word_count(task_type, word_count)
    top_issues = "\n".join(f"- {m.category}: {m.issue}" for m in analysis.mistakes[:12])
    improvements = "\n".join(f"- {a}" for a in analysis.areas_for_improvement)

    return f"""{_task_label(task_type)} — write a complete Band 7.5+ model answer

Question title: {question_title or "Untitled"}
Question prompt:
{question_prompt or "(not provided)"}

Original student essay ({word_count or "unknown"} words):
{essay}

Target length: at least {target} words (do not write less).

Key issues to fix in your rewrite:
{top_issues}

Focus areas:
{improvements}

Examiner summary: {analysis.overall_feedback}

Write the COMPLETE improved essay now. Preserve the student's core argument and ideas but upgrade every aspect to Band 7.5+ standard. Finish with a proper conclusion."""


def _make_client(api_key: str):
    return instructor.from_openai(
        OpenAI(api_key=api_key),
        mode=instructor.Mode.JSON,
    )


def _completion_limit(limit: int) -> dict:
    """Newer OpenAI models (e.g. gpt-5.x) require max_completion_tokens, not max_tokens."""
    return {"max_completion_tokens": limit}


def _run_analysis(
    client,
    *,
    model: str,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    elapsed_minutes: float | None,
) -> WritingEvaluationAnalysis:
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _analysis_system_prompt(task_type)},
            {
                "role": "user",
                "content": _analysis_user_prompt(
                    task_type=task_type,
                    question_title=question_title,
                    question_prompt=question_prompt,
                    essay=essay,
                    word_count=word_count,
                    elapsed_minutes=elapsed_minutes,
                ),
            },
        ],
        response_model=WritingEvaluationAnalysis,
        **_completion_limit(ANALYSIS_MAX_TOKENS),
    )


def _run_rewrite(
    client,
    *,
    model: str,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    analysis: WritingEvaluationAnalysis,
) -> str:
    result: WritingRewriteResult = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _rewrite_system_prompt(task_type)},
            {
                "role": "user",
                "content": _rewrite_user_prompt(
                    task_type=task_type,
                    question_title=question_title,
                    question_prompt=question_prompt,
                    essay=essay,
                    word_count=word_count,
                    analysis=analysis,
                ),
            },
        ],
        response_model=WritingRewriteResult,
        **_completion_limit(REWRITE_MAX_TOKENS),
    )
    rewrite = _clean_rewrite(result.rewritten_essay)
    if _looks_truncated(rewrite):
        rewrite = _continue_rewrite(
            client,
            model=model,
            task_type=task_type,
            question_prompt=question_prompt,
            partial=rewrite,
            target_words=_target_word_count(task_type, word_count),
        )
    return rewrite


def _looks_truncated(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.endswith((".", "!", "?", '"', "»", ")")):
        return False
    tail = stripped[-120:]
    if re.search(r"[.!?][\s\"')\]]*$", tail):
        return False
    return True


def _continue_rewrite(
    client,
    *,
    model: str,
    task_type: str,
    question_prompt: str,
    partial: str,
    target_words: int,
) -> str:
    continuation: WritingRewriteResult = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _rewrite_system_prompt(task_type)},
            {
                "role": "user",
                "content": (
                    f"The following Band 7.5+ rewrite was cut off before it finished. "
                    f"Continue EXACTLY where it stopped and complete the essay through a proper conclusion. "
                    f"Target total length: at least {target_words} words. "
                    f"Use <<>> for any new improvements. Plain text only, no HTML.\n\n"
                    f"Question prompt:\n{question_prompt or '(not provided)'}\n\n"
                    f"Partial rewrite so far:\n{partial}"
                ),
            },
        ],
        response_model=WritingRewriteResult,
        **_completion_limit(REWRITE_MAX_TOKENS),
    )
    extra = _clean_rewrite(continuation.rewritten_essay)
    if extra.startswith(partial[-80:].strip()):
        return extra
    return _clean_rewrite(partial.rstrip() + "\n\n" + extra.lstrip())


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
) -> WritingEvaluationResult:
    if not api_key:
        raise ValueError("OpenAI API key is not configured")
    if not (essay or "").strip():
        raise ValueError("Essay content is empty")

    elapsed_minutes = (elapsed_ms / 60000.0) if elapsed_ms is not None else None
    analysis_model = model or DEFAULT_MODEL
    rewrite_model = REWRITE_MODEL if REWRITE_MODEL != DEFAULT_MODEL else analysis_model
    client = _make_client(api_key)

    if on_progress:
        on_progress(15, "Analyzing essay and finding all mistakes…")
    analysis = _run_analysis(
        client,
        model=analysis_model,
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        elapsed_minutes=elapsed_minutes,
    )

    if on_progress:
        on_progress(70, "Writing complete Band 7.5+ version…")
    rewritten_essay = _run_rewrite(
        client,
        model=rewrite_model,
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        analysis=analysis,
    )

    if on_progress:
        on_progress(95, "Finalising evaluation…")

    return WritingEvaluationResult(
        band_score=analysis.band_score,
        criterion_scores=analysis.criterion_scores,
        overall_feedback=analysis.overall_feedback,
        mistakes=analysis.mistakes,
        areas_for_improvement=analysis.areas_for_improvement,
        rewritten_essay=rewritten_essay,
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
