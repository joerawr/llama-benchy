#!/usr/bin/env python3
"""Run the full /62 suite on the local Ornith MLX checkpoints.

Each model uses its own model-card general-task sampler. Thinking is
explicitly enabled in the chat template for both models.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import ifeval_lite  # noqa: E402
import long_file_compression as compression  # noqa: E402
import pinchbench_lite as pinchbench  # noqa: E402
from grader.semantic_judge import judge_result  # noqa: E402

MODEL_ROOT = Path(os.environ.get("LLAMA_BENCHY_MODEL_ROOT", str(Path.home() / "models"))).expanduser()
PORT = 18081
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
MAX_TOKENS = int(os.environ.get("ORNITH_MAX_TOKENS", "16384"))
TIMEOUT = 1_800
OUT = Path(os.environ.get("ORNITH_SUITE_OUT", ROOT / "results/ornith15-thinking-suite-20260823.json"))

MODELS: dict[str, dict[str, Any]] = {
    "ornith15-35b-mlx8": {
        "name": "Ornith 1.5 35B-A3B MLX 8-bit",
        "path": MODEL_ROOT / "ornith-ai/Ornith-1.5-35B-A3B-MLX-8bit",
        "sampling": {
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "repetition_penalty": 1.0,
        },
        "server_sampling": ["--temp", "0.6", "--top-p", "0.95", "--top-k", "20", "--min-p", "0.0"],
    },
    "ornith15-9b-mlx8": {
        "name": "Ornith 1.5 9B MLX 8-bit",
        "path": MODEL_ROOT / "ornith-ai/Ornith-1.5-9B-MLX-8bit",
        "sampling": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repetition_penalty": 1.0,
        },
        "server_sampling": ["--temp", "1.0", "--top-p", "0.95", "--top-k", "20", "--min-p", "0.0"],
    },
}

EXPERIMENT_SUITE_VERSION = "llama-benchy-thinking-comparison@1.0"
SUITE_IFEVAL_IDS = {"family_backup_note", "two_section_backup_checklist", "family_text_lines"}


def tasks() -> list[tuple[str, str, Any]]:
    pinch_dir = pinchbench.DEFAULT_PINCHBENCH_DIR
    csv_path = pinch_dir / "assets/csvs/apple_stock_2014.csv"
    csv_text = csv_path.read_text(encoding="utf-8")
    ref = pinchbench.finance_reference(pinchbench.load_csv_rows(csv_path))
    access_csv = pinchbench.load_access_events_csv(pinch_dir)
    note = (ROOT / "benchmarks-files/compression/ai-frontier-access-risk-fable-gpt56-glm52-2026-06-26.md").read_text(encoding="utf-8")
    compression_prompt = compression.PROMPT_TEMPLATE.format(note=note).replace("/no_think\n\n", "")
    return [
        ("task_csv_finance_report", pinchbench.build_finance_prompt(csv_text), lambda a: pinchbench.grade_finance(a, ref)),
        ("task_log_apache_error_summary", pinchbench.build_log_prompt((pinch_dir / "assets/logs/apache_error.log").read_text(encoding="utf-8", errors="replace")), pinchbench.grade_log),
        ("task_access_log_anomaly", pinchbench.build_access_anomaly_prompt(access_csv), pinchbench.grade_access_anomaly),
        ("long_file_compression", compression_prompt, compression.grade),
        *[(task.task_id, task.prompt, task.grader) for task in ifeval_lite.TASKS if task.task_id in SUITE_IFEVAL_IDS],
    ]


def request(model_name: str, prompt: str, sampling: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "stream": False,
        "cache_prompt": False,
        **sampling,
    }
    started = time.perf_counter()
    response = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=TIMEOUT)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]
    message = choice.get("message", {})
    usage = body.get("usage") or {}
    completion_tokens = usage.get("completion_tokens") or 0
    return {
        "elapsed_s": round(elapsed, 3),
        "answer": (message.get("content") or "").strip(),
        "reasoning": (message.get("reasoning") or message.get("reasoning_content") or "").strip(),
        "usage": usage,
        "finish_reason": choice.get("finish_reason"),
        "effective_output_tokens_per_s": round(completion_tokens / elapsed, 3) if elapsed else None,
    }


def wait_for_server(proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 900
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"mlx_lm.server exited with {proc.returncode}")
        try:
            response = requests.get(f"{BASE_URL}/models", timeout=2)
            if response.ok:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(2)
    raise TimeoutError(f"mlx_lm.server did not become ready: {last_error}")


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


def stream_server_output(proc: subprocess.Popen[str], label: str) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        lower = line.lower()
        if any(marker in lower for marker in ("error", "exception", "traceback", "killed", "memory", "warning")):
            print(f"[{label} server] {line}", end="", flush=True)


def save(report: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def run_model(label: str, config: dict[str, Any], report: dict[str, Any]) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("Ornith MLX requires macOS/Metal; use a GGUF runner on Linux")
    path = config["path"]
    if not path.exists():
        raise FileNotFoundError(path)

    server_cmd = [
        "mlx_lm.server",
        "--model", str(path),
        "--host", "127.0.0.1",
        "--port", str(PORT),
        *config["server_sampling"],
        "--max-tokens", str(MAX_TOKENS),
        "--chat-template-args", '{"enable_thinking":true}',
    ]
    print(f"\n=== {label}: starting thinking-enabled server ===", flush=True)
    print("$ " + " ".join(server_cmd), flush=True)
    proc = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    threading.Thread(target=stream_server_output, args=(proc, label), daemon=True).start()
    try:
        wait_for_server(proc)
        print(f"=== {label}: server ready; thinking enabled ===", flush=True)
        model_report = report["models"].setdefault(label, {
            "name": config["name"],
            "path": str(path),
            "thinking": True,
            "sampling": config["sampling"],
            "records": {},
        })
        for task_id, prompt, grader in tasks():
            if task_id in model_report["records"] and model_report["records"][task_id].get("semantic_grade", {}).get("score") is not None:
                continue
            print(f"[{label}] {task_id}", flush=True)
            # mlx_lm.server resolves the request's model field as a local path
            # (or Hugging Face repo ID), so use the loaded checkpoint path.
            request_started = time.perf_counter()
            try:
                result = request(str(path), prompt, config["sampling"])
            except requests.RequestException as exc:
                result = {"answer": "", "reasoning": "", "usage": {}, "finish_reason": "error",
                          "elapsed_s": round(time.perf_counter() - request_started, 3), "effective_output_tokens_per_s": None, "error": str(exc)}
            diagnostic = grader(result["answer"])
            semantic, meta = judge_result(result["answer"], diagnostic, task_id, task_prompt=prompt, finish_reason=result.get("finish_reason"))
            result.update({"task_id": task_id, "diagnostic_grade": diagnostic, "semantic_grade": semantic, "semantic_judge": meta})
            model_report["records"][task_id] = result
            save(report)
            print(f"  {semantic['score'] if semantic['score'] is not None else '-'}/{semantic['max_score']} {result['elapsed_s']}s {result['effective_output_tokens_per_s']} tok/s", flush=True)
    finally:
        if proc.poll() is not None:
            print(f"[{label} server] exited with code {proc.returncode}", flush=True)
        print(f"=== {label}: stopping server ===", flush=True)
        stop_server(proc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=list(MODELS), action="append")
    args = parser.parse_args()
    selected = args.only or list(MODELS)
    report = {
        "suite_version": EXPERIMENT_SUITE_VERSION,
        "suite": "/62",
        "max_tokens": MAX_TOKENS,
        "ctx": 65536,
        "models": {},
    }
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        if existing.get("suite_version") != EXPERIMENT_SUITE_VERSION:
            raise ValueError("Existing experiment lacks matching suite provenance; choose a new output path")
        expected_hashes = {task_id: hashlib.sha256(prompt.encode()).hexdigest() for task_id, prompt, _ in tasks()}
        for item in existing.get("models", {}).values():
            for task_id, record in item.get("records", {}).items():
                if record.get("semantic_judge", {}).get("task_prompt_sha256") != expected_hashes.get(task_id):
                    raise ValueError("Existing experiment prompt differs; choose a new output path")
        report.update(existing)
    try:
        for label in selected:
            run_model(label, MODELS[label], report)
    finally:
        for label, model_report in report.get("models", {}).items():
            records = model_report.get("records", {})
            model_report["total_score"] = sum(r["semantic_grade"]["score"] for r in records.values()) if len(records) == 7 and all(r["semantic_grade"]["score"] is not None for r in records.values()) else None
            model_report["total_max_score"] = sum(r["semantic_grade"]["max_score"] for r in records.values())
        save(report)
    report["status"] = "complete" if all(item.get("total_score") is not None for item in report["models"].values()) else "incomplete"
    save(report)
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
