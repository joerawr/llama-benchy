#!/usr/bin/env python3
"""Two five-minute throughput probes, with no quality grading or follow-on runs."""
from __future__ import annotations

import json
import argparse
import fcntl
import hashlib
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_swift_qwen_comparison import (
    BASE, BINARY, MODELS, SERVICE, MemoryMonitor, XHIGH, api, atomic_write_json,
    restore_service, service_active,
)
from gguf_metadata import read_field

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/swift-five-minute-speed-20261019"
LABELS = ["swift15-gsq-iq3s", "swift15-q6"]
PROMPT = (ROOT / "benchmarks/suites/swift-speed-family-text-v1.txt").read_text()
SECONDS = 300
TEMPLATE_SHA256 = "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041"
PROMPT_SHA256 = "9a8e6af7452ae51b085b2bda91baddd2b444088759fd00c2815a4546f56c42d0"


def server_command(server, model, label, template, device=None):
    command = [str(server), "-m", str(model), "--alias", label, "--host", "127.0.0.1", "--port", "18081",
               "-c", "32768", "-np", "1", "-b", "128", "-ub", "128", "-t", "4", "-ngl", "99",
               "--jinja", "--reasoning", "on", "--reasoning-effort", "xhigh", "--reasoning-budget", "-1",
               "--reasoning-format", "deepseek", "--chat-template-file", str(template),
               "--cache-type-k", "f16", "--cache-type-v", "f16", "--spec-type", "none", "--no-context-shift"]
    if device:
        command += ["--device", device]
    return command


def verify_source(label, model_root, destination):
    identity = MODELS[label]
    path = model_root / identity["relative_path"]
    if not path.is_file() or path.stat().st_size != identity["bytes"]:
        raise ValueError(f"Missing or incomplete model: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != identity["sha256"]:
        raise ValueError(f"Model hash mismatch: {label}")
    template = read_field(path, "tokenizer.chat_template")
    if hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise ValueError("The model's native chat template differs from the frozen Linux probe")
    destination.mkdir(parents=True, exist_ok=True)
    template_path = destination / "common-chat-template.jinja"
    if template_path.exists() and template_path.read_text() != template:
        raise ValueError("Models contain different native chat templates")
    template_path.write_text(template)
    atomic_write_json(destination / f"{label}-identity.json", identity | {"verified_sha256": digest.hexdigest()})
    return path, template_path


def aggregate(requests_):
    timings = [r["timings"] for r in requests_ if r.get("timings")]
    tokens = sum(t.get("predicted_n", 0) for t in timings)
    generation_ms = sum(t.get("predicted_ms", 0) for t in timings)
    prompt_tokens = sum(t.get("prompt_n", 0) for t in timings)
    prompt_ms = sum(t.get("prompt_ms", 0) for t in timings)
    return {"generated_tokens": tokens, "generation_seconds": generation_ms / 1000,
            "generation_tokens_per_s": tokens * 1000 / generation_ms if generation_ms else None,
            "prompt_tokens": prompt_tokens, "prompt_seconds": prompt_ms / 1000,
            "prompt_tokens_per_s": prompt_tokens * 1000 / prompt_ms if prompt_ms else None,
            "requests": len(requests_), "completed_answers": sum(r.get("finish_reason") == "stop" for r in requests_)}


def probe(label, deadline, records, report):
    while time.monotonic() < deadline - 2:
        number = len(records) + 1
        payload = {"model": label, "messages": [{"role": "user", "content": PROMPT}],
                   "reasoning_effort": "xhigh", "chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "xhigh"},
                   "reasoning_format": "deepseek", "stream": True, "stream_options": {"include_usage": True},
                   "timings_per_token": True, "return_progress": True, "max_tokens": -1, "cache_prompt": False,
                   "temperature": 1.0, "top_p": .95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0,
                   "repeat_penalty": 1.0, "seed": 20261019 + number}
        prefix = OUT / f"{label}-{number}"
        atomic_write_json(prefix.with_suffix(".request.json"), payload)
        row = {"answer": "", "reasoning": "", "timings": {}, "finish_reason": None, "started_at": time.time()}
        started = time.monotonic(); heartbeat = started
        try:
            remaining = max(1, deadline - time.monotonic())
            with prefix.with_suffix(".sse").open("w") as raw, requests.post(BASE + "/v1/chat/completions", json=payload,
                    stream=True, timeout=(10, min(120, remaining))) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        text = line.decode(); raw.write(text + "\n"); raw.flush()
                        if text == "data: [DONE]":
                            break
                        if text.startswith("data: "):
                            event = json.loads(text[6:])
                            if event.get("error"):
                                raise RuntimeError(str(event["error"]))
                            for choice in event.get("choices", []):
                                delta = choice.get("delta", {})
                                row["reasoning"] += delta.get("reasoning_content") or delta.get("reasoning") or ""
                                row["answer"] += delta.get("content") or ""
                                if choice.get("finish_reason"):
                                    row["finish_reason"] = choice["finish_reason"]
                            row["timings"] = event.get("timings") or row["timings"]
                    now = time.monotonic()
                    if now - heartbeat > 30:
                        report["models"][label]["live_timings"] = row["timings"]
                        atomic_write_json(OUT / "report.json", report)
                        print(label, "remaining", round(max(0, deadline-now)), "s;", row["timings"], flush=True)
                        heartbeat = now
                    if now >= deadline:
                        row["finish_reason"] = "probe_window_elapsed"
                        break
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            row["finish_reason"] = "probe_window_elapsed" if time.monotonic() >= deadline - 1 else "error"
            row["error"] = str(exc)
        row["elapsed_s"] = time.monotonic() - started
        row["quality_score"] = None
        row["scope"] = "Throughput only. Timed partial output is not a completed quality attempt."
        atomic_write_json(prefix.with_suffix(".response.json"), row)
        records.append(row)
        report["models"][label]["summary"] = aggregate(records)
        atomic_write_json(OUT / "report.json", report)
        if row["finish_reason"] in {"probe_window_elapsed", "error"}:
            break


def main():
    global OUT, SECONDS
    parser = argparse.ArgumentParser(description=__doc__)
    default_server = os.environ.get("LLAMA_BENCHY_LLAMA_SERVER") or (str(BINARY) if sys.platform == "linux" else shutil.which("llama-server"))
    parser.add_argument("--server", default=default_server, help="Native GPU-enabled llama-server executable")
    parser.add_argument("--models-root", type=Path, default=Path(os.environ.get("LLAMA_BENCHY_MODEL_ROOT", Path.home() / "models")))
    parser.add_argument("--out", type=Path, default=ROOT / f"results/swift-five-minute-speed-{time.strftime('%Y%m%d')}-{sys.platform}")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--device", default="Vulkan0" if sys.platform == "linux" else None,
                        help="Linux defaults to Vulkan0; macOS selects its enumerated Metal GPU")
    parser.add_argument("--only-model", choices=LABELS, action="append")
    parser.add_argument("--prepare-only", action="store_true", help="Verify weights, native template and GPU runtime without inference/service changes")
    args = parser.parse_args()
    if not args.server or not Path(args.server).is_file():
        parser.error("Pass --server /path/to/a/native/GPU-enabled/llama-server")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if hashlib.sha256(PROMPT.encode()).hexdigest() != PROMPT_SHA256:
        raise ValueError("Canonical prompt changed; create a new probe version")
    OUT, SECONDS = args.out.expanduser().resolve(), args.seconds
    model_root = args.models_root.expanduser().resolve()
    labels = args.only_model or LABELS
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "report.json").exists():
        parser.error("Output already contains a report; select a fresh --out to preserve evidence")
    devices = subprocess.run([args.server, "--list-devices"], capture_output=True, text=True, check=True)
    inventory = devices.stdout + devices.stderr
    if (sys.platform == "darwin" and "Metal" not in inventory) or (args.device and args.device not in inventory):
        raise RuntimeError(f"Requested GPU backend absent: {inventory}")
    version = subprocess.run([args.server, "--version"], capture_output=True, text=True, check=True)
    if args.prepare_only:
        for label in labels:
            verify_source(label, model_root, OUT)
        print("Verified weights, native xhigh template and GPU runtime. No inference or service changes.")
        return
    report = {"status": "running", "started_at": time.time(), "seconds_per_model": SECONDS,
              "task": "family_text_lines", "prompt": PROMPT, "context": 32768, "thinking": "xhigh",
              "device": args.device or "Metal (runtime default)", "mtp": False, "kv_precision": "f16/f16",
              "platform": platform.platform(), "runtime_version": version.stdout + version.stderr,
              "gpu_inventory": inventory, "prompt_sha256": PROMPT_SHA256, "template_sha256": TEMPLATE_SHA256,
              "policy": "300-second wall probe starts after model loading and prompt-template verification. Repeat the same short task if it ends early. Generation tok/s uses summed backend tokens divided by summed generation seconds; prompt processing is separate. No quality grading or automatic quality campaign follows.",
              "models": {}}
    atomic_write_json(OUT / "report.json", report)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(signum)
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "benchy-state/campaign.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.seek(0); lock.truncate();json.dump({"campaign_id": "swift-speed-20261019", "pid": os.getpid()}, lock);lock.flush()
        try:
            for label in labels:
                report["current"] = "verify:" + label;atomic_write_json(OUT / "report.json", report)
                path, template_path = verify_source(label, model_root, OUT)
                proc = None; monitor = None; was_active = sys.platform == "linux" and service_active()
                with (OUT / f"{label}-server.log").open("w") as log:
                    try:
                        if was_active:
                            subprocess.run(["systemctl", "--user", "stop", SERVICE], check=True)
                        if subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True).returncode == 0:
                            raise RuntimeError("Another inference server is active")
                        cmd = server_command(args.server, path, label, template_path, args.device)
                        report["models"][label] = {"name": MODELS[label]["name"], "command": cmd, "requests": [], "status": "loading"}
                        atomic_write_json(OUT / "report.json", report)
                        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                        if sys.platform == "linux":
                            monitor = MemoryMonitor(proc.pid, OUT / f"{label}-memory.json");monitor.thread.start()
                        for _ in range(300):
                            if proc.poll() is not None:
                                raise RuntimeError(f"GPU server exited {proc.returncode}")
                            try:
                                if api("/health", timeout=2).get("status") == "ok":break
                            except requests.RequestException:pass
                            time.sleep(1)
                        else:raise TimeoutError("GPU server loading timed out")
                        rendered = api("/apply-template", {"messages": [{"role": "user", "content": PROMPT}], "reasoning_effort": "xhigh", "chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "xhigh"}})["prompt"]
                        if rendered.count(XHIGH) != 1 or "<think>" not in rendered[-40:]:
                            raise RuntimeError("xhigh thinking template verification failed")
                        reference = OUT / "rendered-prompt.txt"
                        if reference.exists() and reference.read_text() != rendered:raise RuntimeError("Different rendered prompts")
                        reference.write_text(rendered)
                        report["current"] = label
                        report["models"][label].update({"status": "probing", "probe_started_at": time.time()})
                        atomic_write_json(OUT / "report.json", report)
                        print("Starting five-minute probe:", label, flush=True)
                        probe(label, time.monotonic() + SECONDS, report["models"][label]["requests"], report)
                        report["models"][label].update({"status": "finished", "probe_finished_at": time.time()})
                        print("Finished:", label, report["models"][label]["summary"], flush=True)
                    finally:
                        if proc is not None and proc.poll() is None:
                            proc.send_signal(signal.SIGINT)
                            try:proc.wait(timeout=30)
                            except subprocess.TimeoutExpired:proc.kill();proc.wait()
                        if monitor:monitor.stop.set();monitor.thread.join(timeout=10)
                        if was_active:report["service_restored"] = restore_service()
                        atomic_write_json(OUT / "report.json", report)
            report["status"] = "complete"
            report["current"] = None
        except BaseException as exc:
            report.update({"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "error", "error": repr(exc)})
            raise
        finally:
            report["updated_at"] = time.time();atomic_write_json(OUT / "report.json", report)


if __name__ == "__main__":
    main()
