"""Tests for the LangGraph evaluation pipeline."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from eval_chain.graph import build_evaluation_graph, get_evaluation_graph, run_evaluation_chain
from eval_chain.schemas import Task2Classification
from eval_chain.types import Task2EssayType
from eval_chain.utils import (
    CriterionScores,
    WritingEvaluationAnalysis,
    WritingRewriteResult,
)


class TestEvalChainGraph(unittest.TestCase):
    def test_build_evaluation_graph_defined(self):
        graph = build_evaluation_graph()
        self.assertIsNotNone(graph)

    def test_get_evaluation_graph_singleton(self):
        g1 = get_evaluation_graph()
        g2 = get_evaluation_graph()
        self.assertIs(g1, g2)

    @patch("eval_chain.graph._make_client")
    def test_run_evaluation_chain_task2(self, mock_make_client):
        classification = Task2Classification(
            essay_type=Task2EssayType.OPINION,
            requires_opinion=True,
            prompt_parts=["To what extent do you agree?"],
            structure_guidance="Intro + 2 body + conclusion",
            reasoning="Agree/disagree prompt",
        )
        analysis = WritingEvaluationAnalysis(
            band_score=6.5,
            criterion_scores=CriterionScores(
                task=6.5,
                coherence_cohesion=6.0,
                lexical_resource=6.0,
                grammatical_range=6.0,
            ),
            overall_feedback=[
                "Clear position stated in the introduction.",
                "Both parts of the question are addressed.",
                "Some grammar errors but meaning is clear.",
            ],
            mistakes=[],
            areas_for_improvement=["Use more varied vocabulary", "Add stronger examples"],
        )
        rewrite = WritingRewriteResult(
            rewritten_essay="This is a complete improved essay with a conclusion."
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [classification, analysis, rewrite]
        mock_make_client.return_value = mock_client

        result = run_evaluation_chain(
            api_key="test-key",
            task_type="task2",
            question_title="Technology",
            question_prompt="To what extent do you agree that technology improves life?",
            essay="I believe technology helps people in many ways.",
            word_count=50,
        )

        self.assertEqual(result.band_score, 6.0)  # recomputed from criterion average
        self.assertEqual(result.question_subtype, "Opinion (Agree/Disagree)")
        self.assertIn("improved essay", result.rewritten_essay)
        self.assertEqual(mock_client.chat.completions.create.call_count, 3)


if __name__ == "__main__":
    unittest.main()
