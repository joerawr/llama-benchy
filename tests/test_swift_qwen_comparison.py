import json
import unittest
from unittest.mock import patch

from scripts.run_swift_qwen_comparison import MODELS, needs_third, summarize, tasks_for_experiment


class SwiftQwenComparisonTest(unittest.TestCase):
    def record(self, score=10, failures=None, check=True):
        return {"label": next(iter(MODELS)), "task": "finance", "elapsed_s": 1,
                "semantic_grade": {"score": score, "substantive_failures": failures or []},
                "diagnostic_grade": {"checks": [{"id": "metric", "pass": check}]}}

    def test_thinking_prompts_are_frozen_and_do_not_disable_thinking(self):
        tasks = tasks_for_experiment()
        self.assertEqual(set(tasks), {"finance", "compression"})
        self.assertFalse(tasks["compression"].prompt.startswith("/no_think"))
        self.assertEqual(len(tasks["compression"].grader("")["checks"]), 12)

    def test_same_score_with_different_failed_checks_needs_third(self):
        self.assertTrue(needs_third([self.record(failures=["a"]), self.record(failures=["b"])]))
        self.assertTrue(needs_third([self.record(), self.record(check=False)]))
        self.assertFalse(needs_third([self.record(), self.record()]))

    def test_missing_score_needs_third_and_keeps_aggregate_missing(self):
        rows = [self.record(), self.record(score=None)]
        self.assertTrue(needs_third(rows))
        result = summarize({str(n): r for n, r in enumerate(rows)}, ["finance"])
        self.assertIsNone(result[next(iter(MODELS))]["score_out_of_24"])

    def test_source_changes_cannot_silently_enter_same_experiment(self):
        from dataclasses import replace
        tasks = tasks_for_experiment()
        tasks["finance"] = replace(tasks["finance"], prompt="changed prompt")
        with patch("scripts.run_swift_qwen_comparison.build_tasks", return_value=tasks):
            with self.assertRaisesRegex(ValueError, "Source prompt changed"):
                tasks_for_experiment()

    def test_dropped_stream_keeps_partial_evidence_and_missing_finish(self):
        import tempfile
        from pathlib import Path
        from scripts.run_swift_qwen_comparison import request_stream
        event = {"choices": [{"delta": {"reasoning_content": "partial reasoning"}}]}
        with tempfile.TemporaryDirectory() as directory, patch("scripts.run_swift_qwen_comparison.requests.post") as post, patch("scripts.run_swift_qwen_comparison.api", return_value={"tokens": [1]}):
            response = post.return_value.__enter__.return_value
            response.iter_lines.return_value = [b"data: " + json.dumps(event).encode()]
            path = Path(directory) / "trace.sse"
            result = request_stream({}, path, 10)
            self.assertEqual(result["reasoning"], "partial reasoning")
            self.assertEqual(result["finish_reason"], "error")
            self.assertIn("without a finish reason", result["error"])
            self.assertIn("partial reasoning", path.read_text())


if __name__ == "__main__":
    unittest.main()
