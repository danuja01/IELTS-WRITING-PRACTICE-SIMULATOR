"""LangGraph evaluation pipeline: classify → analyse → rewrite."""
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
    question_subtype: str

    analysis: WritingEvaluationAnalysis | None
    rewritten_essay: str


def _make_client(api_key: str):
    return instructor.from_openai(OpenAI(api_key=api_key), mode=instructor.Mode.JSON)


def _llm_kwargs(limit: int) -> dict:
    return {"temperature": EVAL_TEMPERATURE, "max_completion_tokens": limit}


def _analysis_user_prompt(state: EvalState) -> str:
    task_type = state["task_type"]
    wc = state.get("word_count")
    meta = [f"Word count: {wc}"] if wc is not None else []
    chart = state.get("chart")
    chart_line = "\nChart attached — check data accuracy.\n" if chart and is_task1(task_type) else ""

    return f"""{task_label(task_type)} — evaluate and return structured per-criterion feedback.

Question: {state.get("question_title") or "Untitled"}
Prompt: {state.get("question_prompt") or "(not provided)"}{chart_line}
{chr(10).join(meta)}

Student writing:
{state["essay"]}"""


def _rewrite_user_prompt(state: EvalState, analysis: WritingEvaluationAnalysis) -> str:
    task_type = state["task_type"]
    target = target_word_count(task_type, state.get("word_count"))
    chart = state.get("chart")
    chart_note = "\nUse accurate figures from the attached chart.\n" if chart and is_task1(task_type) else ""

    return f"""Write an optimized composition for this {task_label(task_type)} attempt.

Prompt: {state.get("question_prompt") or "(not provided)"}{chart_note}

Original ({state.get("word_count") or "?"} words):
{state["essay"]}

Target: {"150–180 words, 4 paragraphs, no conclusion" if is_task1(task_type) else f"at least {target} words with conclusion"}.

Examiner summary: {analysis.overall_review}

Write a clean optimized version — plain text only, no highlights."""


def classify_question(state: EvalState) -> dict[str, Any]:
    client = _make_client(state["api_key"])
    on_progress = state.get("on_progress")
    if on_progress:
        on_progress(10, "Analysing question type…")

    if is_task1(state["task_type"]):
        user_text = f"Classify:\n{state.get('question_prompt') or ''}"
        result: Task1Classification = client.chat.completions.create(
            model=state["analysis_model"],
            messages=[
                {"role": "system", "content": classification_system_prompt_task1()},
                {"role": "user", "content": user_message_content(user_text, state.get("chart"))},
            ],
            response_model=Task1Classification,
            **_llm_kwargs(4096),
        )
        return {
            "task1_classification": result,
            "task2_classification": None,
            "question_subtype": TASK1_TYPE_LABELS[result.visual_type],
        }

    user_text = f"Classify:\n{state.get('question_prompt') or ''}"
    result2: Task2Classification = client.chat.completions.create(
        model=state["analysis_model"],
        messages=[
            {"role": "system", "content": classification_system_prompt_task2()},
            {"role": "user", "content": user_text},
        ],
        response_model=Task2Classification,
        **_llm_kwargs(4096),
    )
    return {
        "task1_classification": None,
        "task2_classification": result2,
        "question_subtype": TASK2_TYPE_LABELS[result2.essay_type],
    }


def run_analysis(state: EvalState) -> dict[str, Any]:
    client = _make_client(state["api_key"])
    on_progress = state.get("on_progress")
    if on_progress:
        on_progress(25, "Generating per-criterion feedback…")

    if is_task1(state["task_type"]):
        system = analysis_system_prompt_task1(state["task1_classification"])
    else:
        system = analysis_system_prompt_task2(state["task2_classification"])

    analysis: WritingEvaluationAnalysis = client.chat.completions.create(
        model=state["analysis_model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message_content(_analysis_user_prompt(state), state.get("chart"))},
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
        on_progress(70, "Writing optimized composition…")

    if is_task1(state["task_type"]):
        system = rewrite_system_prompt_task1(state["task1_classification"])
    else:
        system = rewrite_system_prompt_task2(state["task2_classification"])

    result: WritingRewriteResult = client.chat.completions.create(
        model=state["rewrite_model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message_content(_rewrite_user_prompt(state, analysis), state.get("chart"))},
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
    if is_task1(task_type):
        system = rewrite_system_prompt_task1(state["task1_classification"])
        finish = "Complete the report (4 paragraphs). Plain text only."
    else:
        system = rewrite_system_prompt_task2(state["task2_classification"])
        finish = "Complete through the conclusion. Plain text only."
    user_text = f"Continue from where it stopped. {finish}\n\nPartial:\n{partial}"
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
    graph = StateGraph(EvalState)
    graph.add_node("classify", classify_question)
    graph.add_node("analyse", run_analysis)
    graph.add_node("rewrite", run_rewrite)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "analyse")
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

    analysis_model = model or DEFAULT_MODEL
    rewrite_model = REWRITE_MODEL if REWRITE_MODEL != DEFAULT_MODEL else analysis_model

    final = get_evaluation_graph().invoke({
        "api_key": api_key,
        "task_type": task_type,
        "question_title": question_title,
        "question_prompt": question_prompt,
        "essay": essay,
        "word_count": word_count,
        "chart": chart,
        "analysis_model": analysis_model,
        "rewrite_model": rewrite_model,
        "on_progress": on_progress,
    })

    analysis = final["analysis"]
    assert analysis is not None
    if on_progress:
        on_progress(95, "Finalising evaluation…")

    return WritingEvaluationResult(
        band_score=analysis.band_score,
        criterion_scores=analysis.criterion_scores,
        overall_review=analysis.overall_review,
        task_comment=analysis.task_comment,
        coherence_comment=analysis.coherence_comment,
        lexical_comment=analysis.lexical_comment,
        grammar_comment=analysis.grammar_comment,
        corrections=analysis.corrections,
        rewritten_essay=final.get("rewritten_essay", ""),
        question_subtype=final.get("question_subtype", ""),
    )
