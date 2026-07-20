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

from ifeval_lite import TASKS
from run_pinchbench_lite_suite import MODELS, parse_memory


PORT = 18081
BASE_URL = f"http://127.0.0.1:{PORT}"
API_URL = f"{BASE_URL}/v1"


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
            raise RuntimeError(f"server exited early with code {proc.returncode}")
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


def build_server_cmd(model: dict[str, Any], ctx: int) -> list[str]:
    backend = model.get("backend", "llama")
    path = model["path"]
    if backend == "mlx":
        cmd = [
            "mlx_lm.server",
            "--model",
            path,
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ]
    else:
        cmd = [
            "llama-server",
            "-m",
            path,
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "-c",
            str(ctx),
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
    cmd.extend(model.get("server_args", []))
    return cmd


def run_one_model(model: dict[str, Any], args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    label = model["label"]
    path = Path(model["path"])
    if not path.exists():
        raise FileNotFoundError(path)

    print(f"\n=== {label}: starting server ===", flush=True)
    server_log = ServerLog(label)
    proc = subprocess.Popen(
        build_server_cmd(model, args.ctx),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    thread = threading.Thread(target=stream_output, args=(proc, server_log), daemon=True)
    thread.start()

    out_path = Path("results") / f"ifeval-lite-{label}.json"
    try:
        wait_for_server(proc)
        print(f"=== {label}: server ready ===", flush=True)
        cmd = [
            sys.executable,
            "scripts/ifeval_lite.py",
            "--base-url",
            API_URL,
            "--model",
            model["served"],
            "--label",
            label,
            "--runs",
            str(args.runs),
            "--timeout",
            str(args.timeout),
            "--max-tokens",
            str(args.max_tokens),
            "--out",
            str(out_path),
        ]
        for task in args.task:
            cmd.extend(["--task", task])
        print(f"$ {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, env=env)
        report = json.loads(out_path.read_text(encoding="utf-8"))
        return {
            "label": label,
            "name": model["name"],
            "path": str(path),
            "served": model["served"],
            "backend": model.get("backend", "llama"),
            "ctx": args.ctx,
            "memory": parse_memory(server_log.snapshot()),
            "result_file": str(out_path),
            "summary": report["summary"],
        }
    finally:
        print(f"=== {label}: stopping server ===", flush=True)
        stop_server(proc)


def print_table(suite: dict[str, Any]) -> None:
    task_ids = suite["tasks"]
    print("\nIFEval-lite summary", flush=True)
    task_headers = " | ".join(task_id.replace("_", " ") for task_id in task_ids)
    print(f"| Model | Passes | Score | {task_headers} | Memory |", flush=True)
    print(f"|---|---:|---:|{'---:|' * len(task_ids)}---:|", flush=True)
    for model in suite["models"]:
        summaries = {item["task_id"]: item for item in model["summary"]}
        score = sum(item["score"] for item in model["summary"])
        max_score = sum(item["max_score"] for item in model["summary"])
        passes = sum(item["passes"] for item in model["summary"])
        runs = sum(item["runs"] for item in model["summary"])
        cells = []
        for task_id in task_ids:
            item = summaries.get(task_id)
            cells.append(f"{item['score']}/{item['max_score']}" if item else "-")
        memory = model.get("memory", {})
        mem_text = "-"
        if "projected_gib" in memory:
            mem_text = f"{memory['projected_gib']:.2f} GiB"
        elif "mtl_self_gib" in memory:
            mem_text = f"{memory['mtl_self_gib']:.2f} GiB"
        print(
            f"| {model['name']} | {passes}/{runs} | {score}/{max_score} | "
            f"{' | '.join(cells)} | {mem_text} |",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--ctx", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--task", action="append", choices=[task.task_id for task in TASKS])
    parser.add_argument("--only", nargs="*", choices=[model["label"] for model in MODELS])
    parser.add_argument("--out", default="results/ifeval-lite-suite.json")
    args = parser.parse_args()

    if not args.task:
        args.task = [task.task_id for task in TASKS]

    selected = MODELS
    if args.only:
        selected = [model for model in MODELS if model["label"] in args.only]

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    reports = [run_one_model(model, args, env) for model in selected]
    suite = {
        "runs": args.runs,
        "ctx": args.ctx,
        "tasks": args.task,
        "models": reports,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(suite, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)
    print_table(suite)


if __name__ == "__main__":
    main()
