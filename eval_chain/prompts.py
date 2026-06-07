"""Jumpinto-style evaluation prompts — fair, per-criterion, constructive."""
from __future__ import annotations

from eval_chain.schemas import Task1Classification, Task2Classification
from eval_chain.types import Task1VisualType, Task2EssayType

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
    Task2EssayType.OPINION: "Opinion",
    Task2EssayType.DISCUSSION: "Discussion",
    Task2EssayType.ADVANTAGES_DISADVANTAGES: "Advantages & Disadvantages",
    Task2EssayType.PROBLEM_SOLUTION: "Problem / Solution",
    Task2EssayType.TWO_PART: "Two-Part Question",
}


def _fair_scoring_rules() -> str:
    return """SCORING — be fair and balanced like a professional IELTS tutor:
- Score what the student DID well, not only errors.
- Minor spelling/grammar errors that do not block understanding should NOT drag scores below 6.0.
- A clear overview, logical structure, and all main points covered with minor language slips = 6.0–6.5+ overall.
- Only drop below 6.0 when key requirements are genuinely missing or meaning is often unclear."""


def _output_format_task1() -> str:
    return """OUTPUT — provide feedback in this exact structure:

1. criterion_scores + band_score (average of four, rounded to 0.5)

2. task_comment (Task Achievement):
   - summary: one paragraph on how well requirements are met
   - sentence_comments: comment on EACH sentence from the student's report
     • status: accurately_hit | slightly_off | off_key
     • sentence: exact quote
     • comment: brief constructive note (mention specific errors in parentheses when relevant)

3. coherence_comment:
   - summary: paragraph on organisation, paragraphing, linking words
   - corrections_title: "Linking Issues" (if any)
   - corrections: original → corrected pairs for linking/wording issues

4. lexical_comment:
   - summary: paragraph on vocabulary range and accuracy
   - corrections_title: "Misspelling" or "Vocabulary"
   - corrections: original → corrected for spelling/word errors

5. grammar_comment:
   - summary: paragraph on grammar range and accuracy
   - corrections_title: "Grammatical Errors"
   - corrections: original → corrected (short phrases only)

6. overall_review: one balanced paragraph (strengths + weaknesses + impression)

corrections: leave empty for Task 1."""


def _output_format_task2() -> str:
    return """OUTPUT — provide feedback in this exact structure:

1. criterion_scores + band_score

2. corrections: top spelling/grammar/word fixes as original → corrected (shown first in UI)

3. task_comment, coherence_comment, lexical_comment, grammar_comment:
   Each has a summary paragraph. Add corrections subsections where relevant
   (Misspelling, Grammatical Errors, Linking Issues, etc.).

4. overall_review: one balanced summary paragraph

task_comment.sentence_comments: leave empty for Task 2."""


def analysis_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    return f"""You are an IELTS Writing Task 1 examiner giving feedback like jumpinto.com.

Visual type: {type_label}
{classification.reasoning}

{_fair_scoring_rules()}

{_output_format_task1()}

Do NOT rewrite the report. Be encouraging but honest."""


def analysis_system_prompt_task2(classification: Task2Classification) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    fairness = ""
    if classification.essay_type == Task2EssayType.TWO_PART:
        fairness = (
            "This is a two-part question. A clear one-sided opinion on 'positive or negative' is valid — "
            "do NOT penalise for missing a disadvantages paragraph."
        )
    elif classification.essay_type == Task2EssayType.OPINION:
        fairness = "Opinion essays need a clear stance. Brief concessions are fine — equal both-sides coverage is NOT required."

    return f"""You are an IELTS Writing Task 2 examiner giving feedback like jumpinto.com.

Essay type: {type_label}
{fairness}

{_fair_scoring_rules()}

{_output_format_task2()}

Do NOT rewrite the essay. Be encouraging but honest."""


def rewrite_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    return f"""Write an optimized Band 7+ IELTS Task 1 **{type_label}** report.

4 paragraphs: introduction → overview → body 1 → body 2. No conclusion. 150–180 words.
Use accurate data from the chart. Plain text only — NO highlights, NO markup, NO <<>> brackets."""


def rewrite_system_prompt_task2(classification: Task2Classification) -> str:
    return f"""Write an optimized Band 7+ IELTS Task 2 **{TASK2_TYPE_LABELS[classification.essay_type]}** essay.

Preserve the student's reasonable argument. Introduction → body paragraphs → conclusion. 280+ words.
Plain text only — NO highlights, NO markup, NO <<>> brackets."""


def classification_system_prompt_task1() -> str:
    return """Classify the Task 1 visual: line_graph, bar_chart, pie_chart, table, map, process_diagram, mixed_charts, or multiple_diagrams.
Return visual_type, is_dynamic, time_period, key_data_needed, tense_guidance, reasoning."""


def classification_system_prompt_task2() -> str:
    return """Classify Task 2 prompt: opinion, discussion, advantages_disadvantages, problem_solution, or two_part.
Return essay_type, requires_opinion, prompt_parts, structure_guidance, reasoning."""
