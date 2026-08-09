#!/usr/bin/env python3
"""Run the shared quality suite through OpenRouter's OpenAI-compatible API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from codex_gap_campaign import (
    NEUTRAL_WRAPPER,
    ROOT,
    atomic_write_json,
    build_tasks,
    grader_signature,
    semantic_judge,
    should_run_third,
)


DATE_TAG = time.strftime("%Y%m%d")
STATE_PATH = Path(
    os.environ.get(
        "OPENROUTER_CAMPAIGN_STATE",
        ROOT / "results" / f"openrouter-apples-campaign-{DATE_TAG}.json",
    )
)
EVENT_DIR = Path(
    os.environ.get(
        "OPENROUTER_CAMPAIGN_EVENTS",
        ROOT / "results" / f"openrouter-apples-events-{DATE_TAG}",
    )
)
ENV_PATH = Path.home() / ".hermes" / ".env"
BASE_URL = "https://openrouter.ai/api/v1"
MAX_TOKENS = None

CONFIGS = [
    ("glm-5.2", "z-ai/glm-5.2", "high"),
    ("glm-5.2", "z-ai/glm-5.2", "xhigh"),
    ("kimi-k3", "moonshotai/kimi-k3", "low"),
    ("kimi-k3", "moonshotai/kimi-k3", "high"),
    ("kimi-k3", "moonshotai/kimi-k3", "max"),
    ("mercury-2", "inception/mercury-2:nitro", None),
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


def config_key(model: str, effort: str | None) -> str:
    return f"{model}:{effort}" if effort else model


def record_key(model: str, effort: str | None, task_id: str, run: int) -> str:
    return f"{config_key(model, effort)}:{task_id}:{run}"


def _env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def openrouter_api_key() -> str:
    value = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if value:
        return value
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(.*)\s*$", line)
            if match:
                value = _env_value(match.group(1))
                if value:
                    return value
    raise RuntimeError("OPENROUTER_API_KEY is not set in the environment or ~/.hermes/.env")


def initial_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign": "OpenRouter apples-to-apples quality comparison",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "updated_at": None,
        "status": "running",
        "provider": "OpenRouter",
        "policy": {
            "runs_before_gate": 2,
            "third_run": "only when complete semantic grader signatures differ or a run fails",
            "sequential": True,
            "reasoning_parameter": "reasoning.effort",
            "max_tokens": "provider default",
            "usage_source": "OpenRouter chat completions usage",
        },
        "configs": [
            {"model": model, "model_id": model_id, "effort": effort}
            for model, model_id, effort in CONFIGS
        ],
        "records": {},
        "gates": {},
    }


def load_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else initial_state()


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    atomic_write_json(STATE_PATH, state)


def usage_summary(response: Any, elapsed_s: float) -> dict[str, Any]:
    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
    details = usage.get("completion_tokens_details") or {}
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    reasoning_tokens = int(details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
    cost = usage.get("cost")
    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": int(usage.get("total_tokens") or 0),
        "cost_usd": float(cost) if cost is not None else None,
        "effective_output_tokens_per_s": round(output_tokens / elapsed_s, 3) if elapsed_s else None,
        "effective_visible_tokens_per_s": round(max(0, output_tokens - reasoning_tokens) / elapsed_s, 3)
        if elapsed_s else None,
        "raw": usage,
    }


def run_once(
    model: str,
    model_id: str,
    effort: str | None,
    task: Any,
    run: int,
    max_tokens: int | None = MAX_TOKENS,
) -> dict[str, Any]:
    slug = f"openrouter-{model}-{effort}-{task.task_id}-run{run}"
    answer_path = EVENT_DIR / f"{slug}.md"
    record_path = EVENT_DIR / f"{slug}.json"
    EVENT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        client = OpenAI(
            api_key=openrouter_api_key(),
            base_url=BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/joerawr/llama-benchy",
                "X-OpenRouter-Title": "llama-benchy",
            },
        )
        request = {
            "model": model_id,
            "messages": [{"role": "user", "content": NEUTRAL_WRAPPER + task.prompt}],
        }
        if effort:
            request["extra_body"] = {"reasoning": {"effort": effort}}
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        response = client.chat.completions.create(**request)
        elapsed = round(time.monotonic() - started, 3)
        message = response.choices[0].message
        answer = message.content or ""
        usage = usage_summary(response, elapsed)
        diagnostic_grade = task.grader(answer) if answer else {
            "score": 0,
            "max_score": 0,
            "pass": False,
            "error": "OpenRouter returned an empty answer",
        }
        semantic_grade, semantic_meta = semantic_judge(answer, diagnostic_grade, task.task_id) if answer else ({
            "score": 0,
            "max_score": diagnostic_grade.get("max_score", 0),
            "error": "no answer to judge",
        }, {})
        record = {
            "provider": "OpenRouter",
            "model": model,
            "model_id": model_id,
            "effort": effort,
            "family": task.family,
            "task_id": task.task_id,
            "run": run,
            "max_tokens": max_tokens,
            "elapsed_s": elapsed,
            "exit_code": 0,
            "answer": answer,
            "diagnostic_grade": diagnostic_grade,
            "semantic_grade": semantic_grade,
            "semantic_judge": semantic_meta,
            "usage": usage,
            "answer_path": str(answer_path),
            "record_path": str(record_path),
            "finish_reason": response.choices[0].finish_reason,
        }
        answer_path.write_text(answer, encoding="utf-8")
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record
    except Exception as exc:
        record = {
            "provider": "OpenRouter",
            "model": model,
            "model_id": model_id,
            "effort": effort,
            "family": task.family,
            "task_id": task.task_id,
            "run": run,
            "max_tokens": max_tokens,
            "elapsed_s": round(time.monotonic() - started, 3),
            "exit_code": None,
            "answer": "",
            "diagnostic_grade": {"score": 0, "max_score": 0, "pass": False, "error": str(exc)},
            "usage": {},
            "answer_path": str(answer_path),
            "record_path": str(record_path),
        }
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record


def run_campaign(args: argparse.Namespace) -> None:
    tasks = build_tasks()
    state = load_state()
    state.setdefault("policy", {})["max_tokens"] = args.max_tokens
    selected = [config for config in CONFIGS if not args.only_config or config_key(config[0], config[2]) in args.only_config]
    state["configs"] = [
        {"model": model, "model_id": model_id, "effort": effort}
        for model, model_id, effort in selected
    ]
    state["status"] = "running"
    save_state(state)
    task_names = args.only_task or TASK_NAMES
    for run in range(1, args.passes + 1):
        for model, model_id, effort in selected:
            print(f"[pass {run}] OpenRouter {model} {effort or 'provider-default'}", flush=True)
            for task_name in task_names:
                task = tasks[task_name]
                key = record_key(model, effort, task.task_id, run)
                if (
                    key not in state["records"]
                    or args.rerun
                    or args.retry_failures
                    and state["records"][key].get("diagnostic_grade", {}).get("error")
                ):
                    state["records"][key] = run_once(
                        model, model_id, effort, task, run, args.max_tokens
                    )
                    save_state(state)
                record = state["records"][key]
                print(
                    f"  {task.task_id}: semantic={record.get('semantic_grade', {}).get('score')}/"
                    f"{record.get('semantic_grade', {}).get('max_score')} elapsed={record['elapsed_s']:.1f}s "
                    f"output_rate={record.get('usage', {}).get('effective_output_tokens_per_s')} "
                    f"cost={record.get('usage', {}).get('cost_usd')}",
                    flush=True,
                )
    if args.passes >= 2 and not args.no_third:
        for model, _, effort in selected:
            for task_name in task_names:
                task = tasks[task_name]
                first = state["records"][record_key(model, effort, task.task_id, 1)]
                second = state["records"][record_key(model, effort, task.task_id, 2)]
                run_third, reason = should_run_third(first, second, args.force_three)
                gate_key = f"{config_key(model, effort)}:{task.task_id}"
                state["gates"][gate_key] = {"run_third": run_third, "reason": reason}
                save_state(state)
                if run_third:
                    model_id = next(item[1] for item in CONFIGS if item[0] == model and item[2] == effort)
                    key = record_key(model, effort, task.task_id, 3)
                    if key not in state["records"] or (
                        args.retry_failures and not grader_signature(state["records"][key])
                    ):
                        state["records"][key] = run_once(
                            model, model_id, effort, task, 3, args.max_tokens
                        )
                        save_state(state)
                    record = state["records"][key]
                    print(
                        f"  {task.task_id} run 3: semantic={record.get('semantic_grade', {}).get('score')}/"
                        f"{record.get('semantic_grade', {}).get('max_score')} reason={reason}",
                        flush=True,
                    )
                else:
                    print(f"  {task.task_id}: skip run 3 ({reason})", flush=True)
    state["status"] = "complete"
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
        "state_path": str(STATE_PATH),
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("run", "status"), default="run")
    parser.add_argument("--only-config", action="append", choices=[config_key(c[0], c[2]) for c in CONFIGS])
    parser.add_argument("--only-task", action="append", choices=TASK_NAMES)
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--force-three", action="store_true")
    parser.add_argument("--no-third", action="store_true")
    parser.add_argument("--passes", type=int, choices=(1, 2), default=2)
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    args = parser.parse_args()
    if args.command == "status":
        print_status()
        return
    try:
        run_campaign(args)
    except KeyboardInterrupt:
        state = load_state()
        state["status"] = "interrupted"
        save_state(state)
        print(f"interrupted; saved {STATE_PATH}", file=sys.stderr, flush=True)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
