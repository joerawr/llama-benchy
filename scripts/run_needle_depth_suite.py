#!/usr/bin/env python3
import argparse
import json
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
DEFAULT_SEED_DIR = "/private/tmp/llama-benchy-haystack-seeds/nuc8"


MODELS: list[dict[str, Any]] = [
    {
        "label": "gemma4-26b-a4b-qat-q4xl",
        "name": "Gemma 26B QAT Q4_K_XL",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-qat-GGUF/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
        "served": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    },
    {
        "label": "gemma4-26b-a4b",
        "name": "Gemma 26B Q4_K_S",
        "path": "/Users/jrogers/models/gemma4/unsloth/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_S.gguf",
        "served": "gemma-4-26B-A4B-it-UD-Q4_K_S.gguf",
    },
    {
        "label": "qwen-apex-mtp-balanced",
        "name": "Qwen APEX-MTP Balanced",
        "path": "/Users/jrogers/models/mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "served": "Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Balanced.gguf",
        "server_args": ["--spec-type", "draft-mtp"],
    },
]


class ServerLog:
    def __init__(self, label: str) -> None:
        self.label = label

    def add(self, line: str) -> None:
        lower = line.lower()
        if any(
            marker in lower
            for marker in [
                "projected to use",
                "will leave",
                "file type",
                "file size",
                "model type",
                "server is listening",
                "chat template",
                "error",
            ]
        ):
            print(f"[{self.label} server] {line}", end="", flush=True)


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


def run_one_model(model: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    label = model["label"]
    model_path = Path(model["path"])
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    server_cmd = [
        "llama-server",
        "-m",
        str(model_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "-c",
        str(args.server_ctx),
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
    thread = threading.Thread(target=stream_output, args=(proc, ServerLog(label)), daemon=True)
    thread.start()

    out_path = Path(args.out_dir) / f"needle-depth-{label}.json"
    try:
        wait_for_server(proc)
        print(f"=== {label}: server ready ===", flush=True)
        cmd = [
            sys.executable,
            "scripts/needle_depth_sweep.py",
            "--base-url",
            API_URL,
            "--model",
            model["served"],
            "--label",
            label,
            "--seed-dir",
            args.seed_dir,
            "--difficulty",
            args.difficulty,
            "--runs",
            str(args.runs),
            "--out",
            str(out_path),
            "--timeout",
            str(args.timeout),
            "--max-tokens",
            str(args.max_tokens),
        ]
        if args.adaptive:
            cmd.append("--adaptive")
        cmd.append("--ctx")
        cmd.extend(str(value) for value in args.ctx)
        cmd.append("--depth")
        cmd.extend(str(value) for value in args.depth)
        print(f"$ {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, env=env)
        report = json.loads(out_path.read_text(encoding="utf-8"))
        return {
            "label": label,
            "name": model["name"],
            "path": str(model_path),
            "served": model["served"],
            "result_file": str(out_path),
            "summary": report.get("summary", []),
            "skipped_contexts": report.get("skipped_contexts", []),
        }
    finally:
        print(f"=== {label}: stopping server ===", flush=True)
        stop_server(proc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", choices=[model["label"] for model in MODELS])
    parser.add_argument("--seed-dir", default=DEFAULT_SEED_DIR)
    parser.add_argument("--ctx", nargs="+", type=int, default=[32768, 16384, 8192])
    parser.add_argument("--depth", nargs="+", type=float, default=[0.1, 0.5, 0.9])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--difficulty", choices=["single", "multi", "decoy", "reasoning"], default="decoy")
    parser.add_argument("--adaptive", action="store_true")
    parser.add_argument("--server-ctx", type=int, default=65536)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--out", default="results/needle-depth-suite.json")
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args()

    selected = MODELS
    if args.only:
        selected = [model for model in MODELS if model["label"] in args.only]

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    reports = [run_one_model(model, args, env) for model in selected]
    suite = {
        "seed_dir": args.seed_dir,
        "ctx": args.ctx,
        "depth": args.depth,
        "runs": args.runs,
        "difficulty": args.difficulty,
        "adaptive": args.adaptive,
        "models": reports,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
