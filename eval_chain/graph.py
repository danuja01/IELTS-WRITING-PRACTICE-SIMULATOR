"""LangGraph evaluation pipeline: classify → retrieve → analyse → rewrite."""
from __future__ import annotations

import os
from typing import Any, Callable, TypedDict

import instructor
from langgraph.graph import END, StateGraph
from openai import OpenAI

from eval_chain.prompts import (
    TASK1_TYPE_LABELS,
    TASK2_TYPE_LABELS,
    analysis_system_prompt_task1,
    analysis_system_prompt_task2,
    classification_system_prompt_task1,
    classification_system_prompt_task2,
    rewrite_system_prompt_task1,
    rewrite_system_prompt_task2,
)
from eval_chain.retriever import retrieve_task1_context, retrieve_task2_context
from eval_chain.schemas import Task1Classification, Task2Classification
from eval_chain.utils import (
    ChartImage,
    WritingEvaluationAnalysis,
    WritingEvaluationResult,
    WritingRewriteResult,
    clean_rewrite,
    is_task1,
    looks_truncated,
    round_band_average,
    target_word_count,
    task_label,
    user_message_content,
)

DEFAULT_MODEL = os.environ.get("OPENAI_EVAL_MODEL", "gpt-4o-mini")
REWRITE_MODEL = os.environ.get("OPENAI_REWRITE_MODEL", DEFAULT_MODEL)
ANALYSIS_MAX_TOKENS = int(os.environ.get("OPENAI_ANALYSIS_MAX_TOKENS", "16384"))
REWRITE_MAX_TOKENS = int(os.environ.get("OPENAI_REWRITE_MAX_TOKENS", "16384"))
EVAL_TEMPERATURE = float(os.environ.get("OPENAI_EVAL_TEMPERATURE", "0.3"))

ProgressCallback = Callable[[int, str], None] | None


class EvalState(TypedDict, total=False):
    api_key: str
    task_type: str
    question_title: str
    question_prompt: str
    essay: str
    word_count: int | None
    elapsed_minutes: float | None
    chart: ChartImage | None
    analysis_model: str
    rewrite_model: str
    on_progress: ProgressCallback

    task1_classification: Task1Classification | None
    task2_classification: Task2Classification | None
    rag_context: str
    question_subtype: str
    classification_reasoning: str

    analysis: WritingEvaluationAnalysis | None
    rewritten_essay: str


def _make_client(api_key: str):
    return instructor.from_openai(OpenAI(api_key=api_key), mode=instructor.Mode.JSON)


def _llm_kwargs(limit: int) -> dict:
    return {"temperature": EVAL_TEMPERATURE, "max_completion_tokens": limit}


def _analysis_user_prompt(state: EvalState) -> str:
    task_type = state["task_type"]
    meta = []
    wc = state.get("word_count")
    em = state.get("elapsed_minutes")
    if wc is not None:
        meta.append(f"Word count: {wc}")
    if em is not None:
        meta.append(f"Time spent: {em:.1f} minutes")
    if is_task1(task_type):
        meta.append("Expected structure: intro → overview → body 1 → body 2 (NO conclusion)")
        meta.append("Target length: 150–180 words")
    meta_block = "\n".join(meta) if meta else "Word count: unknown"
    chart = state.get("chart")
    chart_line = (
        "\nChart/diagram image is attached — evaluate Task Achievement and data accuracy against it.\n"
        if chart and is_task1(task_type)
        else ""
    )
    subtype = state.get("question_subtype", "")
    subtype_line = f"\nClassified subtype: {subtype}\n" if subtype else ""

    return f"""{task_label(task_type)} evaluation request
{subtype_line}
Question title: {state.get("question_title") or "Untitled"}
Question prompt:
{state.get("question_prompt") or "(not provided)"}{chart_line}
Attempt metadata:
{meta_block}

Student {"report" if is_task1(task_type) else "essay"}:
{state["essay"]}

Return band scores, overall feedback, every mistake, and improvement areas. Do not rewrite."""


def _rewrite_user_prompt(state: EvalState, analysis: WritingEvaluationAnalysis) -> str:
    task_type = state["task_type"]
    wc = state.get("word_count")
    target = target_word_count(task_type, wc)
    top_issues = "\n".join(f"- {m.category}: {m.issue}" for m in analysis.mistakes[:12])
    improvements = "\n".join(f"- {a}" for a in analysis.areas_for_improvement)
    chart = state.get("chart")
    chart_note = (
        "\nThe chart/diagram image is attached — use accurate figures from it.\n"
        if chart and is_task1(task_type)
        else ""
    )
    length_line = (
        f"Target length: {target} words maximum (Task 1: 150–180 words)."
        if is_task1(task_type)
        else f"Target length: at least {target} words."
    )
    closing = (
        "Write the COMPLETE improved report (4 paragraphs: intro, overview, body 1, body 2). "
        "150–180 words. NO conclusion. Use chart data accurately."
        if is_task1(task_type)
        else "Write the COMPLETE improved essay. Preserve the student's argument. Finish with a proper conclusion."
    )
    return f"""{task_label(task_type)} — write a complete Band 7.5+ model answer

Classified subtype: {state.get("question_subtype", "")}

Question title: {state.get("question_title") or "Untitled"}
Question prompt:
{state.get("question_prompt") or "(not provided)"}{chart_note}
Original student writing ({wc or "unknown"} words):
{state["essay"]}

{length_line}

Key issues to fix:
{top_issues}

Focus areas:
{improvements}

Examiner summary:
{chr(10).join(f"- {p}" for p in analysis.overall_feedback)}

{closing}"""


def classify_question(state: EvalState) -> dict[str, Any]:
    client = _make_client(state["api_key"])
    task_type = state["task_type"]
    on_progress = state.get("on_progress")
    if on_progress:
        msg = "Analysing chart and classifying visual type…" if is_task1(task_type) else "Classifying essay question type…"
        on_progress(8, msg)

    if is_task1(task_type):
        user_text = f"""Classify this Task 1 question.

Question title: {state.get("question_title") or "Untitled"}
Question prompt:
{state.get("question_prompt") or "(not provided)"}

Analyse the attached image (if present) to determine visual type, time period, key data, and tense guidance."""
        result: Task1Classification = client.chat.completions.create(
            model=state["analysis_model"],
            messages=[
                {"role": "system", "content": classification_system_prompt_task1()},
                {"role": "user", "content": user_message_content(user_text, state.get("chart"))},
            ],
            response_model=Task1Classification,
            **_llm_kwargs(4096),
        )
        subtype = TASK1_TYPE_LABELS[result.visual_type]
        return {
            "task1_classification": result,
            "task2_classification": None,
            "question_subtype": subtype,
            "classification_reasoning": result.reasoning,
        }

    user_text = f"""Classify this Task 2 essay prompt.

Question title: {state.get("question_title") or "Untitled"}
Question prompt:
{state.get("question_prompt") or "(not provided)"}"""
    result2: Task2Classification = client.chat.completions.create(
        model=state["analysis_model"],
        messages=[
            {"role": "system", "content": classification_system_prompt_task2()},
            {"role": "user", "content": user_text},
        ],
        response_model=Task2Classification,
        **_llm_kwargs(4096),
    )
    subtype = TASK2_TYPE_LABELS[result2.essay_type]
    return {
        "task1_classification": None,
        "task2_classification": result2,
        "question_subtype": subtype,
        "classification_reasoning": result2.reasoning,
    }


def retrieve_context(state: EvalState) -> dict[str, Any]:
    on_progress = state.get("on_progress")
    if on_progress:
        on_progress(12, f"Loading {state.get('question_subtype', '')} evaluation criteria…")

    if is_task1(state["task_type"]):
        assert state.get("task1_classification") is not None
        rag = retrieve_task1_context(state["task1_classification"].visual_type)
    else:
        assert state.get("task2_classification") is not None
        rag = retrieve_task2_context(state["task2_classification"].essay_type)
    return {"rag_context": rag}


def run_analysis(state: EvalState) -> dict[str, Any]:
    client = _make_client(state["api_key"])
    on_progress = state.get("on_progress")
    if on_progress:
        msg = "Evaluating report against type-specific criteria…" if is_task1(state["task_type"]) else "Evaluating essay against type-specific criteria…"
        on_progress(20, msg)

    if is_task1(state["task_type"]):
        system = analysis_system_prompt_task1(state["task1_classification"], state["rag_context"])
    else:
        system = analysis_system_prompt_task2(state["task2_classification"], state["rag_context"])

    analysis: WritingEvaluationAnalysis = client.chat.completions.create(
        model=state["analysis_model"],
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user_message_content(_analysis_user_prompt(state), state.get("chart")),
            },
        ],
        response_model=WritingEvaluationAnalysis,
        **_llm_kwargs(ANALYSIS_MAX_TOKENS),
    )
    analysis.band_score = round_band_average(analysis.criterion_scores)
    return {"analysis": analysis}


def run_rewrite(state: EvalState) -> dict[str, Any]:
    client = _make_client(state["api_key"])
    analysis = state["analysis"]
    assert analysis is not None
    on_progress = state.get("on_progress")
    if on_progress:
        msg = "Writing type-specific Band 7.5+ model report…" if is_task1(state["task_type"]) else "Writing type-specific Band 7.5+ model essay…"
        on_progress(70, msg)

    if is_task1(state["task_type"]):
        system = rewrite_system_prompt_task1(state["task1_classification"])
    else:
        system = rewrite_system_prompt_task2(state["task2_classification"])

    user_text = _rewrite_user_prompt(state, analysis)
    result: WritingRewriteResult = client.chat.completions.create(
        model=state["rewrite_model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message_content(user_text, state.get("chart"))},
        ],
        response_model=WritingRewriteResult,
        **_llm_kwargs(REWRITE_MAX_TOKENS),
    )
    rewrite = clean_rewrite(result.rewritten_essay)
    if looks_truncated(rewrite):
        rewrite = _continue_rewrite(client, state, rewrite)
    return {"rewritten_essay": rewrite}


def _continue_rewrite(client, state: EvalState, partial: str) -> str:
    task_type = state["task_type"]
    target = target_word_count(task_type, state.get("word_count"))
    if is_task1(task_type):
        finish = "Continue and complete the report (4 paragraphs). NO conclusion. 150–180 words."
        system = rewrite_system_prompt_task1(state["task1_classification"])
    else:
        finish = f"Continue and complete the essay through conclusion. At least {target} words."
        system = rewrite_system_prompt_task2(state["task2_classification"])
    user_text = (
        f"The rewrite was cut off. {finish} Use <<>> for improvements.\n\n"
        f"Question prompt:\n{state.get('question_prompt') or '(not provided)'}\n\n"
        f"Partial:\n{partial}"
    )
    continuation: WritingRewriteResult = client.chat.completions.create(
        model=state["rewrite_model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message_content(user_text, state.get("chart"))},
        ],
        response_model=WritingRewriteResult,
        **_llm_kwargs(REWRITE_MAX_TOKENS),
    )
    extra = clean_rewrite(continuation.rewritten_essay)
    if extra.startswith(partial[-80:].strip()):
        return extra
    return clean_rewrite(partial.rstrip() + "\n\n" + extra.lstrip())


def build_evaluation_graph():
    """Build LangGraph: classify → retrieve → analyse → rewrite."""
    graph = StateGraph(EvalState)
    graph.add_node("classify", classify_question)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("analyse", run_analysis)
    graph.add_node("rewrite", run_rewrite)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "analyse")
    graph.add_edge("analyse", "rewrite")
    graph.add_edge("rewrite", END)
    return graph.compile()


_EVAL_GRAPH = None


def get_evaluation_graph():
    global _EVAL_GRAPH
    if _EVAL_GRAPH is None:
        _EVAL_GRAPH = build_evaluation_graph()
    return _EVAL_GRAPH


def run_evaluation_chain(
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
    chart: ChartImage | None = None,
) -> WritingEvaluationResult:
    if not api_key:
        raise ValueError("OpenAI API key is not configured")
    if not (essay or "").strip():
        raise ValueError("Essay content is empty")

    elapsed_minutes = (elapsed_ms / 60000.0) if elapsed_ms is not None else None
    analysis_model = model or DEFAULT_MODEL
    rewrite_model = REWRITE_MODEL if REWRITE_MODEL != DEFAULT_MODEL else analysis_model

    initial: EvalState = {
        "api_key": api_key,
        "task_type": task_type,
        "question_title": question_title,
        "question_prompt": question_prompt,
        "essay": essay,
        "word_count": word_count,
        "elapsed_minutes": elapsed_minutes,
        "chart": chart,
        "analysis_model": analysis_model,
        "rewrite_model": rewrite_model,
        "on_progress": on_progress,
    }

    final = get_evaluation_graph().invoke(initial)
    analysis = final["analysis"]
    assert analysis is not None

    if on_progress:
        on_progress(95, "Finalising evaluation…")

    return WritingEvaluationResult(
        band_score=analysis.band_score,
        criterion_scores=analysis.criterion_scores,
        overall_feedback=analysis.overall_feedback,
        mistakes=analysis.mistakes,
        areas_for_improvement=analysis.areas_for_improvement,
        rewritten_essay=final.get("rewritten_essay", ""),
        question_subtype=final.get("question_subtype", ""),
        classification_reasoning=final.get("classification_reasoning", ""),
    )
