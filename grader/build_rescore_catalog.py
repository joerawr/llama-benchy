#!/usr/bin/env python3
"""Catalog and deduplicate archived Codex/Claude candidate answers."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "archived-rescore-catalog-20260716.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def add_record(records: list[dict], provider: str, source: Path, record: dict, model: str | None = None, effort: str | None = None) -> None:
    grade = record.get("grade", {})
    answer = record.get("answer") or ""
    if not answer or not grade.get("max_score") or grade.get("error"):
        return
    resolved_model = model or record.get("model")
    resolved_effort = effort or record.get("effort") or record.get("mode")
    if provider == "Codex" and resolved_model is None:
        resolved_model = "gpt-5.6-luna"
    identity = f"{provider}|{resolved_model}|{resolved_effort}|{record.get('task_id')}|{answer}"
    records.append({
        "provider": provider,
        "model": resolved_model,
        "effort": resolved_effort,
        "task_id": record.get("task_id"),
        "run": record.get("run"),
        "score": grade.get("score"),
        "max_score": grade.get("max_score"),
        "checks": grade.get("checks", []),
        "answer": answer,
        "reference": grade.get("reference", {}),
        "source": str(source),
        "answer_path": record.get("answer_path") or record.get("event_path"),
        "fingerprint": hashlib.sha256(identity.encode()).hexdigest(),
    })


def main() -> None:
    records: list[dict] = []
    quality_sources = sorted((ROOT / "results").glob("codex-agent-quality-*.json"))
    for source in quality_sources:
        payload = load_json(source)
        for record in payload.get("records", []):
            inferred = None
            # This older file omitted model on every record, but contains
            # Luna low/medium only. Other mixed files carry model explicitly.
            if record.get("model") is None and source.name == "codex-agent-quality-luna-low-medium.json":
                inferred = "gpt-5.6-luna"
            add_record(records, "Codex", source, record, model=inferred)

    source = ROOT / "results" / "codex-apples-gap-campaign-20260714.json"
    payload = load_json(source)
    for record in payload.get("records", {}).values():
        add_record(records, "Codex", source, record)

    source = ROOT / "results" / "claude-apples-campaign-20260714.json"
    payload = load_json(source)
    for record in payload.get("records", {}).values():
        add_record(records, "Claude", source, record)

    unique: dict[str, dict] = {}
    for record in records:
        unique.setdefault(record["fingerprint"], record)

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for record in unique.values():
        groups[(record["provider"], record["model"], record["effort"], record["task_id"])].append(record)

    retained: list[dict] = []
    for key, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda item: (float(item["score"]), int(item.get("run") or 0), item["fingerprint"]))
        if len(ordered) >= 4:
            chosen = [ordered[0], ordered[-1]]
            for record in chosen:
                record["selection_reason"] = "retained low/high from 4+ clean passes"
        else:
            chosen = ordered
            for record in chosen:
                record["selection_reason"] = "retained; fewer than 4 clean passes"
        retained.extend(chosen)

    catalog = {
        "schema_version": 1,
        "created_at": "2026-07-16",
        "policy": {
            "valid": "non-empty answer with positive max_score and no grader error",
            "dedupe": "exact answer duplicates removed; for 4+ clean passes retain lowest and highest score",
            "raw_sources_untouched": True,
        },
        "candidate_count_before_dedupe": len(records),
        "candidate_count_after_exact_dedupe": len(unique),
        "retained_count": len(retained),
        "records": retained,
    }
    OUT.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUT),
        "before_dedupe": len(records),
        "after_exact_dedupe": len(unique),
        "retained": len(retained),
        "groups": len(groups),
    }, indent=2))


if __name__ == "__main__":
    main()
