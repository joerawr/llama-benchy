#!/usr/bin/env python3
"""Resumable, sequential Vulkan comparison; raw responses survive judge failures.

Run under a user transient service so a disconnected chat does not stop it.
The existing model service is restored after each model and on exit. This is
an explicitly versioned /24 thinking experiment, not a canonical /62 run.
"""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from codex_gap_campaign import atomic_write_json, build_tasks  # noqa: E402
from grader.semantic_judge import judge_result  # noqa: E402
from gguf_metadata import read_field  # noqa: E402

SUITE = ROOT / "benchmarks/suites/swift-qwen-thinking-v1.json"
OUT = ROOT / "results/swift-qwen-thinking-20261019"
PREFLIGHT = ROOT / "results/swift-qwen-preflight-20261019"
BINARY = Path("/home/jrogers/Documents/Codex/2026-10-07/task-3/llama.cpp-vulkan/build-vulkan/bin/llama-server")
SERVICE = "joe-local-model.service"
BASE = "http://127.0.0.1:18081"
MODEL_ROOT = Path.home() / "models"
TEMPLATE_SOURCE = PREFLIGHT / "ukisai--Swift-1.5-Qwen3.8-27b--chat_template.jinja"
XHIGH = "Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer."
MODELS = {
    "thinkingcap-qwen36-q6": {
        "name": "ThinkingCap Qwen3.6 27B Q6_K",
        "relative_path": "bartowski/bottlecapai_ThinkingCap-Qwen3.6-27B-GGUF/bottlecapai_ThinkingCap-Qwen3.6-27B-Q6_K.gguf",
        "sha256": "c2409ca58a56146f9fca2ee27beec694e10346cc64b70742997d9497914bae60",
        "bytes": 23463129792,
        "caveat": "Dense Qwen3.6 derivative, not base Qwen3.8. Common Swift/Qwen3.8 template supplies the explicit xhigh instruction; native ThinkingCap template has no named effort control."
    },
    "swift15-gsq-iq3s": {
        "name": "Swift 1.5 GSQ-RCO IQ3_S",
        "relative_path": "ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
        "sha256": "1333c6ea70ef348d4ac6d62732772e8ad6571ac5b3754c14ed54f1a0d904a786",
        "bytes": 11771546912,
        "repo": "ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF",
        "revision": "d74895bbe5db4bec1e0024e7cc87d59c02d7631a"
    },
    "swift15-q6": {
        "name": "Swift 1.5 Q6_K",
        "relative_path": "ukisai/Swift-1.5-Qwen3.8-27B-GGUF/Swift-1.5-Qwen3.8-27B-Q6_K.gguf",
        "sha256": "cd2eb6597026ce4eb86100e830be24f01461f84b89d4708634c2ec3d43b67fa8",
        "bytes": 23860565696,
        "repo": "ukisai/Swift-1.5-Qwen3.8-27B-GGUF",
        "revision": "14bfe4b42be4a925d98816db830155f476c605e7"
    }
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tasks_for_experiment():
    suite = json.loads(SUITE.read_text())
    source = build_tasks()
    tasks = {}
    for key, expected in suite["tasks"].items():
        task = source[key]
        if digest(task.prompt.encode()) != expected["source_prompt_sha256"]:
            raise ValueError(f"Source prompt changed for {key}; create a new suite version")
        prompt = task.prompt
        if key == "compression":
            if not prompt.startswith("/no_think\n\n"):
                raise ValueError("Compression directive differs from frozen experiment")
            prompt = prompt[len("/no_think\n\n"):]
        if digest(prompt.encode()) != expected["prompt_sha256"]:
            raise ValueError(f"Experiment prompt hash mismatch for {key}")
        tasks[key] = dataclasses.replace(task, prompt=prompt)
    return tasks


def needs_third(records: list[dict]) -> bool:
    if len(records) < 2:
        return False
    signatures = []
    for record in records[:2]:
        grade = record.get("semantic_grade", {})
        if grade.get("score") is None:
            return True
        signatures.append((grade["score"], json.dumps(grade.get("substantive_failures", []), sort_keys=True),
                           tuple((c["id"], c["pass"]) for c in record["diagnostic_grade"]["checks"])))
    return signatures[0] != signatures[1]


def summarize(records: dict, task_keys: list[str]) -> dict:
    summary = {}
    for label in MODELS:
        per_task = {}
        for key in task_keys:
            rows = [r for r in records.values() if r["label"] == label and r["task"] == key]
            scores = [r.get("semantic_grade", {}).get("score") for r in rows]
            per_task[key] = {"runs": len(rows), "scores": scores,
                             "mean_score": sum(scores) / len(scores) if len(scores) >= 2 and all(s is not None for s in scores) else None,
                             "elapsed_s": [r["elapsed_s"] for r in rows],
                             "generation_tokens_per_s": [r.get("timings", {}).get("predicted_per_second") for r in rows],
                             "reasoning_tokens": [r.get("reasoning_tokens") for r in rows]}
        means = [r["mean_score"] for r in per_task.values()]
        summary[label] = {"tasks": per_task, "score_out_of_24": sum(means) if all(s is not None for s in means) else None}
    return summary


def api(path: str, payload=None, timeout=20):
    r = requests.get(BASE + path, timeout=timeout) if payload is None else requests.post(BASE + path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def service_active() -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", SERVICE]).returncode == 0


def restore_service():
    subprocess.run(["systemctl", "--user", "start", SERVICE], check=True)
    for _ in range(120):
        try:
            r = requests.get("http://127.0.0.1:18082/health", timeout=2)
            if r.ok:
                return {"health": r.json(), "restored_at": time.time()}
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("Original service failed health check after restoration")


class MemoryMonitor:
    def __init__(self, pid: int, target: Path):
        self.pid, self.target = pid, target
        self.stop = threading.Event()
        self.stats = {"peak_rss_kib": 0, "peak_swap_kib": 0, "min_available_kib": None}
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            try:
                status = dict(line.split(":", 1) for line in Path(f"/proc/{self.pid}/status").read_text().splitlines() if ":" in line)
                memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
                self.stats["peak_rss_kib"] = max(self.stats["peak_rss_kib"], int(status["VmRSS"].split()[0]))
                self.stats["peak_swap_kib"] = max(self.stats["peak_swap_kib"], int(status["VmSwap"].split()[0]))
                available = int(memory["MemAvailable"].split()[0])
                old = self.stats["min_available_kib"]
                self.stats["min_available_kib"] = min(old, available) if old is not None else available
                atomic_write_json(self.target, self.stats | {"sampled_at": time.time()})
            except (OSError, KeyError):
                pass
            self.stop.wait(5)


def request_stream(payload: dict, destination: Path, timeout: int) -> dict:
    """Flush every SSE event; timeout/disconnects keep their partial evidence."""
    started = time.monotonic()
    result = {"answer": "", "reasoning": "", "usage": {}, "timings": {}, "finish_reason": None}
    last_heartbeat = started
    try:
        with destination.open("w") as events, requests.post(BASE + "/v1/chat/completions", json=payload,
                timeout=(30, min(timeout, 120)), stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Declared wall timeout {timeout}s exceeded")
                if not line:
                    continue
                text = line.decode("utf-8")
                events.write(text + "\n"); events.flush()
                if text == "data: [DONE]":
                    break
                if not text.startswith("data: "):
                    continue
                event = json.loads(text[6:])
                if event.get("error"):
                    raise RuntimeError(str(event["error"]))
                for choice in event.get("choices", []):
                    delta = choice.get("delta", {})
                    result["answer"] += delta.get("content") or ""
                    result["reasoning"] += delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if choice.get("finish_reason"):
                        result["finish_reason"] = choice["finish_reason"]
                    if delta.get("tool_calls"):
                        result["tool_calls"] = delta["tool_calls"]
                if event.get("usage"):
                    result["usage"] = event["usage"]
                if event.get("timings"):
                    result["timings"] = event["timings"]
                now = time.monotonic()
                if now - last_heartbeat > 60:
                    print(f"  generating: {now-started:.0f}s, {len(result['reasoning'])} reasoning chars, {len(result['answer'])} answer chars", flush=True)
                    last_heartbeat = now
        if result["finish_reason"] is None:
            raise RuntimeError("Stream closed without a finish reason")
        if result.get("tool_calls") or not result["reasoning"].strip():
            raise RuntimeError("Tools attempted or reasoning absent; thinking experiment is invalid")
    except (requests.RequestException, RuntimeError, ValueError, TimeoutError) as exc:
        result.update({"finish_reason": "error", "error": str(exc)})
    result["elapsed_s"] = round(time.monotonic() - started, 3)
    for field in ["answer", "reasoning"]:
        try:
            result[field + "_tokens"] = len(api("/tokenize", {"content": result[field], "add_special": False})["tokens"])
        except requests.RequestException:
            result[field + "_tokens"] = None
    result["token_count_method"] = "Separate retokenization of extracted reasoning and answer; usage completion count includes control tokens."
    return result


def verify_model(label: str) -> Path:
    model = MODELS[label]
    path = MODEL_ROOT / model["relative_path"]
    # Downloads may still be in progress; never load partial files.
    deadline = time.monotonic() + 4 * 3600
    while not path.is_file() or path.stat().st_size != model["bytes"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Model download not complete: {path}")
        print(f"Waiting for complete download: {label}", flush=True)
        time.sleep(30)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != model["sha256"]:
        raise ValueError(f"Model SHA256 mismatch: {label}")
    atomic_write_json(OUT / f"{label}-identity.json", model | {"path": str(path), "verified_sha256": h.hexdigest(), "verified_at": time.time()})
    return path


def run_model(label: str, path: Path, state: dict, tasks: dict, args):
    records = state["records"]
    was_active = service_active()
    proc = None
    monitor = None
    log = (OUT / f"{label}-server.log").open("a")
    try:
        if was_active:
            subprocess.run(["systemctl", "--user", "stop", SERVICE], check=True)
        others = subprocess.run(["pgrep", "-x", "llama-server"], capture_output=True, text=True)
        if others.returncode == 0:
            raise RuntimeError(f"Another model server is active: {others.stdout.strip()}")
        command = [str(BINARY), "-m", str(path), "--alias", label, "--host", "127.0.0.1", "--port", "18081",
                   "-c", str(args.ctx), "-np", "1", "-b", "128", "-ub", "128", "-t", "4",
                   "--device", "Vulkan0", "-ngl", "99", "--jinja", "--reasoning", "on",
                   "--reasoning-effort", "xhigh", "--reasoning-budget", "-1", "--reasoning-format", "deepseek",
                   "--chat-template-file", str(OUT / "common-chat-template.jinja"),
                   "--cache-type-k", "f16", "--cache-type-v", "f16", "--spec-type", "none",
                   "--no-context-shift", "--timeout", str(args.timeout + 120)]
        atomic_write_json(OUT / f"{label}-server-command.json", {"command": command, "started_at": time.time()})
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        monitor = MemoryMonitor(proc.pid, OUT / f"{label}-memory.json"); monitor.thread.start()
        for _ in range(300):
            if proc.poll() is not None:
                raise RuntimeError(f"GPU server exited {proc.returncode}; see {label}-server.log")
            try:
                if api("/health", timeout=2).get("status") == "ok":
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            raise TimeoutError("GPU server startup timed out")
        props = api("/props")
        if props["default_generation_settings"]["n_ctx"] != args.ctx:
            raise RuntimeError("Server context differs from declared experiment")
        atomic_write_json(OUT / f"{label}-props.json", props)
        suite = json.loads(SUITE.read_text())
        for key, task in tasks.items():
            payload = {"model": label, "messages": [{"role": "user", "content": task.prompt}],
                       "reasoning_effort": "xhigh", "chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "xhigh"},
                       "reasoning_format": "deepseek", "max_tokens": -1,
                       "stream": True, "stream_options": {"include_usage": True}, "cache_prompt": False,
                       **suite["sampling"]}
            rendered = api("/apply-template", payload)["prompt"]
            if rendered.count(XHIGH) != 1 or "<think>" not in rendered[-40:]:
                raise RuntimeError("Rendered chat lacks exactly one xhigh instruction and an open thinking prefix")
            reference = OUT / f"{key}-rendered-chat.txt"
            if reference.exists() and reference.read_text() != rendered:
                raise RuntimeError("Models received different rendered chat prompts")
            reference.write_text(rendered)
            atomic_write_json(OUT / f"{label}-{key}-template-check.json", {"sha256": digest(rendered.encode()), "xhigh_verified": True, "thinking_prefix_verified": True})
            # Run two first; third only when signatures differ or a pass fails.
            run = 1
            while run <= 3:
                existing = [records[f"{label}:{key}:{n}"] for n in (1, 2) if f"{label}:{key}:{n}" in records]
                if run == 3 and not needs_third(existing):
                    break
                record_key = f"{label}:{key}:{run}"
                prefix = OUT / f"{label}-{key}-{run}"
                if record_key not in records:
                    # Reuse a saved raw response if interrupted during grading.
                    raw_path = prefix.with_suffix(".raw.json")
                    if raw_path.exists():
                        raw = json.loads(raw_path.read_text())
                    else:
                        request = payload | {"seed": 20261019 + run}
                        atomic_write_json(prefix.with_suffix(".request.json"), request)
                        state["current"] = record_key; save(state, tasks)
                        print(f"[{record_key}] requesting on Vulkan0", flush=True)
                        raw = request_stream(request, prefix.with_suffix(".sse"), args.timeout)
                        atomic_write_json(raw_path, raw)
                    diagnostic = task.grader(raw["answer"])
                    grade, meta = judge_result(raw["answer"], diagnostic, task.task_id, task_prompt=task.prompt, finish_reason=raw["finish_reason"])
                    records[record_key] = raw | {"label": label, "task": key, "run": run, "diagnostic_grade": diagnostic,
                                               "semantic_grade": grade, "semantic_judge": meta}
                    save(state, tasks)
                    print(f"[{record_key}] score {grade.get('score')}/12; {raw['elapsed_s']}s", flush=True)
                run += 1
        state.setdefault("model_status", {})[label] = "finished"
    finally:
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
        if monitor:
            monitor.stop.set(); monitor.thread.join(timeout=10)
        log.close()
        if was_active:
            state["service_restored"] = restore_service()
        save(state, tasks)


def save(state: dict, tasks: dict):
    state["updated_at"] = time.time()
    state["summary"] = summarize(state["records"], list(tasks))
    atomic_write_json(OUT / "report.json", state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ctx", type=int, default=32768)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--only-model", choices=MODELS)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    tasks = tasks_for_experiment()
    OUT.mkdir(parents=True, exist_ok=True)
    template = (TEMPLATE_SOURCE.read_bytes() if TEMPLATE_SOURCE.exists() else
                read_field(MODEL_ROOT / MODELS["swift15-gsq-iq3s"]["relative_path"], "tokenizer.chat_template").encode())
    template_path = OUT / "common-chat-template.jinja"
    if template_path.exists() and template_path.read_bytes() != template:
        raise ValueError("Frozen common template changed")
    template_path.write_bytes(template)
    for key, task in tasks.items():
        (OUT / f"{key}-prompt.txt").write_text(task.prompt)
    manifest = {"suite": json.loads(SUITE.read_text()), "context": args.ctx, "timeout_s": args.timeout,
                "completion_cap": None, "context_shift": False, "kv_precision": "f16/f16", "mtp": False,
                "models": MODELS, "common_template_sha256": digest(template),
                "template_source_revision": "b4c84d42903a8646b25857eb2827288d92ed85a4",
                "template_caveat": "All models use the same Swift/Qwen3.8 template. This supplies xhigh for ThinkingCap, whose native Qwen3.6 template lacks effort levels.",
                "runtime": str(BINARY), "runtime_sha256": digest(BINARY.read_bytes()),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    manifest_path = OUT / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise ValueError("Run protocol changed; choose a new output directory")
    atomic_write_json(manifest_path, manifest)
    if args.prepare_only:
        print(f"Prepared {OUT}; no service changes or inference", flush=True)
        return
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "benchy-state/campaign.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.seek(0); lock.truncate(); json.dump({"campaign_id": "swift-qwen-thinking-20261019", "pid": os.getpid()}, lock); lock.flush()
        state_path = OUT / "report.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"records": {}, "status": "running", "created_at": time.time()}
        state["status"] = "running"; save(state, tasks)
        try:
            for label in ([args.only_model] if args.only_model else MODELS):
                if state.get("model_status", {}).get(label) == "finished":
                    continue
                state["current"] = f"verify:{label}"; save(state, tasks)
                path = verify_model(label)
                run_model(label, path, state, tasks, args)
            complete = all(state.get("model_status", {}).get(label) == "finished" for label in MODELS)
            state["status"] = "complete" if complete and all(s["score_out_of_24"] is not None for s in state["summary"].values()) else "incomplete"
            state["current"] = None
        except BaseException as exc:
            state.update({"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "error", "error": repr(exc)})
            raise
        finally:
            save(state, tasks)


if __name__ == "__main__":
    main()
