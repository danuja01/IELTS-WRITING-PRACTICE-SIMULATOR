"""Tests for the LangGraph evaluation pipeline."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from eval_chain.graph import build_evaluation_graph, get_evaluation_graph, run_evaluation_chain
from eval_chain.schemas import Task2Classification
from eval_chain.types import Task2EssayType
from eval_chain.utils import (
    CorrectionItem,
    CriterionComment,
    CriterionScores,
    SentenceComment,
    WritingEvaluationAnalysis,
    WritingRewriteResult,
)


def _sample_analysis() -> WritingEvaluationAnalysis:
    return WritingEvaluationAnalysis(
        band_score=6.5,
        criterion_scores=CriterionScores(
            task=6.5,
            coherence_cohesion=6.5,
            lexical_resource=6.0,
            grammatical_range=6.0,
        ),
        task_comment=CriterionComment(
            summary="The response covers all main stages with a clear overview.",
            sentence_comments=[
                SentenceComment(
                    status="accurately_hit",
                    sentence="Overall, the process has seven stages.",
                    comment="Clear overview of the process.",
                )
            ],
        ),
        coherence_comment=CriterionComment(
            summary="Logical chronological order with good linking words.",
            corrections_title="Linking Issues",
            corrections=[],
        ),
        lexical_comment=CriterionComment(
            summary="Good task vocabulary with minor spelling slips.",
            corrections_title="Misspelling",
            corrections=[CorrectionItem(original="suger", corrected="sugar")],
        ),
        grammar_comment=CriterionComment(
            summary="Mostly clear sentences with some tense slips.",
            corrections_title="Grammatical Errors",
            corrections=[CorrectionItem(original="were harvested", corrected="are harvested")],
        ),
        corrections=[CorrectionItem(original="begining", corrected="beginning")],
        overall_review="A solid report that meets Task 1 requirements with minor language errors.",
    )


class TestEvalChainGraph(unittest.TestCase):
    def test_build_evaluation_graph_defined(self):
        self.assertIsNotNone(build_evaluation_graph())

    def test_get_evaluation_graph_singleton(self):
        self.assertIs(get_evaluation_graph(), get_evaluation_graph())

    @patch("eval_chain.graph._make_client")
    def test_run_evaluation_chain_task2(self, mock_make_client):
        classification = Task2Classification(
            essay_type=Task2EssayType.OPINION,
            requires_opinion=True,
            prompt_parts=["To what extent do you agree?"],
            structure_guidance="Intro + 2 body + conclusion",
            reasoning="Agree/disagree prompt",
        )
        analysis = _sample_analysis()
        rewrite = WritingRewriteResult(
            rewritten_essay="This is the optimized composition with a proper conclusion."
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [classification, analysis, rewrite]
        mock_make_client.return_value = mock_client

        result = run_evaluation_chain(
            api_key="test-key",
            task_type="task2",
            question_title="Technology",
            question_prompt="To what extent do you agree?",
            essay="I believe technology helps people.",
            word_count=50,
        )

        self.assertEqual(result.band_score, 6.5)
        self.assertEqual(result.format_version, 2)
        self.assertEqual(result.question_subtype, "Opinion")
        self.assertIn("optimized composition", result.rewritten_essay)
        self.assertEqual(len(result.corrections), 1)
        self.assertTrue(result.task_comment.summary)


if __name__ == "__main__":
    unittest.main()
