import json
import subprocess
import unittest
from unittest.mock import patch

from grader.semantic_judge import judge_answer


class SemanticJudgeTest(unittest.TestCase):
    def test_returns_semantic_grade_and_usage(self):
        output = "\n".join([
            json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": '{"score": 1, "max_score": 1}'},
            }),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}}),
        ])
        completed = subprocess.CompletedProcess([], 0, output, "")
        with patch("grader.semantic_judge.subprocess.run", return_value=completed) as run:
            grade, meta = judge_answer(
                "answer",
                {"checks": [{"id": "one", "description": "Requires one fact."}]},
                "task",
                task_prompt="Use only this source: source fact.",
            )

        self.assertEqual(grade["score"], 1)
        self.assertEqual(meta["usage"]["output_tokens"], 3)
        self.assertEqual(meta["judge_protocol"], "source-aware-v2")
        self.assertIn('model_reasoning_effort="xhigh"', run.call_args.args[0])
        judge_prompt = run.call_args.kwargs["input"]
        self.assertIn("Use only this source: source fact.", judge_prompt)
        self.assertIn("Requires one fact.", judge_prompt)
        self.assertIn("answer", judge_prompt)

    def test_rejects_wrong_denominator(self):
        output = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"score": 2, "max_score": 2}'}})
        completed = subprocess.CompletedProcess([], 0, output, "")
        with patch("grader.semantic_judge.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "invalid rubric"):
                judge_answer("answer", {"checks": [{"id": "one", "description": "One fact"}]}, "task", task_prompt="source")

    def test_does_not_fallback_when_judge_fails(self):
        completed = subprocess.CompletedProcess([], 1, "", "judge failed")
        with patch("grader.semantic_judge.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "judge failed"):
                judge_answer("answer", {"checks": []}, "task", task_prompt="task source")

    def test_rejects_check_without_explicit_requirement(self):
        with self.assertRaisesRegex(ValueError, "no explicit description"):
            judge_answer(
                "answer",
                {"checks": [{"id": "missing", "detail": "observed"}]},
                "task",
                task_prompt="task source",
            )


if __name__ == "__main__":
    unittest.main()
