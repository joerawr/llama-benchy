import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.openrouter_benchmark_campaign import (
    CONFIGS,
    MAX_TOKENS,
    _env_value,
    openrouter_api_key,
    usage_summary,
)


class OpenRouterCampaignTest(unittest.TestCase):
    def test_requested_effort_matrix_is_explicit(self):
        self.assertEqual(
            [(model, effort) for model, _, effort in CONFIGS],
            [
                ("glm-5.2", "high"),
                ("glm-5.2", "xhigh"),
                ("kimi-k3", "low"),
                ("kimi-k3", "high"),
                ("kimi-k3", "max"),
                ("mercury-2", None),
            ],
        )

    def test_env_value_removes_matching_quotes(self):
        self.assertEqual(_env_value('"secret"'), "secret")
        self.assertEqual(_env_value("'secret'"), "secret")

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "from-process"}, clear=False)
    def test_process_environment_wins(self):
        self.assertEqual(openrouter_api_key(), "from-process")

    def test_usage_summary_extracts_reasoning_and_rate(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(
                model_dump=lambda: {
                    "prompt_tokens": 100,
                    "completion_tokens": 40,
                    "total_tokens": 140,
                    "cost": 0.12,
                    "completion_tokens_details": {"reasoning_tokens": 30},
                }
            )
        )
        usage = usage_summary(response, 4.0)
        self.assertEqual(usage["reasoning_output_tokens"], 30)
        self.assertEqual(usage["effective_output_tokens_per_s"], 10.0)
        self.assertEqual(usage["cost_usd"], 0.12)

    def test_default_has_no_harness_completion_cap(self):
        self.assertIsNone(MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
