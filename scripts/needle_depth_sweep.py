#!/usr/bin/env python3
import argparse
import json
import random
import re
import string
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_SEED_PATHS = ["README.md", "docs"]
WORDS = [
    "amber",
    "atlas",
    "banyan",
    "cedar",
    "cobalt",
    "copper",
    "delta",
    "ember",
    "harbor",
    "indigo",
    "juniper",
    "lantern",
    "maple",
    "north",
    "onyx",
    "prairie",
    "quartz",
    "raven",
    "signal",
    "tundra",
    "violet",
    "willow",
]


SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*[^\s\"']+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{20,}"), "Bearer <REDACTED>"),
    (re.compile(r"(?i)(sk-[a-z0-9_-]{20,})"), "<REDACTED_OPENAI_KEY>"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "<REDACTED_LONG_TOKEN>"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "<REDACTED_HEX_TOKEN>"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "<REDACTED_PRIVATE_KEY>"),
]


def redact(text: str) -> str:
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def read_text_file(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    text = data.decode("utf-8", errors="ignore")
    return redact(text)


def load_seed_texts(seed_dirs: list[Path], max_files: int, max_file_bytes: int) -> list[str]:
    texts: list[str] = []
    paths: list[Path] = []
    for seed_dir in seed_dirs:
        expanded = seed_dir.expanduser()
        if expanded.is_file():
            paths.append(expanded)
        elif expanded.is_dir():
            for path in expanded.rglob("*"):
                if path.is_file() and not path.name.startswith("."):
                    paths.append(path)
        else:
            continue

    for path in sorted(paths)[:max_files]:
        text = read_text_file(path, max_file_bytes)
        if text.strip():
            texts.append(f"\n\n### SOURCE: {path}\n{text.strip()}\n")

    if texts:
        return texts

    fallback: list[str] = []
    for raw_path in DEFAULT_SEED_PATHS:
        path = Path(raw_path)
        if path.is_file():
            fallback.append(read_text_file(path, max_file_bytes))
        elif path.is_dir():
            for file_path in sorted(path.rglob("*"))[:max_files]:
                if file_path.is_file():
                    text = read_text_file(file_path, max_file_bytes)
                    if text.strip():
                        fallback.append(text)
    if fallback:
        return fallback

    return [
        "System event stream: service restarts, queue checkpoints, scheduler notes, and operator annotations.",
        "Maintenance ledger: daily status records, runtime observations, incident notes, and benign distractor facts.",
    ]


def chunk_texts(texts: list[str], chunk_chars: int) -> list[str]:
    chunks = []
    for text in texts:
        clean = re.sub(r"\s+", " ", text).strip()
        for start in range(0, len(clean), chunk_chars):
            chunk = clean[start : start + chunk_chars].strip()
            if len(chunk) >= 80:
                chunks.append(chunk)
    return chunks or texts


def synthetic_block(rng: random.Random, index: int) -> str:
    host = f"node-{rng.randrange(10, 99)}"
    service = rng.choice(["scheduler", "bridge", "cache", "worker", "notifier", "router"])
    code = f"{rng.choice(string.ascii_uppercase)}{rng.randrange(1000, 9999)}"
    status = rng.choice(["nominal", "delayed", "replayed", "degraded", "checked"])
    return (
        f"[synthetic-log-{index:05d}] {host} {service} status={status} "
        f"checkpoint={code} note=\"routine event with no benchmark answer\""
    )


def make_filler(chunks: list[str], target_chars: int, rng: random.Random) -> str:
    parts = []
    total = 0
    index = 0
    while total < target_chars:
        if chunks and rng.random() < 0.75:
            text = rng.choice(chunks)
        else:
            text = synthetic_block(rng, index)
        index += 1
        paragraph = f"\n\n{text}"
        parts.append(paragraph)
        total += len(paragraph)
    return "".join(parts)[:target_chars]


def phrase(rng: random.Random) -> str:
    return f"{rng.choice(WORDS)} {rng.choice(WORDS)}"


def build_needle(rng: random.Random, difficulty: str) -> tuple[str, dict[str, str], str]:
    packet = f"PKT-{rng.randrange(1000, 9999)}-{rng.choice(string.ascii_uppercase)}{rng.choice(string.ascii_uppercase)}"
    valve = f"VX-{rng.randrange(100, 999)}"
    corridor = f"{rng.choice(['CEDAR', 'MAPLE', 'ONYX', 'RAVEN', 'HARBOR'])}-{rng.randrange(10, 99)}"
    override = phrase(rng)
    tier = rng.choice(["green", "amber", "red", "violet"])
    decoy_packet = packet.replace(packet[-1], rng.choice([c for c in string.ascii_uppercase if c != packet[-1]]))
    old_valve = f"VX-{rng.randrange(100, 999)}"

    if difficulty == "single":
        expected = {"packet": packet, "recovery_valve": valve}
        needle = (
            "NEEDLE RECORD - CURRENT OPERATIONS MEMO\n"
            f"Audit packet {packet} has current approved recovery valve {valve}.\n"
        )
    elif difficulty == "multi":
        expected = {
            "packet": packet,
            "recovery_valve": valve,
            "fallback_corridor": corridor,
            "override_phrase": override,
        }
        needle = (
            "NEEDLE RECORD - CURRENT OPERATIONS MEMO\n"
            f"For audit packet {packet}, the approved recovery valve is {valve}, "
            f"the fallback corridor is {corridor}, and the override phrase is \"{override}\".\n"
        )
    elif difficulty == "decoy":
        expected = {
            "packet": packet,
            "recovery_valve": valve,
            "fallback_corridor": corridor,
            "override_phrase": override,
        }
        needle = (
            "NEEDLE RECORD - SUPERSESSION MEMO\n"
            f"Historical entry: audit packet {packet} previously used recovery valve {old_valve}; revoked.\n"
            f"Nearby packet {decoy_packet} currently uses recovery valve VX-{rng.randrange(100, 999)}.\n"
            f"Current entry: audit packet {packet} now uses recovery valve {valve}, "
            f"fallback corridor {corridor}, and override phrase \"{override}\".\n"
            "Use the current entry, not historical or nearby packet entries.\n"
        )
    elif difficulty == "reasoning":
        expected = {
            "packet": packet,
            "recovery_valve": valve,
            "risk_tier": tier,
        }
        needle = (
            "NEEDLE RECORD - CROSS REFERENCE MEMO\n"
            f"Audit packet {packet} is assigned recovery valve {valve}.\n"
            f"Valve risk table: valve {valve} maps to risk tier {tier}.\n"
            f"Nearby packet {decoy_packet} maps to risk tier {rng.choice(['green', 'amber', 'red', 'violet'])}.\n"
        )
    else:
        raise ValueError(f"unknown difficulty: {difficulty}")

    if difficulty == "single":
        question = (
            f"For audit packet {packet}, what is the current approved recovery valve? "
            "Return JSON with keys packet and recovery_valve."
        )
    elif difficulty == "reasoning":
        question = (
            f"For audit packet {packet}, what recovery valve is assigned and what risk tier does that valve map to? "
            "Return JSON with keys packet, recovery_valve, and risk_tier."
        )
    else:
        question = (
            f"For audit packet {packet}, what are the current recovery valve, fallback corridor, and override phrase? "
            "Return JSON with keys packet, recovery_valve, fallback_corridor, and override_phrase."
        )
    return needle, expected, question


def build_prompt(
    chunks: list[str],
    context_target: int,
    depth: float,
    run_index: int,
    difficulty: str,
    seed: int,
    chars_per_token: float,
) -> tuple[str, dict[str, Any]]:
    rng = random.Random(seed + context_target * 1009 + int(depth * 1000) * 131 + run_index * 17)
    needle, expected, question = build_needle(rng, difficulty)
    target_haystack_chars = max(2000, int(context_target * chars_per_token))
    before_chars = int(target_haystack_chars * depth)
    after_chars = max(0, target_haystack_chars - before_chars - len(needle))
    before = make_filler(chunks, before_chars, rng)
    after = make_filler(chunks, after_chars, rng)
    haystack = f"{before}\n\n<<<BEGIN INSERTED PRIVATE AUDIT RECORD>>>\n{needle}<<<END INSERTED PRIVATE AUDIT RECORD>>>\n{after}"
    prompt = f"""/no_think

You are taking a private long-context retrieval test.

Rules:
- Use only the haystack below.
- The haystack contains private operational text plus one inserted private audit record.
- Ignore historical, revoked, nearby-packet, and unrelated entries unless the question asks for them.
- Return final JSON only. Do not include explanation, markdown, or extra keys.

<HAYSTACK>
{haystack}
</HAYSTACK>

Question: {question}
"""
    meta = {
        "expected": expected,
        "question": question,
        "needle": needle,
        "target_haystack_chars": target_haystack_chars,
        "prompt_chars": len(prompt),
        "seed": seed + context_target * 1009 + int(depth * 1000) * 131 + run_index * 17,
    }
    return prompt, meta


def extract_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    candidates = [stripped]
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def grade_answer(answer: str, expected: dict[str, str]) -> dict[str, Any]:
    parsed = extract_json(answer)
    checks = []
    score = 0
    normalized_answer = normalize(answer)
    for key, value in expected.items():
        expected_norm = normalize(value)
        parsed_value = normalize(parsed.get(key, "")) if parsed else ""
        passed = parsed_value == expected_norm or expected_norm in normalized_answer
        if passed:
            score += 1
        checks.append({"id": key, "expected": value, "parsed": parsed.get(key) if parsed else None, "pass": passed})
    return {
        "score": score,
        "max_score": len(expected),
        "pass": score == len(expected),
        "valid_json": parsed is not None,
        "checks": checks,
    }


def run_once(base_url: str, model: str, prompt: str, timeout: int, max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "cache_prompt": False,
    }
    start = time.perf_counter()
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json=payload,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]
    message = choice.get("message", {})
    content = message.get("content") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    answer = "\n".join(part for part in [reasoning.strip(), content.strip()] if part)
    return {
        "elapsed_s": elapsed,
        "answer": answer,
        "usage": body.get("usage") or {},
        "finish_reason": choice.get("finish_reason"),
    }


def summarize_context(results: list[dict[str, Any]], context_target: int) -> dict[str, Any]:
    skipped = [result for result in results if result["context_target"] == context_target and result.get("skipped")]
    if skipped:
        return {
            "context_target": context_target,
            "pass_count": None,
            "total": 0,
            "all_passed": None,
            "skipped": True,
            "reason": skipped[0].get("reason", "adaptive skip"),
        }
    matching = [result for result in results if result["context_target"] == context_target and not result.get("skipped")]
    if not matching:
        return {"context_target": context_target, "pass_count": 0, "total": 0, "all_passed": False, "skipped": False}
    pass_count = sum(1 for result in matching if result["grade"]["pass"])
    return {
        "context_target": context_target,
        "pass_count": pass_count,
        "total": len(matching),
        "all_passed": pass_count == len(matching),
        "skipped": False,
    }


def self_test() -> None:
    chunks = ["alpha beta gamma " * 200, "service log status nominal " * 200]
    prompt, meta = build_prompt(chunks, 1024, 0.5, 1, "decoy", 123, 4.0)
    assert "HAYSTACK" in prompt
    expected = meta["expected"]
    answer = json.dumps(expected)
    grade = grade_answer(answer, expected)
    assert grade["pass"], grade
    bad = grade_answer("{}", expected)
    assert not bad["pass"], bad
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--label", default="unknown")
    parser.add_argument("--seed-dir", action="append", type=Path, default=[])
    parser.add_argument("--ctx", nargs="+", type=int, default=[32768, 16384, 8192])
    parser.add_argument("--depth", nargs="+", type=float, default=[0.1, 0.5, 0.9])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--difficulty", choices=["single", "multi", "decoy", "reasoning"], default="decoy")
    parser.add_argument("--adaptive", action="store_true")
    parser.add_argument("--chars-per-token", type=float, default=3.7)
    parser.add_argument("--max-files", type=int, default=400)
    parser.add_argument("--max-file-bytes", type=int, default=512_000)
    parser.add_argument("--seed", type=int, default=20260703)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.base_url or not args.model or not args.out:
        parser.error("--base-url, --model, and --out are required unless --self-test is used")

    seed_dirs = args.seed_dir or [Path(path) for path in DEFAULT_SEED_PATHS]
    texts = load_seed_texts(seed_dirs, args.max_files, args.max_file_bytes)
    chunks = chunk_texts(texts, 1800)
    context_targets = sorted(args.ctx, reverse=args.adaptive)
    depths = args.depth
    results: list[dict[str, Any]] = []
    skipped_contexts: list[int] = []

    for context_target in context_targets:
        context_results_before = len(results)
        print(f"context {context_target}: depths={depths} runs={args.runs}", flush=True)
        for depth in depths:
            for run_index in range(1, args.runs + 1):
                prompt, meta = build_prompt(
                    chunks=chunks,
                    context_target=context_target,
                    depth=depth,
                    run_index=run_index,
                    difficulty=args.difficulty,
                    seed=args.seed,
                    chars_per_token=args.chars_per_token,
                )
                print(
                    f"  ctx={context_target} depth={depth:.2f} run={run_index}/{args.runs} "
                    f"prompt chars={len(prompt)}",
                    flush=True,
                )
                response = run_once(args.base_url, args.model, prompt, args.timeout, args.max_tokens)
                grade = grade_answer(response["answer"], meta["expected"])
                row = {
                    "label": args.label,
                    "model": args.model,
                    "context_target": context_target,
                    "depth": depth,
                    "run": run_index,
                    "difficulty": args.difficulty,
                    "expected": meta["expected"],
                    "question": meta["question"],
                    "seed": meta["seed"],
                    "prompt_chars": meta["prompt_chars"],
                    "target_haystack_chars": meta["target_haystack_chars"],
                    "answer": response["answer"],
                    "elapsed_s": response["elapsed_s"],
                    "usage": response["usage"],
                    "finish_reason": response["finish_reason"],
                    "grade": grade,
                }
                results.append(row)
                print(
                    f"    score={grade['score']}/{grade['max_score']} pass={grade['pass']} "
                    f"json={grade['valid_json']} elapsed={response['elapsed_s']:.2f}s "
                    f"answer={response['answer'][:120]!r}",
                    flush=True,
                )

        context_rows = results[context_results_before:]
        context_passed = all(row["grade"]["pass"] for row in context_rows)
        if args.adaptive and context_passed:
            lower_contexts = [ctx for ctx in context_targets if ctx < context_target]
            for skipped in lower_contexts:
                skipped_contexts.append(skipped)
                results.append(
                    {
                        "label": args.label,
                        "model": args.model,
                        "context_target": skipped,
                        "difficulty": args.difficulty,
                        "skipped": True,
                        "reason": f"adaptive skip: passed all runs at {context_target}",
                    }
                )
            break

    summaries = [summarize_context(results, ctx) for ctx in context_targets]
    report = {
        "label": args.label,
        "model": args.model,
        "difficulty": args.difficulty,
        "adaptive": args.adaptive,
        "contexts": context_targets,
        "depths": depths,
        "runs_per_depth": args.runs,
        "seed_dirs": [str(path.expanduser()) for path in seed_dirs],
        "seed_text_count": len(texts),
        "chunk_count": len(chunks),
        "skipped_contexts": skipped_contexts,
        "summary": summaries,
        "results": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
