#!/usr/bin/env python3
"""Run the apples-to-apples quality campaign through Claude Code JSON mode."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from codex_gap_campaign import (  # noqa: E402
    NEUTRAL_WRAPPER,
    ROOT,
    atomic_write_json,
    build_tasks,
    grader_signature,
    semantic_judge,
    should_run_third,
)


STATE_PATH = ROOT / "results" / "claude-apples-campaign-20260714.json"
EVENT_DIR = ROOT / "results" / "claude-apples-events-20260714"
WORK_DIR = Path("/private/tmp/claude-benchmark-empty")
CLAUDE_TOOL_FREE_WRAPPER = (
    "You are in a tool-free evaluation sandbox. Do not call tools or attempt to use shell, Linux, "
    "filesystem, network, or file-inspection capabilities. The complete source material is already "
    "included in this prompt. Analyze only the supplied text and return the requested final answer "
    "directly. Do not explain these restrictions or your process.\n\n"
)

CONFIGS = [
    ("sonnet", "low"),
    ("sonnet", "medium"),
    ("sonnet", "high"),
    ("sonnet", "xhigh"),
    ("sonnet", "max"),
    ("opus", "low"),
    ("opus", "medium"),
    ("opus", "xhigh"),
    ("fable", "low"),
    ("fable", "medium"),
    ("fable", "high"),
    ("opus", "high"),
]

TASK_NAMES = [
    "finance",
    "apache",
    "access",
    "compression",
    "family_backup_note",
    "two_section_backup_checklist",
    "family_text_lines",
]

SESSION_LIMIT_PATTERN = re.compile(
    r"you(?:'|\u2019)ve hit your session limit(?:\s*\u00b7\s*resets\s+(.+))?",
    re.IGNORECASE,
)


def config_key(model: str, effort: str) -> str:
    return f"{model}:{effort}"


def record_key(model: str, effort: str, task_id: str, run: int) -> str:
    return f"{config_key(model, effort)}:{task_id}:{run}"


def initial_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign": "Claude apples-to-apples quality and usage comparison",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "updated_at": None,
        "status": "running",
        "policy": {
            "runs_before_gate": 2,
            "third_run": "only when complete grader signatures differ or a run fails",
            "sequential": True,
            "timeout": "none; pause manually if needed",
            "working_directory": str(WORK_DIR),
            "tools": "disabled",
            "usage_source": "claude --output-format json",
        },
        "configs": [{"model": model, "effort": effort} for model, effort in CONFIGS],
        "records": {},
        "gates": {},
        "failed_attempt_history": [],
    }


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return initial_state()


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    atomic_write_json(STATE_PATH, state)


def usage_summary(body: dict[str, Any], elapsed_s: float) -> dict[str, Any]:
    usage = body.get("usage") or {}
    model_usage = body.get("modelUsage") or {}
    resolved_models = sorted(model_usage)
    input_tokens = int(usage.get("input_tokens") or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    api_s = float(body.get("duration_api_ms") or 0) / 1000
    return {
        "resolved_models": resolved_models,
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "total_input_tokens": input_tokens + cache_creation + cache_read,
        "output_tokens": output_tokens,
        "cost_usd": float(body.get("total_cost_usd") or 0),
        "duration_api_ms": body.get("duration_api_ms"),
        "ttft_ms": body.get("ttft_ms"),
        "effective_output_tokens_per_s": round(output_tokens / elapsed_s, 3) if elapsed_s else None,
        "api_output_tokens_per_s": round(output_tokens / api_s, 3) if api_s else None,
    }


def session_limit_blocker(body: dict[str, Any]) -> dict[str, str] | None:
    if not body.get("is_error"):
        return None
    message = body.get("result")
    if not isinstance(message, str):
        return None
    match = SESSION_LIMIT_PATTERN.search(message)
    if not match:
        return None
    blocker = {"type": "claude_session_limit", "message": message}
    if match.group(1):
        blocker["resets"] = match.group(1).strip()
    return blocker


def authentication_blocker(body: dict[str, Any]) -> dict[str, str] | None:
    if not body.get("is_error"):
        return None
    message = body.get("result")
    if not isinstance(message, str):
        return None
    if "failed to authenticate" not in message.lower():
        return None
    return {"type": "claude_authentication", "message": message}


def run_once(model: str, effort: str, task: Any, run: int) -> dict[str, Any]:
    slug = f"claude-{model}-{effort}-{task.task_id}-run{run}"
    json_path = EVENT_DIR / f"{slug}.json"
    answer_path = EVENT_DIR / f"{slug}.md"
    EVENT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--effort",
        effort,
        "--allowed-tools",
        "",
        "--no-session-persistence",
        "--safe-mode",
        CLAUDE_TOOL_FREE_WRAPPER + NEUTRAL_WRAPPER + task.prompt,
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=WORK_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        elapsed = round(time.monotonic() - started, 3)
        json_path.write_text(result.stdout, encoding="utf-8")
        body = json.loads(result.stdout) if result.stdout.strip() else {}
        answer = body.get("result") if isinstance(body.get("result"), str) else ""
        blocker = session_limit_blocker(body)
        answer_path.write_text(answer, encoding="utf-8")
        successful = (
            result.returncode == 0
            and body.get("subtype") == "success"
            and not body.get("is_error")
            and bool(answer)
            and bool(body.get("usage"))
        )
        grade = task.grader(answer) if successful else {
            "score": 0,
            "max_score": 0,
            "pass": False,
            "error": body.get("result") or "Claude did not return a successful JSON result",
        }
        semantic_grade, semantic_meta = semantic_judge(answer, grade, task.task_id) if successful else ({
            "score": 0, "max_score": grade.get("max_score", 0), "error": "no answer to judge"
        }, {})
        return {
            "model": model,
            "effort": effort,
            "family": task.family,
            "task_id": task.task_id,
            "run": run,
            "elapsed_s": elapsed,
            "exit_code": result.returncode,
            "answer": answer,
            "grade": grade,
            "semantic_grade": semantic_grade,
            "semantic_judge": semantic_meta,
            "usage": usage_summary(body, elapsed),
            "json_path": str(json_path),
            "answer_path": str(answer_path),
            "stop_reason": body.get("stop_reason"),
            "terminal_reason": body.get("terminal_reason"),
            "session_id": body.get("session_id"),
            "stderr_tail": result.stderr[-2000:],
            "blocker": blocker,
        }
    except Exception as exc:
        return {
            "model": model,
            "effort": effort,
            "family": task.family,
            "task_id": task.task_id,
            "run": run,
            "elapsed_s": round(time.monotonic() - started, 3),
            "exit_code": None,
            "answer": "",
            "grade": {"score": 0, "max_score": 0, "pass": False, "error": str(exc)},
            "usage": {},
            "json_path": str(json_path),
            "answer_path": str(answer_path),
            "stderr_tail": "",
            "blocker": None,
        }


def pause_for_blocker(
    state: dict[str, Any], record: dict[str, Any], key: str
) -> bool:
    blocker = record.get("blocker")
    if not blocker:
        error = record.get("grade", {}).get("error")
        body = {"is_error": True, "result": error}
        blocker = session_limit_blocker(body) or authentication_blocker(body)
    if not blocker:
        return False
    selectors = " ".join(
        f"--only-config {config_key(item['model'], item['effort'])}"
        for item in state.get("active_configs", [])
    )
    state["status"] = (
        "paused_authentication"
        if blocker["type"] == "claude_authentication"
        else "paused_session_limit"
    )
    state["blocker"] = {
        **blocker,
        "record_key": key,
        "paused_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "resume_command": (
            f"{sys.executable} {Path(__file__).resolve()} run --retry-failures"
            f"{(' ' + selectors) if selectors else ''}"
        ),
    }
    save_state(state)
    print(f"paused: {blocker['message']}", flush=True)
    return True


def execute_run(
    state: dict[str, Any], args: argparse.Namespace, model: str, effort: str,
    task: Any, run: int
) -> bool:
    key = record_key(model, effort, task.task_id, run)
    existing = state["records"].get(key)
    if args.retry_failures and existing and existing.get("grade", {}).get("error"):
        state.setdefault("failed_attempt_history", []).append(existing)
        del state["records"][key]
        save_state(state)
    if key not in state["records"]:
        state["records"][key] = run_once(model, effort, task, run)
        save_state(state)
    record = state["records"][key]
    print(
        f"    {task.task_id}: semantic={record.get('semantic_grade', {}).get('score')}/"
        f"{record.get('semantic_grade', {}).get('max_score')} elapsed={record['elapsed_s']:.1f}s "
        f"cost=${record.get('usage', {}).get('cost_usd', 0):.4f} "
        f"rate={record.get('usage', {}).get('effective_output_tokens_per_s')}",
        flush=True,
    )
    return not pause_for_blocker(state, record, key)


def run_campaign(args: argparse.Namespace) -> None:
    tasks = build_tasks()
    state = load_state()
    selected = [
        pair for pair in CONFIGS
        if not args.only_config or config_key(*pair) in args.only_config
    ]
    state["status"] = "running"
    state.pop("blocker", None)
    state["active_configs"] = [
        {"model": model, "effort": effort} for model, effort in selected
    ]
    state["policy"]["execution_order"] = (
        "one complete task-suite pass per selected config; all configs complete "
        "a pass before the next pass begins"
    )
    save_state(state)

    task_names = args.only_task or TASK_NAMES
    for run in range(args.start_run, args.start_run + args.passes):
        state["phase"] = f"pass_{run}"
        save_state(state)
        for config_index, (model, effort) in enumerate(selected, 1):
            print(
                f"[pass {run}] [{config_index}/{len(selected)}] Claude {model} {effort}",
                flush=True,
            )
            for task_name in task_names:
                if not execute_run(state, args, model, effort, tasks[task_name], run):
                    return

    if args.passes < 2:
        state["phase"] = "complete_after_requested_passes"
        state["status"] = "selection_complete"
        save_state(state)
        print(f"saved {STATE_PATH}", flush=True)
        return

    state["phase"] = "gated_pass_3"
    save_state(state)
    for config_index, (model, effort) in enumerate(selected, 1):
        print(f"[pass 3] [{config_index}/{len(selected)}] Claude {model} {effort}", flush=True)
        for task_name in TASK_NAMES:
            task = tasks[task_name]
            first = state["records"][record_key(model, effort, task.task_id, 1)]
            second = state["records"][record_key(model, effort, task.task_id, 2)]
            run_third, reason = should_run_third(first, second, args.force_three)
            gate_key = f"{config_key(model, effort)}:{task.task_id}"
            state["gates"][gate_key] = {"run_third": run_third, "reason": reason}
            save_state(state)
            if not run_third:
                print(f"    {task.task_id}: skip ({reason})", flush=True)
                continue
            if not execute_run(state, args, model, effort, task, 3):
                return
    state["status"] = "complete" if len(selected) == len(CONFIGS) else "selection_complete"
    save_state(state)
    print(f"saved {STATE_PATH}", flush=True)


def print_status() -> None:
    state = load_state()
    records = list(state.get("records", {}).values())
    print(json.dumps({
        "status": state.get("status"),
        "records": len(records),
        "successful": sum(1 for record in records if grader_signature(record) is not None),
        "third_runs": sum(1 for record in records if record.get("run") == 3),
        "cost_usd": round(sum(record.get("usage", {}).get("cost_usd", 0) for record in records), 4),
        "blocker": state.get("blocker"),
        "state_path": str(STATE_PATH),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=["run", "status"], default="run")
    parser.add_argument("--force-three", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--passes", type=int, choices=(1, 2), default=2)
    parser.add_argument("--start-run", type=int, default=1)
    parser.add_argument("--only-task", action="append", choices=TASK_NAMES)
    parser.add_argument(
        "--only-config",
        action="append",
        choices=[config_key(model, effort) for model, effort in CONFIGS],
        help="Run only this model:effort pair; repeat for multiple pairs.",
    )
    args = parser.parse_args()
    if args.command == "status":
        print_status()
    else:
        run_campaign(args)


if __name__ == "__main__":
    main()
