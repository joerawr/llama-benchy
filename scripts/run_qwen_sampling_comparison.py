#!/usr/bin/env python3
"""Compare Qwen3.6-35B with the local and model-card samplers."""

from __future__ import annotations

import json
import hashlib
import argparse
import os
import signal
import subprocess
import sys
import time
import threading
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
MODEL = MODEL_ROOT / "mudler/qwen36-apex-mtp/Qwen3.6-35B-A3B-Claude-4.7-Opus-Reasoning-Distilled-APEX-MTP-I-Quality.gguf"
SERVED = MODEL.name
BASE_URL = "http://127.0.0.1:18081/v1"
OUT = Path(os.environ.get("QWEN_SAMPLING_OUT", ROOT / "results/qwen36-apex-mtp-quality-sampling-comparison-20260823.json"))
OLD_OUT = ROOT / "results/qwen36-apex-mtp-quality-sampling-comparison-20260823.json"
MAX_TOKENS = 16384
TIMEOUT = 1800

VARIANTS = {
    "current-low-temp": {
        "temperature": 0.0,
        "top_p": 0.95,
        "top_k": 40,
        "min_p": 0.05,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
    },
    "qwen-recommended": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
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


def request(prompt: str, sampling: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": SERVED,
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
    message = body["choices"][0].get("message", {})
    answer = (message.get("content") or "").strip()
    usage = body.get("usage") or {}
    return {
        "elapsed_s": round(elapsed, 3),
        "answer": answer,
        "reasoning": (message.get("reasoning") or message.get("reasoning_content") or "").strip(),
        "usage": usage,
        "finish_reason": body["choices"][0].get("finish_reason"),
        "effective_output_tokens_per_s": round((usage.get("completion_tokens") or 0) / elapsed, 3) if elapsed else None,
    }


def wait_for_server(proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 900
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited with {proc.returncode}")
        try:
            if requests.get(f"{BASE_URL}/models", timeout=2).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("llama-server did not become ready")


def drain_server_output(proc: subprocess.Popen[str]) -> None:
    # Keep the child stdout pipe flowing during long requests.
    if proc.stdout is not None:
        for line in proc.stdout:
            if any(marker in line.lower() for marker in ("error", "exception", "warning")):
                print(line, end="", flush=True)


def stop_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def save(report: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-variant", choices=VARIANTS)
    args = parser.parse_args()
    if not MODEL.exists():
        raise FileNotFoundError(MODEL)
    report = {"suite_version": EXPERIMENT_SUITE_VERSION, "model": str(MODEL), "ctx": 65536, "max_tokens": MAX_TOKENS, "thinking": "on", "variants": {}}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        if existing.get("suite_version") != EXPERIMENT_SUITE_VERSION:
            raise ValueError("Existing experiment lacks matching suite provenance; choose a new output path")
        expected_hashes = {task_id: hashlib.sha256(prompt.encode()).hexdigest() for task_id, prompt, _ in tasks()}
        for item in existing.get("variants", {}).values():
            for task_id, record in item.get("records", {}).items():
                if record.get("semantic_judge", {}).get("task_prompt_sha256") != expected_hashes.get(task_id):
                    raise ValueError("Existing experiment prompt differs; choose a new output path")
        report.update(existing)

    server_cmd = [
        "llama-server", "-m", str(MODEL), "--host", "127.0.0.1", "--port", "18081",
        "-c", "65536", "-np", "1", "-ngl", "99", "--reasoning", "on",
        "--reasoning-budget", "-1", "--spec-type", "draft-mtp",
    ]
    print("$ " + " ".join(server_cmd), flush=True)
    proc = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    threading.Thread(target=drain_server_output, args=(proc,), daemon=True).start()
    try:
        wait_for_server(proc)
        print("server ready; thinking is enabled", flush=True)
        selected = {args.only_variant: VARIANTS[args.only_variant]} if args.only_variant else VARIANTS
        for variant, sampling in selected.items():
            records = report.setdefault("variants", {}).setdefault(variant, {"sampling": sampling, "records": {}})["records"]
            for task_id, prompt, grader in tasks():
                if task_id in records and records[task_id].get("semantic_grade", {}).get("score") is not None:
                    continue
                print(f"[{variant}] {task_id}", flush=True)
                request_started = time.perf_counter()
                try:
                    result = request(prompt, sampling)
                except requests.RequestException as exc:
                    result = {"answer": "", "reasoning": "", "usage": {}, "finish_reason": "error",
                              "elapsed_s": round(time.perf_counter() - request_started, 3), "effective_output_tokens_per_s": None, "error": str(exc)}
                diagnostic = grader(result["answer"])
                semantic, meta = judge_result(result["answer"], diagnostic, task_id, task_prompt=prompt, finish_reason=result.get("finish_reason"))
                result.update({"task_id": task_id, "diagnostic_grade": diagnostic, "semantic_grade": semantic, "semantic_judge": meta})
                records[task_id] = result
                save(report)
                print(f"  {semantic['score'] if semantic['score'] is not None else '-'}/{semantic['max_score']} {result['elapsed_s']}s {result['effective_output_tokens_per_s']} tok/s", flush=True)
    finally:
        stop_server(proc)
    for variant, data in report["variants"].items():
        data["total_score"] = sum(r["semantic_grade"]["score"] for r in data["records"].values()) if len(data["records"]) == 7 and all(r["semantic_grade"]["score"] is not None for r in data["records"].values()) else None
        data["total_max_score"] = sum(r["semantic_grade"]["max_score"] for r in data["records"].values())
    report["status"] = "complete" if all(item.get("total_score") is not None for item in report["variants"].values()) else "incomplete"
    save(report)
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
