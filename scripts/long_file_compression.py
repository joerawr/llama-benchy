#!/usr/bin/env python3
import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests


PROMPT_TEMPLATE = """/no_think

You are compressing a markdown research note for an investing agent.

Instructions:
- Use only the note below.
- Preserve uncertainty. Mark rumors, social chatter, and unverified claims as such.
- Do not invent companies, dates, numbers, sources, or market conclusions.
- Return the final answer only. Do not include thinking, reasoning, analysis notes, scratch work, or preambles.
- Be dense and useful, not verbose.

Return exactly these sections:
1. Executive brief: 90-130 words.
2. Key facts: 8 bullets, each with a concrete fact, date, number, source type, or named entity when available.
3. Investment implications: split into Opportunities and Risks.
4. Verify before acting: 4 bullets.

<MARKDOWN_NOTE>
{note}
</MARKDOWN_NOTE>
"""


RUBRIC = [
    {
        "id": "access_risk_thesis",
        "description": "Frames the thesis as frontier-AI access/jurisdiction/policy risk, not only model quality.",
        "patterns": [r"access risk|access[- ]?risk", r"jurisdiction|policy|export-control|export control|regulated infrastructure"],
    },
    {
        "id": "fable_mythos_export_control",
        "description": "Mentions Fable 5 and Mythos 5 suspension under US government/export-control pressure.",
        "patterns": [r"fable 5", r"mythos 5", r"export-control|export control|US government|government directive|government pressure"],
    },
    {
        "id": "api_access_not_chips",
        "description": "Notes the precedent applies to model/API access, not just chips or infrastructure.",
        "patterns": [r"API access|model access", r"chips|data centers|training infrastructure|infrastructure"],
    },
    {
        "id": "mythos_partial_restore",
        "description": "Captures partial Mythos 5 restoration for about 100 US government/critical-infrastructure organizations.",
        "patterns": [r"mythos 5", r"100|hundred", r"critical infrastructure|government"],
    },
    {
        "id": "gpt56_uncertain_rollout",
        "description": "Treats GPT-5.6 as rollout anxiety/community framing rather than confirmed benchmark fact.",
        "patterns": [r"gpt-?5\.6", r"rumou?r|community|anxiety|unconfirmed|not confirmed|less about confirmed|rollout"],
    },
    {
        "id": "glm_open_weight_hedge",
        "description": "Explains GLM-5.2 as a credible open-weight/local hedge against US access risk.",
        "patterns": [r"glm-?5\.2", r"open[- ]weight|local|deployable", r"hedge|alternative|insurance|resilience"],
    },
    {
        "id": "glm_social_benchmark_specifics",
        "description": "Includes concrete GLM-5.2 support evidence such as LocalLLaMA 1,188 points/307 comments or Artificial Analysis ranking.",
        "patterns": [r"1,?188|307|Artificial Analysis|Intelligence Index|LocalLLaMA"],
    },
    {
        "id": "sovereign_ai_definition",
        "description": "Defines sovereign AI as capacity that cannot be switched off by another country's regulator.",
        "patterns": [r"sovereign AI", r"switched off|regulator|another country|foreign regulator|jurisdiction"],
    },
    {
        "id": "polymarket_numbers",
        "description": "Preserves Polymarket signals: 98% US restoration and 17% foreign-use ban rescission.",
        "patterns": [r"98\s*%", r"17\s*%", r"Polymarket"],
    },
    {
        "id": "four_hypotheses_or_surfaces",
        "description": "Names multiple investable surfaces: open-weight ecosystems, local inference/private labs, segmentation/compliance, sovereign/private cloud or eval tooling.",
        "patterns": [
            r"open[- ]weight",
            r"local inference|private AI|on-prem|workstations|GPU rentals",
            r"segmentation|compliance|trusted partner|critical infrastructure",
            r"sovereign|private AI cloud|eval|red-team|audit|model-routing|routing",
        ],
    },
    {
        "id": "caveats",
        "description": "Includes caveats about social-source concentration, GPT-5.6 uncertainty, GLM eval brittleness, sovereign-AI vaporware, or adoption constraints.",
        "patterns": [
            r"Reddit|X|social",
            r"GPT-?5\.6.*(rumou?r|unconfirmed|uncertain)|rumou?r.*GPT-?5\.6",
            r"brittleness|real-world eval|enthusiasm may fade",
            r"vaporware|licensing|hardware|support|safety|export",
        ],
    },
    {
        "id": "no_bad_core_inversion",
        "description": "Does not invert core facts by saying foreign access normalized, GLM must beat closed labs everywhere, or Fable 5 was fully restored.",
        "negative_patterns": [
            r"foreign access (?:was |is )?(?:normalized|restored)",
            r"GLM-?5\.2 (?:must|needs to) beat (?:OpenAI|Anthropic)",
            r"Fable 5 (?:was |is )?(?:fully|publicly|generally) restored",
        ],
    },
]


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def section_count(text: str) -> int:
    return sum(
        1
        for pattern in [
            r"executive brief",
            r"key facts",
            r"investment implications",
            r"opportunities",
            r"risks",
            r"verify before acting",
        ]
        if re.search(pattern, text, flags=re.IGNORECASE)
    )


def grade(text: str) -> dict[str, Any]:
    checks = []
    for item in RUBRIC:
        passed = True
        if "patterns" in item:
            passed = all(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in item["patterns"])
        if "negative_patterns" in item:
            passed = not any(
                re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
                for pattern in item["negative_patterns"]
            )
        checks.append({**item, "pass": passed})

    word_count = len(re.findall(r"\b\w+\b", text))
    structure_pass = section_count(text) >= 5
    score = sum(1 for check in checks if check["pass"])
    return {
        "score": score,
        "max_score": len(checks),
        "word_count": word_count,
        "structure_pass": structure_pass,
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
    usage = body.get("usage") or {}
    return {
        "elapsed_s": elapsed,
        "answer": answer,
        "grade": grade(answer),
        "usage": usage,
        "finish_reason": choice.get("finish_reason"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-tokens", type=int, default=1600)
    args = parser.parse_args()

    note_path = Path(args.note).expanduser()
    note = note_path.read_text(encoding="utf-8")
    prompt = PROMPT_TEMPLATE.format(note=note)

    results = []
    for index in range(args.runs):
        print(f"run {index + 1}/{args.runs}: prompt chars={len(prompt)}", flush=True)
        result = run_once(args.base_url, args.model, prompt, args.timeout, args.max_tokens)
        result["run"] = index + 1
        grade_result = result["grade"]
        print(
            f"  score={grade_result['score']}/{grade_result['max_score']} "
            f"structure={grade_result['structure_pass']} elapsed={result['elapsed_s']:.2f}s "
            f"finish={result['finish_reason']}",
            flush=True,
        )
        print(f"  answer={result['answer'][:180]!r}", flush=True)
        results.append(result)

    scores = [result["grade"]["score"] for result in results]
    report = {
        "label": args.label,
        "model": args.model,
        "note": str(note_path),
        "prompt_chars": len(prompt),
        "rubric": RUBRIC,
        "runs": results,
        "score_summary": {
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "avg": sum(scores) / len(scores) if scores else None,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
