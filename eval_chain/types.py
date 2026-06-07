"""Question subtype enums for Task 1 visuals and Task 2 essays."""
from __future__ import annotations

from enum import Enum


class Task1VisualType(str, Enum):
    LINE_GRAPH = "line_graph"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    TABLE = "table"
    MAP = "map"
    PROCESS_DIAGRAM = "process_diagram"
    MIXED_CHARTS = "mixed_charts"
    MULTIPLE_DIAGRAMS = "multiple_diagrams"


class Task2EssayType(str, Enum):
    OPINION = "opinion"
    DISCUSSION = "discussion"
    ADVANTAGES_DISADVANTAGES = "advantages_disadvantages"
    PROBLEM_SOLUTION = "problem_solution"
    TWO_PART = "two_part"


TASK1_RAG_FILES: dict[Task1VisualType, str] = {
    Task1VisualType.LINE_GRAPH: "line_graph.md",
    Task1VisualType.BAR_CHART: "bar_chart.md",
    Task1VisualType.PIE_CHART: "pie_chart.md",
    Task1VisualType.TABLE: "table.md",
    Task1VisualType.MAP: "map.md",
    Task1VisualType.PROCESS_DIAGRAM: "process_diagram.md",
    Task1VisualType.MIXED_CHARTS: "mixed_charts.md",
    Task1VisualType.MULTIPLE_DIAGRAMS: "multiple_diagrams.md",
}

TASK2_RAG_FILES: dict[Task2EssayType, str] = {
    Task2EssayType.OPINION: "opinion.md",
    Task2EssayType.DISCUSSION: "discussion.md",
    Task2EssayType.ADVANTAGES_DISADVANTAGES: "advantages_disadvantages.md",
    Task2EssayType.PROBLEM_SOLUTION: "problem_solution.md",
    Task2EssayType.TWO_PART: "two_part.md",
}

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
