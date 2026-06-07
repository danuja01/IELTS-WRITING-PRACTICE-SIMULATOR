"""Type-specific RAG retrieval for Task 1 and Task 2."""
from __future__ import annotations

from pathlib import Path

from eval_chain.types import (
    TASK1_RAG_FILES,
    TASK2_RAG_FILES,
    Task1VisualType,
    Task2EssayType,
)

RAG_ROOT = Path(__file__).resolve().parent.parent / "ielts_rag"


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def retrieve_task1_context(visual_type: Task1VisualType) -> str:
    """Load shared Task 1 criteria plus the visual-type-specific guide."""
    chunks = [
        _read(RAG_ROOT / "common" / "scoring_matrix.md"),
        _read(RAG_ROOT / "common" / "task1_shared.md"),
        _read(RAG_ROOT / "task1" / TASK1_RAG_FILES[visual_type]),
    ]
    return "\n\n---\n\n".join(c for c in chunks if c)


def retrieve_task2_context(essay_type: Task2EssayType) -> str:
    """Load shared Task 2 criteria plus the essay-type-specific guide."""
    chunks = [
        _read(RAG_ROOT / "common" / "scoring_matrix.md"),
        _read(RAG_ROOT / "common" / "task2_shared.md"),
        _read(RAG_ROOT / "task2" / TASK2_RAG_FILES[essay_type]),
    ]
    return "\n\n---\n\n".join(c for c in chunks if c)
