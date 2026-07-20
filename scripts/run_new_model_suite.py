#!/usr/bin/env python3
import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests


PORT = 18081
BASE_URL = f"http://127.0.0.1:{PORT}"
API_URL = f"{BASE_URL}/v1"

NEEDLE = "/Users/jrogers/rcave/OBnotes/ZEN30 Double Switch VER. 1.05 Advanced Settings.md"
COMPRESSION_NOTE = (
    "/Users/jrogers/rcave/OBnotes/"
    "AI Frontier Access Risk - Fable GPT-5.6 GLM-5.2 Sovereign AI - 2026-06-26.md"
)

MODELS: list[dict[str, Any]] = [
    {
        "label": "gemma4-26b-a4b-q6xl",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q6_K_XL.gguf",
        "served": "gemma-4-26B-A4B-it-UD-Q6_K_XL.gguf",
    },
    {
        "label": "qwen-apex-mtp-balanced",
        "path": "/Users/jrogers/models/mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "served": "Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "server_args": ["--spec-type", "draft-mtp"],
    },
    {
        "label": "qwen-apex-mtp-quality",
        "path": "/Users/jrogers/models/mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Quality.gguf",
        "served": "Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Quality.gguf",
        "server_args": ["--spec-type", "draft-mtp"],
    },
    {
        "label": "gemma4-26b-a4b-qat-q4xl",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-qat-GGUF/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
        "served": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    },
    {
        "label": "gemma4-12b-qat-q4xl",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-12b-it-qat-GGUF/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
        "served": "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
    },
    {
        "label": "qwen35-9b-q4km",
        "path": "/Users/jrogers/models/lmstudio-community/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q4_K_M.gguf",
        "served": "Qwen3.5-9B-Q4_K_M.gguf",
    },
    {
        "label": "qwythos-9b-q6k",
        "path": "/Users/jrogers/models/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF/Qwythos-9B-Claude-Mythos-5-1M-Q6_K.gguf",
        "served": "Qwythos-9B-Claude-Mythos-5-1M-Q6_K.gguf",
    },
    {
        "label": "qwopus36-35b-mxfp8-mlx",
        "path": "/Users/jrogers/models/Shiftedx/qwopus3.6-35b-a3b-coder-mxfp8-vision-mlx",
        "served": "/Users/jrogers/models/Shiftedx/qwopus3.6-35b-a3b-coder-mxfp8-vision-mlx",
        "backend": "mlx",
        "server_args": [
            "--temp",
            "0",
            "--max-tokens",
            "4096",
            "--chat-template-args",
            '{"enable_thinking": false}',
        ],
    },
]


def stream_output(proc: subprocess.Popen[str], label: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        if any(
            marker in line
            for marker in [
                "main: server is listening",
                "common_memory_breakdown_print",
                "print_info: file type",
                "print_info: file size",
                "print_info: model type",
                "srv          init: init: chat template",
                "prompt eval time",
                "eval time",
                "total time",
                "error",
                "Error",
            ]
        ):
            print(f"[{label} server] {line}", end="", flush=True)


def wait_for_server(proc: subprocess.Popen[str], timeout_s: int = 900) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited early with code {proc.returncode}")
        try:
            response = requests.get(f"{API_URL}/models", timeout=2)
            if response.ok:
                return
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(f"server did not become ready: {last_error}")


def stop_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def run_command(cmd: list[str], env: dict[str, str]) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, env=env)


def run_suite_for_model(model: dict[str, Any], env: dict[str, str]) -> None:
    label = model["label"]
    path = model["path"]
    served = model["served"]
    if not Path(path).exists():
        raise FileNotFoundError(path)

    backend = model.get("backend", "llama")
    if backend == "mlx":
        server_cmd = [
            "mlx_lm.server",
            "--model",
            path,
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ]
    else:
        server_cmd = [
            "llama-server",
            "-m",
            path,
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "-c",
            "65536",
            "-np",
            "1",
            "-ngl",
            "99",
            "--reasoning",
            "off",
            "--reasoning-budget",
            "0",
        ]
    server_cmd.extend(model.get("server_args", []))

    print(f"\n=== {label}: starting server ===", flush=True)
    proc = subprocess.Popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    thread = threading.Thread(target=stream_output, args=(proc, label), daemon=True)
    thread.start()

    try:
        wait_for_server(proc)
        print(f"=== {label}: server ready ===", flush=True)

        run_command(
            [
                sys.executable,
                "-m",
                "llama_benchy",
                "--base-url",
                API_URL,
                "--model",
                served,
                "--pp",
                "256",
                "--tg",
                "32",
                "--depth",
                "0",
                "--runs",
                "1",
                "--latency-mode",
                "none",
                "--no-warmup",
                "--skip-coherence",
                "--no-adapt-prompt",
                "--save-result",
                f"results/{label}-short.json",
                "--format",
                "json",
            ],
            env,
        )

        run_command(
            [
                sys.executable,
                "-m",
                "llama_benchy",
                "--base-url",
                API_URL,
                "--model",
                served,
                "--pp",
                "512",
                "2048",
                "--tg",
                "128",
                "--depth",
                "0",
                "4096",
                "--runs",
                "3",
                "--latency-mode",
                "generation",
                "--no-cache",
                "--save-result",
                f"results/{label}-medium.json",
                "--format",
                "json",
            ],
            env,
        )

        run_command(
            [
                sys.executable,
                "scripts/hackstack_needle.py",
                "--base-url",
                API_URL,
                "--model",
                served,
                "--label",
                label,
                "--needle",
                NEEDLE,
                "--runs",
                "3",
                "--out",
                f"results/hackstack-{label}.json",
            ],
            env,
        )

        run_command(
            [
                sys.executable,
                "scripts/long_file_compression.py",
                "--base-url",
                API_URL,
                "--model",
                served,
                "--label",
                label,
                "--note",
                COMPRESSION_NOTE,
                "--runs",
                "3",
                "--out",
                f"results/long-compression-{label}.json",
            ],
            env,
        )
    finally:
        print(f"=== {label}: stopping server ===", flush=True)
        stop_server(proc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[model["label"] for model in MODELS],
        help="Run only selected labels.",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env["HOME"] = str(Path(".bench-home").resolve())
    env.setdefault("PYTHONUNBUFFERED", "1")

    selected = MODELS
    if args.only:
        selected = [model for model in MODELS if model["label"] in args.only]

    for model in selected:
        run_suite_for_model(model, env)


if __name__ == "__main__":
    main()
