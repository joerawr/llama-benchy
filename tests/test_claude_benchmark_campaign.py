import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.claude_benchmark_campaign import (
    TASK_NAMES,
    initial_state,
    pause_for_blocker,
    run_campaign,
    authentication_blocker,
    session_limit_blocker,
)


class SessionLimitBlockerTest(unittest.TestCase):
    def test_detects_claude_session_limit_and_reset_time(self):
        body = {
            "subtype": "success",
            "is_error": True,
            "result": (
                "You've hit your session limit \u00b7 "
                "resets 7:30pm (America/Los_Angeles)"
            ),
        }

        self.assertEqual(
            session_limit_blocker(body),
            {
                "type": "claude_session_limit",
                "message": body["result"],
                "resets": "7:30pm (America/Los_Angeles)",
            },
        )

    def test_ignores_normal_success_and_unrelated_errors(self):
        self.assertIsNone(
            session_limit_blocker({"is_error": False, "result": "answer"})
        )
        self.assertIsNone(
            session_limit_blocker({"is_error": True, "result": "unknown model"})
        )
        self.assertEqual(
            authentication_blocker(
                {
                    "is_error": True,
                    "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
                }
            )["type"],
            "claude_authentication",
        )

    @patch("scripts.claude_benchmark_campaign.save_state")
    def test_pauses_for_legacy_record_without_blocker_field(self, save_state):
        state = {"status": "running"}
        record = {
            "grade": {
                "error": "You've hit your session limit \u00b7 resets 7:30pm"
            }
        }

        self.assertTrue(pause_for_blocker(state, record, "model:task:1"))
        self.assertEqual(state["status"], "paused_session_limit")
        self.assertEqual(state["blocker"]["resets"], "7:30pm")
        save_state.assert_called_once_with(state)

    @patch("scripts.claude_benchmark_campaign.print")
    @patch("scripts.claude_benchmark_campaign.save_state")
    @patch("scripts.claude_benchmark_campaign.load_state")
    @patch("scripts.claude_benchmark_campaign.build_tasks")
    @patch("scripts.claude_benchmark_campaign.run_once")
    def test_campaign_prioritizes_one_pass_across_configs(
        self, run_once, build_tasks, load_state, save_state, _print
    ):
        build_tasks.return_value = {
            name: SimpleNamespace(task_id=name) for name in TASK_NAMES
        }
        load_state.return_value = initial_state()
        calls = []

        def fake_run(model, effort, task, run):
            calls.append((model, effort, task.task_id, run))
            return {
                "model": model,
                "effort": effort,
                "task_id": task.task_id,
                "run": run,
                "elapsed_s": 1.0,
                "exit_code": 0,
                "grade": {"score": 1, "max_score": 1, "pass": True},
                "usage": {"output_tokens": 1, "cost_usd": 0},
                "blocker": None,
            }

        run_once.side_effect = fake_run
        args = SimpleNamespace(
            only_config=["opus:low", "opus:medium", "fable:low", "opus:high"],
            retry_failures=True,
            force_three=False,
            passes=2,
        )

        run_campaign(args)

        first_pass_models = [(model, effort) for model, effort, _, run in calls if run == 1]
        self.assertEqual(
            first_pass_models,
            [("opus", "low")] * 7
            + [("opus", "medium")] * 7
            + [("fable", "low")] * 7
            + [("opus", "high")] * 7,
        )
        self.assertEqual(len([call for call in calls if call[3] == 2]), 28)
        self.assertFalse(any(call[3] == 3 for call in calls))


if __name__ == "__main__":
    unittest.main()
