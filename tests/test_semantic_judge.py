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
                "item": {"type": "agent_message", "text": '{"score": 2, "max_score": 2}'},
            }),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}}),
        ])
        completed = subprocess.CompletedProcess([], 0, output, "")
        with patch("grader.semantic_judge.subprocess.run", return_value=completed):
            grade, meta = judge_answer(
                "answer", {"checks": [{"id": "one", "description": "one"}]}, "task"
            )

        self.assertEqual(grade["score"], 2)
        self.assertEqual(meta["usage"]["output_tokens"], 3)

    def test_does_not_fallback_when_judge_fails(self):
        completed = subprocess.CompletedProcess([], 1, "", "judge failed")
        with patch("grader.semantic_judge.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "judge failed"):
                judge_answer("answer", {"checks": []}, "task")


if __name__ == "__main__":
    unittest.main()
