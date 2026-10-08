import hashlib
import unittest
from unittest.mock import patch

import requests

from grader.semantic_judge import judge_answer, judge_result
from grader.task_context import resolve_task_context
from scripts.ifeval_lite import TASKS, run_task, summarize, tasks_for_suite


class BenchmarkProtocolTest(unittest.TestCase):
    def test_empty_and_capped_outputs_never_call_paid_judge(self):
        for answer, finish in [("", "stop"), ("partial answer", "length"), ("filtered", "content_filter")]:
            with self.subTest(finish=finish), patch("grader.semantic_judge.subprocess.run") as run:
                grade, meta = judge_answer(answer, {"checks": [{}]}, "task", task_prompt="source", finish_reason=finish)
                self.assertIsNone(grade["score"])
                self.assertEqual(grade["status"], "incomplete")
                run.assert_not_called()

    def test_judge_failure_is_preserved_as_missing_quality(self):
        with patch("grader.semantic_judge.judge_answer", side_effect=RuntimeError("judge unavailable")):
            grade, _ = judge_result("answer", {"checks": [{}]}, "task", task_prompt="source")
        self.assertIsNone(grade["score"])
        self.assertIn("judge unavailable", grade["error"])

    def test_request_timeout_is_retained_without_judging(self):
        with patch("scripts.ifeval_lite.chat_completion", side_effect=requests.Timeout("timed out")), patch("grader.semantic_judge.subprocess.run") as paid:
            record = run_task("http://localhost/v1", "model", "label", TASKS[-1], 1, 1, 10)
        self.assertEqual(record["finish_reason"], "error")
        self.assertIn("timed out", record["error"])
        self.assertIsNone(record["semantic_grade"]["score"])
        paid.assert_not_called()

    def test_incomplete_summary_does_not_average_only_successes(self):
        task = TASKS[-1]
        rows = [{"task_id": task.task_id, "elapsed_s": 1, "semantic_grade": {"score": score, "max_score": 8, "pass": score == 8}} for score in [8, None]]
        summary = summarize(rows)[0]
        self.assertIsNone(summary["score"])
        self.assertIsNone(summary["score_pct"])
        self.assertEqual(summary["runs"], 2)

    def test_variant_changes_only_checklist_and_resolves_saved_source(self):
        original = {task.task_id: task for task in tasks_for_suite("1.1")}
        variant = {task.task_id: task for task in tasks_for_suite("1.2")}
        changed = [key for key in original if original[key].prompt != variant[key].prompt]
        self.assertEqual(changed, ["two_section_backup_checklist"])
        key = changed[0]
        record = {"semantic_judge": {"task_prompt_sha256": hashlib.sha256(variant[key].prompt.encode()).hexdigest()}}
        self.assertEqual(resolve_task_context(key, record).prompt, variant[key].prompt)
        record["semantic_judge"]["task_prompt_sha256"] = "unknown"
        with self.assertRaisesRegex(ValueError, "No versioned task"):
            resolve_task_context(key, record)

    def test_checklist_versions_match_frozen_public_sources(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for version in ["1.1", "1.2"]:
            task = next(task for task in tasks_for_suite(version) if task.task_id == "two_section_backup_checklist")
            self.assertEqual(task.prompt, (root / f"benchmarks/suites/checklist-v{version}.txt").read_text())
