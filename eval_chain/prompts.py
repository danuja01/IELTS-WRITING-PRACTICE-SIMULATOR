"""Type-specific evaluation and rewrite prompts for the LangGraph chain."""
from __future__ import annotations

from eval_chain.schemas import Task1Classification, Task2Classification
from eval_chain.types import (
    MISTAKE_CATEGORIES_TASK1,
    MISTAKE_CATEGORIES_TASK2,
    Task1VisualType,
    Task2EssayType,
)

TASK1_TYPE_LABELS: dict[Task1VisualType, str] = {
    Task1VisualType.LINE_GRAPH: "Line Graph",
    Task1VisualType.BAR_CHART: "Bar Chart",
    Task1VisualType.PIE_CHART: "Pie Chart",
    Task1VisualType.TABLE: "Table",
    Task1VisualType.MAP: "Map",
    Task1VisualType.PROCESS_DIAGRAM: "Process Diagram",
    Task1VisualType.MIXED_CHARTS: "Mixed Charts",
    Task1VisualType.MULTIPLE_DIAGRAMS: "Multiple Diagrams",
}

TASK2_TYPE_LABELS: dict[Task2EssayType, str] = {
    Task2EssayType.OPINION: "Opinion (Agree/Disagree)",
    Task2EssayType.DISCUSSION: "Discussion (Both Views + Opinion)",
    Task2EssayType.ADVANTAGES_DISADVANTAGES: "Advantages & Disadvantages",
    Task2EssayType.PROBLEM_SOLUTION: "Problem / Solution",
    Task2EssayType.TWO_PART: "Two-Part Question",
}


def _format_key_data(items: list[str]) -> str:
    if not items:
        return "- (none identified)"
    return "\n".join(f"- {item}" for item in items)


def analysis_system_prompt_task1(
    classification: Task1Classification,
    rag_context: str,
) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    categories = ", ".join(MISTAKE_CATEGORIES_TASK1)
    dynamic_note = (
        "This is a DYNAMIC visual — expect trend language (rose, fell, fluctuated)."
        if classification.is_dynamic
        else "This is a STATIC visual — expect comparison language, NOT inappropriate trend verbs."
    )
    return f"""You are an IELTS Academic Writing Task 1 examiner.

CLASSIFIED VISUAL TYPE: **{type_label}**
{classification.reasoning}

Classification details:
- Dynamic (time-based): {classification.is_dynamic}
- Time period: {classification.time_period or "N/A"}
- Tense guidance: {classification.tense_guidance}
- {dynamic_note}

Key data/features the report should cover:
{_format_key_data(classification.key_data_needed)}

Apply ONLY the **{type_label}** evaluation framework below. Do not use generic graph advice — maps need spatial/change language, line graphs need trends, pie charts need proportions, etc.

REFERENCE MATERIAL:
{rag_context}

SCORING WORKFLOW:
1. Score Task Achievement against **{type_label}** expectations (overview, key features, data accuracy for this visual type).
2. Score CC, LR, GRA using the band descriptors in the reference material.
3. Assign bands FIRST holistically; list mistakes SECOND for teaching feedback.
4. Mistake categories: {categories}.

This is a REPORT — no opinion, no conclusion paragraph. Do NOT rewrite the student's report."""


def analysis_system_prompt_task2(
    classification: Task2Classification,
    rag_context: str,
) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    categories = ", ".join(MISTAKE_CATEGORIES_TASK2)
    parts = _format_key_data(classification.prompt_parts)
    opinion_note = (
        "The student MUST state a clear personal opinion."
        if classification.requires_opinion
        else "Personal opinion is not required unless the prompt asks for it."
    )
    return f"""You are an IELTS Academic Writing Task 2 examiner.

CLASSIFIED ESSAY TYPE: **{type_label}**
{classification.reasoning}

Prompt parts that must be answered:
{parts}

Structure guidance: {classification.structure_guidance}
{opinion_note}

Apply ONLY the **{type_label}** Task Response framework below — opinion essays need a clear stance; discussion essays need both views; advantage/disadvantage essays need both sides (and a verdict if asked); problem/solution needs linked solutions; two-part questions need both parts developed.

REFERENCE MATERIAL:
{rag_context}

SCORING WORKFLOW:
1. Score Task Response against **{type_label}** expectations.
2. Score CC, LR, GRA using the band descriptors in the reference material.
3. Assign bands FIRST; list mistakes SECOND for feedback.
4. Mistake categories: {categories}.

Do NOT rewrite the essay."""


def rewrite_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    extra = ""
    if classification.visual_type == Task1VisualType.MAP:
        extra = "\n- Use passive voice and location language (north of, adjacent to).\n- Do NOT use trend verbs (rose/fell)."
    elif classification.visual_type == Task1VisualType.PROCESS_DIAGRAM:
        extra = "\n- Use present simple passive for stages (is harvested, is heated).\n- Cover all major stages in correct order."
    elif classification.visual_type == Task1VisualType.LINE_GRAPH:
        extra = "\n- Emphasise trends and line comparisons.\n- Use appropriate past tenses for historical data."
    elif classification.visual_type == Task1VisualType.BAR_CHART:
        extra = (
            "\n- Emphasise rankings and category comparisons."
            + ("\n- Dynamic bar chart: trend language allowed." if classification.is_dynamic else "\n- Static bar chart: comparison language only, no rise/fall.")
        )
    elif classification.visual_type == Task1VisualType.PIE_CHART:
        extra = "\n- Use proportion/share language.\n- Highlight dominant and minor segments."
    elif classification.visual_type in (Task1VisualType.MIXED_CHARTS, Task1VisualType.MULTIPLE_DIAGRAMS):
        extra = "\n- Balance coverage across all visuals/diagrams.\n- Overview must reference each visual."

    return f"""You are an expert IELTS Task 1 coach writing a Band 7.5+ **{type_label}** report.

Tense guidance: {classification.tense_guidance}

STRUCTURE (exactly 4 paragraphs — NO conclusion):
1. Introduction — paraphrase the task (no data)
2. Overview — main trends/changes/comparisons (no specific figures)
3. Body 1 — key features group 1 with selective accurate data
4. Body 2 — key features group 2 with selective accurate data
{extra}

RULES:
- Read data from the chart image — never invent figures.
- Target **150–180 words**. Be concise.
- Wrap improved words/phrases in <<double angle brackets>>.
- Plain text, blank lines between paragraphs. No HTML."""


def rewrite_system_prompt_task2(classification: Task2Classification) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    return f"""You are an expert IELTS Task 2 coach writing a Band 7.5+ **{type_label}** essay.

Structure guidance: {classification.structure_guidance}

RULES:
- Answer every prompt part: {_format_key_data(classification.prompt_parts)}
- {"Include a clear, consistent opinion." if classification.requires_opinion else "Address all required parts of the question."}
- Introduction with thesis → developed body paragraph(s) → conclusion.
- Target length per user message (typically 280+ words).
- Wrap improved words/phrases in <<double angle brackets>>.
- Plain text, blank lines between paragraphs. No HTML."""


def classification_system_prompt_task1() -> str:
    return """You classify IELTS Academic Writing Task 1 questions by analysing the attached chart/image and the question prompt.

Identify the primary visual type from:
- line_graph — trends over time with connected lines
- bar_chart — categorical comparisons with bars (may be static or over time)
- pie_chart — proportions/percentages of a whole
- table — rows/columns of data
- map — spatial layout, before/after location changes
- process_diagram — stages of a process with arrows
- mixed_charts — two different chart types in one task
- multiple_diagrams — two or more similar diagrams (e.g. two maps)

Also determine:
- is_dynamic: true if data changes over a time axis
- time_period: dates/years shown
- key_data_needed: main figures, trends, or features visible
- tense_guidance: which tenses to use in intro/overview/body

Be precise — a map is NOT a line graph; a process is NOT a bar chart."""


def classification_system_prompt_task2() -> str:
    return """You classify IELTS Academic Writing Task 2 essay prompts into exactly one type:

- opinion — agree/disagree, to what extent
- discussion — discuss both views and give your opinion
- advantages_disadvantages — advantages/disadvantages, outweigh, positive/negative development
- problem_solution — causes/problems and solutions
- two_part — two distinct questions requiring separate answers

Extract prompt_parts (each question/part that must be answered), whether an opinion is required, and recommended paragraph structure."""
