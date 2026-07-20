#!/usr/bin/env python3
import argparse
import json
import os
import re
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

MODELS: list[dict[str, Any]] = [
    {
        "label": "ornith",
        "name": "Ornith Q8_0",
        "path": "/Users/jrogers/models/deepreinforce-ai/ornith-1.0-35b/ornith-1.0-35b-Q8_0.gguf",
        "served": "ornith-1.0-35b-Q8_0.gguf",
    },
    {
        "label": "qwen-apex",
        "name": "Qwen APEX Balanced",
        "path": "/Users/jrogers/models/mudler/qwen36-apex/Qwen3.6-35B-A3B-APEX-I-Balanced.gguf",
        "served": "Qwen3.6-35B-A3B-APEX-I-Balanced.gguf",
    },
    {
        "label": "gemma4-26b-a4b",
        "name": "Gemma Q4_K_S",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_S.gguf",
        "served": "gemma-4-26B-A4B-it-UD-Q4_K_S.gguf",
    },
    {
        "label": "gemma4-26b-a4b-q6xl",
        "name": "Gemma Q6_K_XL",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q6_K_XL.gguf",
        "served": "gemma-4-26B-A4B-it-UD-Q6_K_XL.gguf",
    },
    {
        "label": "qwen-apex-mtp-balanced",
        "name": "Qwen APEX-MTP Balanced",
        "path": "/Users/jrogers/models/mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "served": "Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "server_args": ["--spec-type", "draft-mtp"],
    },
    {
        "label": "qwen-apex-mtp-quality",
        "name": "Qwen APEX-MTP Quality",
        "path": "/Users/jrogers/models/mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Quality.gguf",
        "served": "Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Quality.gguf",
        "server_args": ["--spec-type", "draft-mtp"],
    },
    {
        "label": "gemma4-26b-a4b-qat-q4xl",
        "name": "Gemma QAT Q4_K_XL",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-qat-GGUF/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
        "served": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    },
    {
        "label": "gemma4-12b-qat-q4xl",
        "name": "Gemma 12B QAT Q4_K_XL",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-12b-it-qat-GGUF/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
        "served": "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
    },
    {
        "label": "qwen35-9b-q4km",
        "name": "Qwen3.5 9B Q4_K_M",
        "path": "/Users/jrogers/models/lmstudio-community/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q4_K_M.gguf",
        "served": "Qwen3.5-9B-Q4_K_M.gguf",
    },
    {
        "label": "qwythos-9b-q6k",
        "name": "Qwythos 9B Q6_K",
        "path": "/Users/jrogers/models/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF/Qwythos-9B-Claude-Mythos-5-1M-Q6_K.gguf",
        "served": "Qwythos-9B-Claude-Mythos-5-1M-Q6_K.gguf",
    },
    {
        "label": "qwopus36-35b-mxfp8-mlx",
        "name": "Qwopus3.6 35B A3B MXFP8 MLX",
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


class ServerLog:
    def __init__(self, label: str) -> None:
        self.label = label
        self.lines: list[str] = []
        self.lock = threading.Lock()

    def add(self, line: str) -> None:
        with self.lock:
            self.lines.append(line.rstrip("\n"))
        lower = line.lower()
        if any(
            marker in lower
            for marker in [
                "memory breakdown",
                "projected to use",
                "will leave",
                "file type",
                "file size",
                "model type",
                "server is listening",
                "chat template, thinking",
                "error",
            ]
        ):
            print(f"[{self.label} server] {line}", end="", flush=True)

    def snapshot(self) -> list[str]:
        with self.lock:
            return list(self.lines)


def stream_output(proc: subprocess.Popen[str], log: ServerLog) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        log.add(line)


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


def parse_memory(lines: list[str]) -> dict[str, Any]:
    joined = "\n".join(lines)
    memory: dict[str, Any] = {}

    projected = re.search(r"projected to use\s+(\d+)\s+MiB", joined, re.IGNORECASE)
    if projected:
        memory["projected_mib"] = int(projected.group(1))

    will_leave = re.search(r"will leave\s+(\d+)\s+>=\s+\d+\s+MiB", joined, re.IGNORECASE)
    if will_leave:
        memory["projected_free_mib"] = int(will_leave.group(1))

    file_size = re.search(r"file size\s*=\s*([0-9.]+)\s+GiB", joined, re.IGNORECASE)
    if file_size:
        memory["file_size_gib"] = float(file_size.group(1))

    file_type = re.search(r"file type\s*=\s*([^\n]+)", joined, re.IGNORECASE)
    if file_type:
        memory["file_type"] = file_type.group(1).strip()

    # Newer llama.cpp logs still include memory rows, but with timestamps. Capture the MTL0 line.
    mtl_rows = [line for line in lines if "MTL0" in line and "MiB" not in line and "memory breakdown" not in line]
    for line in mtl_rows:
        match = re.search(
            r"MTL0.*?\|\s*(\d+)\s*=\s*(\d+)\s*\+\s*\((\d+)\s*=\s*(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)\)",
            line,
        )
        if match:
            memory["mtl_total_mib"] = int(match.group(1))
            memory["mtl_free_mib_at_breakdown"] = int(match.group(2))
            memory["mtl_self_mib"] = int(match.group(3))
            memory["mtl_model_mib"] = int(match.group(4))
            memory["mtl_context_mib"] = int(match.group(5))
            memory["mtl_compute_mib"] = int(match.group(6))

    if "projected_mib" in memory:
        memory["projected_gib"] = round(memory["projected_mib"] / 1024, 2)
    if "projected_free_mib" in memory:
        memory["projected_free_gib"] = round(memory["projected_free_mib"] / 1024, 2)
    if "mtl_self_mib" in memory:
        memory["mtl_self_gib"] = round(memory["mtl_self_mib"] / 1024, 2)

    return memory


def run_one_model(model: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    label = model["label"]
    path = model["path"]
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
            str(args.ctx),
            "-np",
            "1",
            "-ngl",
            "99",
            "--reasoning",
            "off",
            "--reasoning-budget",
            "0",
            "-lv",
            "4",
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
    server_log = ServerLog(label)
    thread = threading.Thread(target=stream_output, args=(proc, server_log), daemon=True)
    thread.start()

    try:
        wait_for_server(proc)
        print(f"=== {label}: server ready ===", flush=True)
        out_path = Path("results") / f"pinchbench-lite-{label}.json"
        cmd = [
            sys.executable,
            "scripts/pinchbench_lite.py",
            "--base-url",
            API_URL,
            "--model",
            model["served"],
            "--label",
            label,
            "--runs",
            str(args.runs),
            "--out",
            str(out_path),
        ]
        for task in args.task:
            cmd.extend(["--task", task])
        print(f"$ {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, env=env)
        task_report = json.loads(out_path.read_text(encoding="utf-8"))
        return {
            "label": label,
            "name": model["name"],
            "path": path,
            "served": model["served"],
            "backend": backend,
            "ctx": args.ctx,
            "memory": parse_memory(server_log.snapshot()),
            "result_file": str(out_path),
            "tasks": task_report["tasks"],
        }
    finally:
        print(f"=== {label}: stopping server ===", flush=True)
        stop_server(proc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--ctx", type=int, default=65536)
    parser.add_argument("--out", default="results/pinchbench-lite-suite.json")
    parser.add_argument(
        "--task",
        action="append",
        choices=[
            "task_csv_finance_report",
            "task_log_apache_error_summary",
            "task_access_log_anomaly",
            "task_csv_iris_outliers",
        ],
        help="Task to run. Repeatable. Defaults to the original two PinchBench-lite tasks.",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        choices=[model["label"] for model in MODELS],
        help="Run only selected labels.",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if not args.task:
        args.task = ["task_csv_finance_report", "task_log_apache_error_summary"]

    selected = MODELS
    if args.only:
        selected = [model for model in MODELS if model["label"] in args.only]

    reports = [run_one_model(model, args, env) for model in selected]
    suite = {
        "runs": args.runs,
        "ctx": args.ctx,
        "models": reports,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
