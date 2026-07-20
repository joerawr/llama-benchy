#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTED = ROOT / "benchy-state" / "tested-models.json"


def run_json(cmd: list[str], timeout_s: int = 120) -> Any:
    completed = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return []
    return json.loads(stdout)


def load_tested(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    repos = set()
    for item in data.get("models", []):
        repo = item.get("repo")
        if repo:
            repos.add(repo.lower())
    return repos


def model_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("modelId") or item.get("repo_id") or "")


def interesting_hint(repo_id: str, tags: list[str]) -> list[str]:
    haystack = " ".join([repo_id, *tags]).lower()
    hints = []
    for needle, label in [
        ("gguf", "gguf"),
        ("moe", "moe"),
        ("a3b", "low-active-moe"),
        ("a4b", "low-active-moe"),
        ("12b", "dense-12b"),
        ("9b", "dense-9b"),
        ("qat", "qat"),
        ("imatrix", "imatrix"),
        ("qwen", "qwen-family"),
        ("gemma", "gemma-family"),
        ("glm", "glm-family"),
        ("mistral", "mistral-family"),
        ("mixtral", "mixtral-family"),
    ]:
        if needle in haystack and label not in hints:
            hints.append(label)
    return hints


def list_models(library: str, sort: str, limit: int) -> list[dict[str, Any]]:
    """List models from a Hugging Face library filter and ordering."""
    return run_json(
        [
            "hf",
            "models",
            "list",
            "--filter",
            library,
            "--sort",
            sort,
            "--limit",
            str(limit),
            "--expand",
            "downloads,likes,tags,lastModified,createdAt,trendingScore,pipeline_tag",
            "--format",
            "json",
        ]
    )


def list_gguf_files(repo_id: str) -> list[dict[str, str]]:
    try:
        files = run_json(
            [
                "hf",
                "download",
                repo_id,
                "--include",
                "*.gguf",
                "--dry-run",
                "--format",
                "json",
            ],
            timeout_s=180,
        )
    except Exception as exc:  # noqa: BLE001 - include metadata error for agent review
        return [{"error": str(exc)}]

    useful = []
    for item in files:
        name = str(item.get("file", ""))
        if is_min_q4_model_file(name):
            useful.append({"file": name, "size": str(item.get("size", ""))})
    return useful[:20]


def is_min_q4_model_file(name: str) -> bool:
    lower = name.lower()
    if "mmproj" in lower:
        return False
    if any(token in lower for token in ["q1", "q2", "q3", "iq1", "iq2", "iq3"]):
        return False
    if any(token in lower for token in ["q4", "q5", "q6", "q8", "iq4", "mxfp4", "fp4", "4bit"]):
        return True
    match = re.search(r"bpw([0-9]+(?:\.[0-9]+)?)", lower)
    return bool(match and float(match.group(1)) >= 4.0)


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def file_enrichment_score(entry: dict[str, Any]) -> float:
    if entry.get("already_tested"):
        return -1_000_000

    repo_id = str(entry.get("id") or "").lower()
    hints = set(entry.get("hints") or [])
    pipeline = entry.get("pipeline_tag")
    score = 0.0

    if pipeline in (None, "", "text-generation", "image-text-to-text"):
        score += 20
    else:
        score -= 35

    for hint, weight in [
        ("low-active-moe", 36),
        ("dense-12b", 30),
        ("dense-9b", 24),
        ("qat", 24),
        ("moe", 12),
        ("imatrix", 10),
        ("gemma-family", 10),
        ("qwen-family", 10),
        ("glm-family", 4),
        ("mistral-family", 4),
        ("mixtral-family", 4),
    ]:
        if hint in hints:
            score += weight

    for token, penalty in [
        ("embedding", 40),
        ("vl-", 18),
        ("vision", 18),
        ("ocr", 18),
        ("uncensored", 14),
        ("coder", 8),
        ("legal", 8),
        ("security", 8),
        ("roleplay", 8),
    ]:
        if token in repo_id:
            score -= penalty

    score += min(as_float(entry.get("trendingScore")), 100.0) / 10.0
    score += min(as_int(entry.get("likes")), 500) / 100.0
    score += min(as_int(entry.get("downloads")), 500_000) / 100_000.0
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--file-limit", type=int, default=12)
    parser.add_argument("--tested", type=Path, default=DEFAULT_TESTED)
    args = parser.parse_args()

    tested = load_tested(args.tested)
    merged: dict[str, dict[str, Any]] = {}
    errors = []
    # Mirror the HF browsing workflow: inspect Trending MLX first for Apple-Silicon-native
    # candidates, then Trending GGUF for llama.cpp candidates.  Fresh/most-downloaded GGUF
    # supplements the trending view without replacing it.
    sources = [
        ("mlx", "trending_score"),
        ("gguf", "trending_score"),
        ("gguf", "last_modified"),
        ("gguf", "downloads"),
    ]
    for library, sort in sources:
        source_label = f"{library}:{sort}"
        try:
            rows = list_models(library, sort, args.limit)
        except Exception as exc:  # noqa: BLE001 - capture source failure in report
            errors.append({"source": source_label, "error": str(exc)})
            continue
        for item in rows:
            repo_id = model_id(item)
            if not repo_id:
                continue
            entry = merged.setdefault(repo_id, {"id": repo_id, "sources": [], "libraries": []})
            entry["sources"].append(source_label)
            if library not in entry["libraries"]:
                entry["libraries"].append(library)
            for key in ["downloads", "likes", "tags", "lastModified", "createdAt", "trendingScore", "pipeline_tag"]:
                if key in item:
                    entry[key] = item[key]

    candidates = []
    for repo_id, entry in merged.items():
        tags = entry.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        hints = interesting_hint(repo_id, [str(tag) for tag in tags])
        entry["already_tested"] = repo_id.lower() in tested
        entry["hints"] = hints
        entry["file_enrichment_score"] = round(file_enrichment_score(entry), 3)
        candidates.append(entry)

    candidates.sort(
        key=lambda item: (
            item.get("already_tested", False),
            -float(item.get("trendingScore") or 0),
            -int(item.get("downloads") or 0),
        )
    )

    files_added = 0
    enrichment_order = sorted(
        candidates,
        key=lambda item: (
            -file_enrichment_score(item),
            -float(item.get("trendingScore") or 0),
            -int(item.get("downloads") or 0),
            item.get("id", ""),
        ),
    )
    for entry in enrichment_order:
        if files_added >= args.file_limit:
            break
        if entry.get("already_tested"):
            continue
        if not entry.get("hints"):
            continue
        # The llama.cpp benchmark path needs a GGUF file. MLX trending candidates
        # remain visible to the selector but are not probed with a GGUF-only download.
        if "gguf" not in entry.get("libraries", []):
            continue
        entry["candidate_files"] = list_gguf_files(entry["id"])
        files_added += 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "selection_note": "This script gathers metadata only. Codex chooses whether to test a model.",
        "errors": errors,
        "candidates": candidates,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved {out_path} candidates={len(candidates)} files_added={files_added}")


if __name__ == "__main__":
    main()
