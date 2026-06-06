"""Lightweight RAG + OpenAI evaluation for IELTS writing attempts."""
from __future__ import annotations

import base64
import math
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
RAG_DIR = APP_DIR / "ielts_rag"
DEFAULT_MODEL = os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")
REWRITE_MODEL = os.environ.get("OPENAI_REWRITE_MODEL", DEFAULT_MODEL)
ANALYSIS_MAX_TOKENS = int(os.environ.get("OPENAI_ANALYSIS_MAX_TOKENS", "16384"))
REWRITE_MAX_TOKENS = int(os.environ.get("OPENAI_REWRITE_MAX_TOKENS", "16384"))
EVAL_TEMPERATURE = float(os.environ.get("OPENAI_EVAL_TEMPERATURE", "0.3"))

ProgressCallback = Callable[[int, str], None] | None

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


class ChartImage:
    def __init__(self, *, b64: str, media_type: str):
        self.b64 = b64
        self.media_type = media_type


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
        description=(
            "Holistic feedback summarising strengths and weaknesses. "
            "Briefly justify each criterion band (like a ChatGPT IELTS evaluation table)."
        ),
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
    if _is_task1(task_type):
        chunks = [
            _read_rag_file("evaluation_guide_task1.md"),
            _read_rag_file("task1_structure.md"),
            _read_rag_file("task1_criteria.md"),
        ]
    else:
        chunks = [
            _read_rag_file("evaluation_guide_task2.md"),
            _read_rag_file("task2_criteria.md"),
        ]
    return "\n\n---\n\n".join(c for c in chunks if c)


def _is_task1(task_type: str) -> bool:
    return (task_type or "task2").lower() == "task1"


def _task_label(task_type: str) -> str:
    return "IELTS Academic Writing Task 1" if _is_task1(task_type) else "IELTS Academic Writing Task 2"


def _mistake_categories(task_type: str) -> str:
    cats = MISTAKE_CATEGORIES_TASK1 if _is_task1(task_type) else MISTAKE_CATEGORIES_TASK2
    return ", ".join(cats)


def _target_word_count(task_type: str, word_count: int | None) -> int:
    if _is_task1(task_type):
        original = word_count or 150
        return min(180, max(150, original))
    original = word_count or 280
    return max(280, original, int(original * 1.05))


def _chart_image_from_path(image_path: str | None, upload_root: str | None) -> ChartImage | None:
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


def _user_message_content(text: str, chart: ChartImage | None) -> str | list[dict[str, Any]]:
    if not chart:
        return text
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{chart.media_type};base64,{chart.b64}"},
        },
    ]


def _clean_rewrite(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _round_band_average(scores: CriterionScores) -> float:
    avg = (
        scores.task
        + scores.coherence_cohesion
        + scores.lexical_resource
        + scores.grammatical_range
    ) / 4.0
    # IELTS rounds halves up (5.25 → 5.5); avoid Python banker's rounding.
    return math.floor(avg * 2 + 0.5) / 2


def _analysis_system_prompt(task_type: str, *, has_chart: bool) -> str:
    rag = retrieve_rag_context(task_type)
    categories = _mistake_categories(task_type)
    if _is_task1(task_type):
        chart_note = (
            "A chart/diagram image is attached. Study it carefully — score Task Achievement and Data accuracy against the actual visual data."
            if has_chart
            else "No chart image was provided; evaluate Task Achievement from the prompt and essay only."
        )
        return f"""You are an IELTS Task 1 tutor scoring exactly like **ChatGPT IELTS evaluation** — balanced, never overly strict.

This is a **report** (chart, graph, table, map, or plan) — NOT an essay. No opinion. No conclusion paragraph.

{chart_note}

Reference material:
{rag}

SCORING RULES — assign bands FIRST (holistically), list mistakes SECOND (for feedback only):

• **Task Achievement:** Intro + overview + key features covering main changes/trends. For **map/plan** tasks: Band **6.5** when main developments are described even if some facility locations or numbers are imprecise. Do NOT drop to 5.5 just because you can list data inaccuracies in the mistake section.

• **Coherence & Cohesion:** Intro → overview → body 1 → body 2 = Band **6.5** when structure is clear. Awkward sentences do not drop this below 6.0.

• **Lexical Resource:** Band **6.0–6.5** when map/data vocabulary range is adequate (relocated, facilities, planned, increased, terminal). Spelling errors (transpotation, redevelopong) do NOT justify Band 5.5.

• **Grammatical Range:** Band **6.0** when meaning is clear despite article, capitalisation, and grammar errors. Reserve 5.5 only when errors frequently impede understanding.

**ChatGPT alignment (CRITICAL):** A script ChatGPT would call "one of your stronger map responses" at **6.5 overall** must receive **6.5 overall** here — typically 6.5 / 6.5 / 6.5 / 6.0. Do NOT score 5.5 overall for the same script.

**Mistake list ≠ low bands.** You may list many errors for teaching while still assigning Band 6.5 criteria. Categories: {categories}.

Do NOT rewrite the report."""

    return f"""You are an experienced IELTS Writing Task 2 tutor scoring an **essay** — balanced, fair, like ChatGPT.

Apply: Task Response, Coherence and Cohesion, Lexical Resource, Grammatical Range and Accuracy.

Reference material:
{rag}

SCORING RULES (score FIRST, mistakes SECOND):

• **Task Response:** Clear position + all parts answered → **6.5–7.0** even if language is weak.
• **Coherence & Cohesion:** Clear essay structure (intro, body, conclusion) → **6.0–6.5**.
• **Lexical Resource:** Adequate range → **6.0** even with spelling errors.
• **Grammatical Range:** Complex attempts + clear meaning → **5.5–6.0**.

Do NOT be stricter than ChatGPT. Mistakes are for feedback only — categories: {categories}.

Do NOT rewrite the essay."""


def _rewrite_system_prompt(task_type: str) -> str:
    if _is_task1(task_type):
        return """You are an expert IELTS Task 1 coach writing a Band 7.5+ **report** (NOT an essay).

STRUCTURE (exactly 4 paragraphs — NO conclusion):
1. **Introduction:** Paraphrase the task title only (1–2 sentences). No data. No overview here.
2. **Overview:** Main trends/differences at a glance (2–3 sentences). No specific figures.
3. **Body 1:** One group of key features with accurate data and comparisons from the chart.
4. **Body 2:** Remaining key features with accurate data and comparisons.

CRITICAL RULES:
- Read data from the chart image provided — never invent figures.
- **NO conclusion paragraph. NO personal opinion.**
- Target length: **150–180 words** total. Be concise.
- Wrap improved words/phrases in <<double angle brackets>>.
- Plain text, blank lines between paragraphs. No HTML tags."""

    return """You are an expert IELTS Task 2 coach writing a Band 7.5+ **essay**.

STRUCTURE: Introduction with thesis → 2–3 developed body paragraphs → conclusion summarising your position.

RULES:
- Write the COMPLETE essay through the conclusion.
- Target length per user message (typically 280+ words).
- Wrap improved words/phrases in <<double angle brackets>>.
- Plain text, blank lines between paragraphs. No HTML tags."""


def _analysis_user_prompt(
    *,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    elapsed_minutes: float | None,
    has_chart: bool = False,
) -> str:
    meta = []
    if word_count is not None:
        meta.append(f"Word count: {word_count}")
    if elapsed_minutes is not None:
        meta.append(f"Time spent: {elapsed_minutes:.1f} minutes")
    if _is_task1(task_type):
        meta.append("Expected structure: intro (paraphrase) → overview → body 1 → body 2 (NO conclusion)")
        meta.append("Target length: 150–180 words")
    meta_block = "\n".join(meta) if meta else "Word count: unknown"
    chart_line = (
        "\nChart/diagram image is attached — evaluate Task Achievement and data accuracy against it.\n"
        if has_chart and _is_task1(task_type)
        else ""
    )

    return f"""{_task_label(task_type)} evaluation request

Question title: {question_title or "Untitled"}
Question prompt:
{question_prompt or "(not provided)"}{chart_line}
Attempt metadata:
{meta_block}

Student {"report" if _is_task1(task_type) else "essay"}:
{essay}

Return band scores, overall feedback, every mistake, and improvement areas. Do not rewrite."""


def _rewrite_user_prompt(
    *,
    task_type: str,
    question_title: str,
    question_prompt: str,
    essay: str,
    word_count: int | None,
    analysis: WritingEvaluationAnalysis,
    has_chart: bool,
) -> str:
    target = _target_word_count(task_type, word_count)
    top_issues = "\n".join(f"- {m.category}: {m.issue}" for m in analysis.mistakes[:12])
    improvements = "\n".join(f"- {a}" for a in analysis.areas_for_improvement)
    chart_note = (
        "\nThe chart/diagram image is attached — use accurate figures from it.\n"
        if has_chart and _is_task1(task_type)
        else ""
    )
    length_line = (
        f"Target length: {target} words maximum (Task 1: 150–180 words)."
        if _is_task1(task_type)
        else f"Target length: at least {target} words."
    )
    closing = (
        "Write the COMPLETE improved report (4 paragraphs: intro, overview, body 1, body 2). "
        "150–180 words. NO conclusion. Use chart data accurately."
        if _is_task1(task_type)
        else "Write the COMPLETE improved essay. Preserve the student's argument. Finish with a proper conclusion."
    )

    return f"""{_task_label(task_type)} — write a complete Band 7.5+ model answer

Question title: {question_title or "Untitled"}
Question prompt:
{question_prompt or "(not provided)"}{chart_note}
Original student writing ({word_count or "unknown"} words):
{essay}

{length_line}

Key issues to fix:
{top_issues}

Focus areas:
{improvements}

Examiner summary: {analysis.overall_feedback}

{closing}"""


def _make_client(api_key: str):
    return instructor.from_openai(
        OpenAI(api_key=api_key),
        mode=instructor.Mode.JSON,
    )


def _llm_kwargs(limit: int) -> dict:
    return {"temperature": EVAL_TEMPERATURE, "max_completion_tokens": limit}


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
    chart: ChartImage | None = None,
) -> WritingEvaluationAnalysis:
    user_text = _analysis_user_prompt(
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        elapsed_minutes=elapsed_minutes,
        has_chart=bool(chart),
    )
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _analysis_system_prompt(task_type, has_chart=bool(chart))},
            {"role": "user", "content": _user_message_content(user_text, chart)},
        ],
        response_model=WritingEvaluationAnalysis,
        **_llm_kwargs(ANALYSIS_MAX_TOKENS),
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
    chart: ChartImage | None = None,
) -> str:
    user_text = _rewrite_user_prompt(
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        analysis=analysis,
        has_chart=bool(chart),
    )
    result: WritingRewriteResult = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _rewrite_system_prompt(task_type)},
            {"role": "user", "content": _user_message_content(user_text, chart)},
        ],
        response_model=WritingRewriteResult,
        **_llm_kwargs(REWRITE_MAX_TOKENS),
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
            chart=chart,
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
    chart: ChartImage | None = None,
) -> str:
    if _is_task1(task_type):
        finish_instruction = (
            "Continue EXACTLY where it stopped and complete the report (4 paragraphs total). "
            "NO conclusion. Target 150–180 words. Use chart data accurately."
        )
    else:
        finish_instruction = (
            f"Continue EXACTLY where it stopped and complete the essay through a proper conclusion. "
            f"Target at least {target_words} words."
        )
    user_text = (
        f"The following Band 7.5+ rewrite was cut off. {finish_instruction} "
        f"Use <<>> for improvements. Plain text only.\n\n"
        f"Question prompt:\n{question_prompt or '(not provided)'}\n\n"
        f"Partial rewrite so far:\n{partial}"
    )
    continuation: WritingRewriteResult = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _rewrite_system_prompt(task_type)},
            {"role": "user", "content": _user_message_content(user_text, chart)},
        ],
        response_model=WritingRewriteResult,
        **_llm_kwargs(REWRITE_MAX_TOKENS),
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
    chart_image_path: str | None = None,
    upload_root: str | None = None,
) -> WritingEvaluationResult:
    if not api_key:
        raise ValueError("OpenAI API key is not configured")
    if not (essay or "").strip():
        raise ValueError("Essay content is empty")

    elapsed_minutes = (elapsed_ms / 60000.0) if elapsed_ms is not None else None
    analysis_model = model or DEFAULT_MODEL
    rewrite_model = REWRITE_MODEL if REWRITE_MODEL != DEFAULT_MODEL else analysis_model
    client = _make_client(api_key)
    chart = None
    if _is_task1(task_type) and chart_image_path and upload_root:
        chart = _chart_image_from_path(chart_image_path, upload_root)

    if on_progress:
        msg = "Analyzing chart and report…" if _is_task1(task_type) else "Analyzing essay and finding all mistakes…"
        on_progress(15, msg)
    analysis = _run_analysis(
        client,
        model=analysis_model,
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        elapsed_minutes=elapsed_minutes,
        chart=chart,
    )
    analysis.band_score = _round_band_average(analysis.criterion_scores)

    if on_progress:
        msg = "Writing Band 7.5+ Task 1 model report…" if _is_task1(task_type) else "Writing complete Band 7.5+ version…"
        on_progress(70, msg)
    rewritten_essay = _run_rewrite(
        client,
        model=rewrite_model,
        task_type=task_type,
        question_title=question_title,
        question_prompt=question_prompt,
        essay=essay,
        word_count=word_count,
        analysis=analysis,
        chart=chart,
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
