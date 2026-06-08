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


def _fair_scoring_task1() -> str:
    return """SCORING — fair and balanced:
- Minor spelling/grammar that does not block understanding should NOT drag scores below 6.0.
- Clear overview + all main stages/points + logical order with minor slips = 6.0–6.5+ overall."""


def _fair_scoring_task2() -> str:
    return """SCORING — fair and balanced:
- Minor spelling/grammar that does not block understanding should NOT drag scores below 6.0.
- Clear position, all prompt parts answered, logical essay structure with minor slips = 6.0–6.5+ overall.
- Score against what THIS essay type actually asks — not a generic template."""


def _criterion_output_block(task_field: str, task_detail: str) -> str:
    return f"""2. {task_field}:
   - summary: one paragraph
{task_detail}

3. coherence_comment:
   - summary: paragraph on organisation, paragraphing, linking
   - corrections_title: "Linking Issues" (if any)
   - corrections: original → corrected (short phrases)

4. lexical_comment:
   - summary: paragraph on vocabulary
   - corrections_title: "Misspelling" or "Vocabulary"
   - corrections: original → corrected

5. grammar_comment:
   - summary: paragraph on grammar range and accuracy
   - corrections_title: "Grammatical Errors"
   - corrections: original → corrected (short phrases)

6. overall_review: one balanced paragraph

corrections (top-level): leave empty [] — all fixes go inside criterion sections."""


def _output_format_task1() -> str:
    task_detail = """   - sentence_comments: comment on EACH sentence in the report
     • status: accurately_hit | slightly_off | off_key
     • sentence: exact quote
     • comment: brief note (mention specific errors in parentheses when relevant)"""
    return f"""OUTPUT structure:

1. criterion_scores + band_score (average of four, rounded to 0.5)

{_criterion_output_block("task_comment (Task Achievement)", task_detail)}"""


def _output_format_task2() -> str:
    task_detail = """   - sentence_comments: one entry per paragraph (introduction, each body paragraph, conclusion)
     • label: "Introduction" | "Body paragraph 1" | "Body paragraph 2" | "Conclusion" etc.
     • status: accurately_hit | slightly_off | off_key
     • sentence: opening or key sentence from that paragraph
     • comment: does it answer the prompt? Is the argument clear and developed?"""
    return f"""OUTPUT structure:

1. criterion_scores + band_score

{_criterion_output_block("task_comment (Task Response)", task_detail)}"""


def analysis_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    return f"""You are an IELTS Writing Task 1 examiner (jumpinto.com style).

Visual type: {type_label}

{_fair_scoring_task1()}

{_output_format_task1()}

Do NOT rewrite. Be encouraging but honest."""


def analysis_system_prompt_task2(classification: Task2Classification) -> str:
    type_label = TASK2_TYPE_LABELS[classification.essay_type]
    fairness = ""
    if classification.essay_type == Task2EssayType.TWO_PART:
        fairness = (
            "Two-part question: both parts must be answered. A clear one-sided opinion on "
            "'positive or negative' is valid — do NOT require a separate disadvantages paragraph."
        )
    elif classification.essay_type == Task2EssayType.OPINION:
        fairness = "Opinion essay: clear stance required. Brief concessions are fine."

    return f"""You are an IELTS Writing Task 2 examiner (jumpinto.com style).

Essay type: {type_label}
{fairness}

{_fair_scoring_task2()}

{_output_format_task2()}

Do NOT rewrite. Be encouraging but honest."""


def rewrite_system_prompt_task1(classification: Task1Classification) -> str:
    type_label = TASK1_TYPE_LABELS[classification.visual_type]
    return f"""Write an optimized Band 7+ IELTS Task 1 **{type_label}** report.

4 paragraphs: introduction → overview → body 1 → body 2. No conclusion. 150–180 words.
Use accurate chart data. Plain text only — no markup."""


def rewrite_system_prompt_task2(classification: Task2Classification) -> str:
    return f"""Write an optimized Band 7+ IELTS Task 2 **{TASK2_TYPE_LABELS[classification.essay_type]}** essay.

Preserve the student's reasonable argument. Introduction → body paragraphs → conclusion. 280+ words.
Plain text only — no markup."""


def classification_system_prompt_task1() -> str:
    return """Classify Task 1 visual type. Return visual_type, is_dynamic, time_period, key_data_needed, tense_guidance, reasoning."""


def classification_system_prompt_task2() -> str:
    return """Classify Task 2 essay type. Return essay_type, requires_opinion, prompt_parts, structure_guidance, reasoning."""
