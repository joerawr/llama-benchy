#!/usr/bin/env python3
"""Rescore retained archived answers with the calibrated semantic judge.

The run is resumable: one JSON artifact is written per catalog record, so an
interrupted or quota-limited run can continue without repeating completed work.
"""

from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path

from semantic_judge import JUDGE_PROTOCOL, judge_answer
from task_context import resolve_task_context


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "results/archived-rescore-catalog-20260716.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/semantic-rescore-source-aware-v2")
    parser.add_argument("--judge-model", default="gpt-5.6-luna")
    parser.add_argument("--judge-effort", default="xhigh", choices=("low", "medium", "high", "xhigh"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    records = catalog["records"][:args.limit] if args.limit else catalog["records"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.json"
    completed = 0
    total_input = total_output = 0

    for index, record in enumerate(records, 1):
        task = resolve_task_context(record["task_id"], record)
        key = record["fingerprint"]
        output_path = args.output_dir / f"{key}.json"
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            existing_judge = existing.get("semantic_judge", {})
            if (
                (existing.get("semantic_grade") or {}).get("score") is not None
                and existing_judge.get("task_prompt_sha256") == hashlib.sha256(task.prompt.encode()).hexdigest()
                and existing_judge.get("judge_protocol") == JUDGE_PROTOCOL
                and existing_judge.get("judge_model") == args.judge_model
                and existing_judge.get("judge_effort") == args.judge_effort
            ):
                completed += 1
                continue
        diagnostic_grade = task.grader(record.get("answer", ""))
        judgment, judge_meta = judge_answer(
            record.get("answer", ""), diagnostic_grade, record["task_id"],
            task_prompt=task.prompt, finish_reason=record.get("finish_reason"),
            judge_model=args.judge_model, judge_effort=args.judge_effort,
        )
        judge_meta["source_context_status"] = "matched_saved_hash" if record.get("semantic_judge", {}).get("task_prompt_sha256") else "reconstructed_1.1_unverified_original"
        item = {
            "catalog_fingerprint": key,
            "provider": record["provider"], "model": record["model"],
            "effort": record["effort"], "task_id": record["task_id"],
            "run": record.get("run"), "source": record["source"],
            "diagnostic_score": diagnostic_grade.get("score"),
            "diagnostic_max_score": diagnostic_grade.get("max_score"),
            "judge_model": args.judge_model, "judge_effort": args.judge_effort,
            "semantic_grade": judgment, "semantic_judge": judge_meta,
        }
        output_path.write_text(json.dumps(item, indent=2), encoding="utf-8")
        completed += 1
        total_input += int(judge_meta.get("usage", {}).get("input_tokens", 0) or 0)
        total_output += int(judge_meta.get("usage", {}).get("output_tokens", 0) or 0)
        print(json.dumps({"index": index, "total": len(records), "file": output_path.name,
                          "ok": True}), flush=True)

    summary = {
        "catalog": str(args.catalog), "judge_protocol": JUDGE_PROTOCOL,
        "judge_model": args.judge_model,
        "judge_effort": args.judge_effort, "requested": len(records),
        "completed": completed,
        "input_tokens_new": total_input, "output_tokens_new": total_output,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
