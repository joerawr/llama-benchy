#!/usr/bin/env python3
"""Run a fresh, side-by-side Luna high/xhigh Finance comparison."""

from __future__ import annotations

import json
from pathlib import Path

from codex_gap_campaign import build_tasks, run_once


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "codex-finance-luna-high-xhigh-20260716.json"


def main() -> None:
    task = build_tasks()["finance"]
    records = [
        run_once("gpt-5.6-luna", effort, task, 1, 0, "-fresh-20260716")
        for effort in ("high", "xhigh")
    ]
    OUTPUT.write_text(json.dumps({"task": "finance", "records": records}, indent=2))
    for record in records:
        print(
            f"{record['model']} {record['effort']}: "
            f"{record['grade'].get('score')}/{record['grade'].get('max_score')} "
            f"elapsed={record['elapsed_s']:.1f}s "
            f"output={record.get('usage', {}).get('output_tokens')} "
            f"reasoning={record.get('usage', {}).get('reasoning_output_tokens')}"
        )
    print(f"saved {OUTPUT}")


if __name__ == "__main__":
    main()
