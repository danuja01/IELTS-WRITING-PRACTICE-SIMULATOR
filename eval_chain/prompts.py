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


def _analysis_output_rules(categories: str) -> str:
    return f"""OUTPUT FORMAT:
- overall_feedback: 4–6 bullet points (strengths + weaknesses). One point per line. No paragraphs.
- mistakes: only genuine errors worth fixing. Skip nitpicks.
  • wrong_text / corrected_text: the smallest wrong phrase and its fix (e.g. "competetion" → "competition"), NOT whole sentences unless necessary.
  • Do NOT flag Task Response issues that apply to a different essay type than the one classified.
- Score bands first, then list mistakes for feedback.
- Categories: {categories}."""


def _rewrite_highlight_rules() -> str:
    return """HIGHLIGHTING (<<word>>):
- Wrap ONLY the specific word or short phrase that changed. Example: "drives <<healthy>> competition" not "<<drives healthy competition among businesses>>".
- Grammar fixes: highlight just the corrected word(s), not the whole sentence.
- Aim for under 20 highlights total. Most sentences should have no highlights."""


def analysis_system_prompt_task1(
    classification: Task1Classification,
    rag_context: str,
) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    categories = ", ".join(MISTAKE_CATEGORIES_TASK1)
    return f"""You are a fair IELTS Task 1 examiner marking a **{type_label}** report.

Use the reference material for this visual type. Be balanced — clear structure with minor language errors should score around Band 6.

Type: {type_label} | Dynamic: {classification.is_dynamic} | Tenses: {classification.tense_guidance}

REFERENCE:
{rag_context}

{_analysis_output_rules(categories)}

This is a report — no opinion, no conclusion. Do not rewrite."""


def analysis_system_prompt_task2(
    classification: Task2Classification,
    rag_context: str,
) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    categories = ", ".join(MISTAKE_CATEGORIES_TASK2)
    fairness = _task2_fairness_note(classification)
    return f"""You are a fair IELTS Task 2 examiner marking a **{type_label}** essay.

Prompt parts to answer: {_format_key_data(classification.prompt_parts)}

{fairness}

Use the reference material for this essay type only. Be balanced — a clear answer to the actual question with language errors should score around Band 6.

REFERENCE:
{rag_context}

{_analysis_output_rules(categories)}

Do not rewrite."""


def _task2_fairness_note(classification: Task2Classification) -> str:
    t = classification.essay_type
    if t == Task2EssayType.TWO_PART:
        return (
            "FAIRNESS: Two-part prompts (e.g. 'Why?' + 'positive or negative?') need both parts answered. "
            "A clear one-sided opinion on the second part is fine — do NOT require a separate disadvantages "
            "paragraph or both-sides discussion unless the prompt explicitly asks for both views."
        )
    if t == Task2EssayType.OPINION:
        return (
            "FAIRNESS: Opinion essays need a clear stance. A brief concession ('while there are drawbacks') "
            "is fine — do NOT require equal coverage of both sides."
        )
    if t == Task2EssayType.DISCUSSION:
        return "FAIRNESS: Both views must be presented before the writer's opinion."
    if t == Task2EssayType.ADVANTAGES_DISADVANTAGES:
        return (
            "FAIRNESS: Require both sides only when the prompt asks for advantages AND disadvantages, "
            "or asks which outweighs. A 'positive development' opinion question does not need a full disadvantages body."
        )
    return "FAIRNESS: Score against what this prompt actually asks, not a generic essay template."


def rewrite_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    return f"""Write a Band 7.5+ **{type_label}** Task 1 report.

4 paragraphs: intro → overview → body 1 → body 2. No conclusion. 150–180 words.
Use chart data accurately. Tenses: {classification.tense_guidance}

{_rewrite_highlight_rules()}
Plain text, blank lines between paragraphs."""


def rewrite_system_prompt_task2(classification: Task2Classification) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    return f"""Write a Band 7.5+ **{type_label}** Task 2 essay.

Answer: {_format_key_data(classification.prompt_parts)}
Structure: {classification.structure_guidance}
{"State a clear opinion." if classification.requires_opinion else ""}

Preserve the student's argument where it is reasonable. 280+ words.

{_rewrite_highlight_rules()}
Plain text, blank lines between paragraphs."""


def classification_system_prompt_task1() -> str:
    return """Classify the Task 1 visual from the image and prompt.

Types: line_graph, bar_chart, pie_chart, table, map, process_diagram, mixed_charts, multiple_diagrams.

Return: visual_type, is_dynamic, time_period, key_data_needed, tense_guidance, reasoning."""


def classification_system_prompt_task2() -> str:
    return """Classify the Task 2 prompt into one type:

- opinion — agree/disagree, to what extent
- discussion — discuss both views and give your opinion
- advantages_disadvantages — explicit advantages/disadvantages or outweigh
- problem_solution — causes/problems and solutions
- two_part — two questions (e.g. "Why is this?" + "Is it positive or negative?")

For two_part: "positive or negative development" accepts a clear one-sided answer.
Return: essay_type, requires_opinion, prompt_parts, structure_guidance, reasoning."""
