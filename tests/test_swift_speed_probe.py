import struct
import tempfile
import unittest
from pathlib import Path

from scripts.gguf_metadata import read_field
from scripts.run_swift_speed_probe import aggregate, server_command


class SwiftSpeedProbeTest(unittest.TestCase):
    def test_metal_command_does_not_require_linux_device(self):
        command = server_command("/native/llama-server", "/models/swift.gguf", "swift", "/tmp/template")
        self.assertNotIn("--device", command)
        self.assertNotIn("Vulkan0", command)
        self.assertEqual(command[command.index("-ngl") + 1], "99")
        self.assertEqual(command[command.index("--reasoning-effort") + 1], "xhigh")
        vulkan = server_command("server", "model", "swift", "template", "Vulkan0")
        self.assertEqual(vulkan[vulkan.index("--device") + 1], "Vulkan0")

    def test_throughput_uses_total_tokens_over_total_time(self):
        result = aggregate([
            {"timings": {"predicted_n": 100, "predicted_ms": 1000}, "finish_reason": "stop"},
            {"timings": {"predicted_n": 100, "predicted_ms": 3000}, "finish_reason": "probe_window_elapsed"},
        ])
        self.assertEqual(result["generation_tokens_per_s"], 50)
        self.assertEqual(result["completed_answers"], 1)

    def test_extract_template_past_vocab_without_reading_tensor_payload(self):
        def string(value):
            data = value.encode()
            return struct.pack("<Q", len(data)) + data
        metadata = (string("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2) + string("one") + string("two")
                    + string("tokenizer.chat_template") + struct.pack("<I", 8) + string("template"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.gguf"
            path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 2) + metadata)
            self.assertEqual(read_field(path, "tokenizer.chat_template"), "template")
            with self.assertRaises(KeyError):
                read_field(path, "missing")


if __name__ == "__main__":
    unittest.main()
