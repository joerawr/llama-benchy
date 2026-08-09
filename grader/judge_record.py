#!/usr/bin/env python3
"""Judge one saved benchmark record with the dedicated grader instructions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from semantic_judge import judge_answer


ROOT = Path(__file__).resolve().parents[1]


def find_record(source: dict, args: argparse.Namespace) -> dict:
    records = source.get("records", [])
    if isinstance(records, dict):
        records = list(records.values())
    matches = [
        record for record in records
        if record.get("task_id") == args.task
        and record.get("run") == args.run
        and (record.get("effort") or record.get("mode")) == args.effort
        and (not args.model or record.get("model") in (args.model, None))
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one record, found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--model")
    parser.add_argument("--judge-model", default="gpt-5.6-luna")
    parser.add_argument("--judge-effort", default="low", choices=("low", "medium"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    record = find_record(source, args)
    diagnostic_grade = record.get("diagnostic_grade", record.get("grade", {}))
    semantic_grade, semantic_meta = judge_answer(
        record.get("answer", ""), diagnostic_grade, args.task,
        judge_model=args.judge_model, judge_effort=args.judge_effort,
    )
    output = {
        "source": str(args.source),
        "task": args.task,
        "candidate_model": record.get("model"),
        "candidate_effort": args.effort,
        "candidate_run": args.run,
        "diagnostic_grade": diagnostic_grade,
        "semantic_grade": semantic_grade,
        "semantic_judge": semantic_meta,
    }
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
