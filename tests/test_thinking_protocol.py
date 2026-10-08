import unittest

from scripts import run_ornith_thinking_suite as ornith
from scripts import run_qwen_sampling_comparison as qwen
from grader.task_context import load_task_contexts


class ThinkingProtocolTest(unittest.TestCase):
    def test_thinking_directive_change_has_separate_protocol(self):
        baseline = load_task_contexts()
        for runner in [ornith, qwen]:
            self.assertEqual(runner.EXPERIMENT_SUITE_VERSION, "llama-benchy-thinking-comparison@1.0")
            for task_id, prompt, _ in runner.tasks():
                expected = baseline[task_id].prompt
                if task_id == "long_file_compression":
                    expected = expected.removeprefix("/no_think\n\n")
                self.assertEqual(prompt, expected)

    def test_experiment_paths_use_configurable_model_root(self):
        self.assertTrue(qwen.MODEL.is_relative_to(qwen.MODEL_ROOT))
        for config in ornith.MODELS.values():
            self.assertTrue(config["path"].is_relative_to(ornith.MODEL_ROOT))
