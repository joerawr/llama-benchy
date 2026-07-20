#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


QUESTION = (
    "In the hidden markdown note, what is the default value for Parameter 12 "
    "'On Off Status After Power Failure', and what does that value mean? "
    "Answer with only the value and its meaning."
)


def build_hackstack(needle: str, distractor: str, run_index: int) -> str:
    positions = [(2, 5), (4, 3), (6, 1)]
    before_count, after_count = positions[run_index % len(positions)]
    before = (distractor + "\n\n") * before_count
    after = ("\n\n" + distractor) * after_count
    return f"""You are taking a needle-in-a-hackstack retrieval test.

Rules:
- The context below contains distractor material and exactly one hidden markdown note.
- Use only the hidden markdown note to answer the question.
- Do not answer from memory.
- Keep internal reasoning short and provide the final answer directly.

<HACKSTACK>
{before}

<<<BEGIN HIDDEN MARKDOWN NOTE>>>
{needle}
<<<END HIDDEN MARKDOWN NOTE>>>

{after}
</HACKSTACK>

Question: {QUESTION}
"""


def grade(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return (
        "3" in normalized
        and "remember" in normalized
        and "restore" in normalized
        and "dimmer" in normalized
        and "relay" in normalized
    )


def run_once(base_url: str, model: str, prompt: str, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 512,
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
    usage = body.get("usage") or {}
    return {
        "elapsed_s": elapsed,
        "answer": answer,
        "pass": grade(answer),
        "usage": usage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--needle", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    needle_path = Path(args.needle).expanduser()
    needle = needle_path.read_text(encoding="utf-8")
    distractor = Path("README.md").read_text(encoding="utf-8")[:3000]

    results = []
    for index in range(args.runs):
        prompt = build_hackstack(needle, distractor, index)
        print(f"run {index + 1}/{args.runs}: prompt chars={len(prompt)}", flush=True)
        result = run_once(args.base_url, args.model, prompt, args.timeout)
        result["run"] = index + 1
        print(
            f"  pass={result['pass']} elapsed={result['elapsed_s']:.2f}s "
            f"answer={result['answer'][:160]!r}",
            flush=True,
        )
        results.append(result)

    report = {
        "label": args.label,
        "model": args.model,
        "needle": str(needle_path),
        "question": QUESTION,
        "runs": results,
        "pass_count": sum(1 for result in results if result["pass"]),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
