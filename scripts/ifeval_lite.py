#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from grader.semantic_judge import judge_result  # noqa: E402


@dataclass(frozen=True)
class Task:
    task_id: str
    prompt: str
    grader: Callable[[str], dict[str, Any]]


WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?")

CHECK_REQUIREMENTS = {
    "exactly_5_bullets": "Contains exactly five bullet lines.",
    "no_extra_text": "Contains no text outside the requested bullets.",
    "bullet_word_counts_9_to_13": "Each of the five bullets contains 9 to 13 words, inclusive.",
    "offline_once_total": "Uses the word 'offline' exactly once in the entire answer.",
    "forbidden_words_absent": "Uses none of the words forbidden by the original task prompt.",
    "final_bullet_exact_ending": "The final bullet ends exactly with 'before disaster strikes.'",
    "exactly_3_sentences": "Contains exactly three sentences.",
    "total_words_45_to_60": "Contains 45 to 60 words total, inclusive.",
    "restore_path_once": "Includes the exact phrase 'restore path' exactly once.",
    "no_cloud": "Does not use the word 'cloud'.",
    "no_bullets_or_numbering": "Uses neither bullets nor numbered-list formatting.",
    "exactly_4_lines": "Contains exactly four nonempty lines.",
    "numbered_1_to_4": "The four lines are numbered 1. through 4. in order.",
    "each_step_max_11_words": "Each numbered step contains at most 11 words.",
    "verify_word_each_line": "Each numbered step contains the word 'verify' exactly once.",
    "no_title_or_extra": "Contains no title, introduction, summary, or extra lines.",
    "exactly_6_bullets": "Contains exactly six bullet lines.",
    "each_bullet_6_to_8_words": "Each of the six bullets contains 6 to 8 words, inclusive.",
    "alphabetical_first_words": "The first words of the six bullets are distinct and alphabetically ordered.",
    "backup_exactly_twice": "Uses the word 'backup' exactly twice in the entire answer.",
    "all_end_period": "Every bullet ends with a period.",
    "exactly_4_sentences": "Contains exactly four sentences.",
    "total_words_70_to_85": "Contains 70 to 85 words total, inclusive.",
    "test_restore_once": "Includes the exact phrase 'test restore' exactly once.",
    "no_list_or_heading": "Uses no bullets, numbering, or heading.",
    "final_sentence_max_12_words": "The final sentence contains at most 12 words.",
    "exact_headings": "Uses exactly '## Why it matters' then '## What to do' as the only headings.",
    "exactly_4_bullets": "Contains exactly four bullet lines.",
    "two_bullets_per_section": "Places exactly two bullets under each requested heading.",
    "no_extra_lines": "Contains exactly the two headings and four bullets, with no other nonempty lines.",
    "bullet_word_counts_8_to_12": "Each of the four bullets contains 8 to 12 words, inclusive.",
    "exactly_5_nonempty_lines": "Contains exactly five nonempty lines.",
    "greeting_exact": "Line 1 is exactly 'Hi Sam,'.",
    "lines_2_and_3_sentences": "Lines 2 and 3 are each exactly one complete sentence.",
    "sentence_lines_max_14_words": "Lines 2 and 3 each contain at most 14 words.",
    "exactly_2_bullets": "Lines 4 and 5 are exactly two bullet lines.",
    "bullet_words_5_to_9": "Each of the two bullets contains 5 to 9 words, inclusive.",
    "photos_documents_once": "Uses 'photos' exactly once and 'documents' exactly once.",
}


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def word_count(text: str) -> int:
    return len(words(text))


def exact_word_occurrences(text: str, word: str) -> int:
    return len(re.findall(rf"\b{re.escape(word)}\b", text, re.IGNORECASE))


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    description = CHECK_REQUIREMENTS.get(
        check_id,
        f"Satisfies the original task requirement named '{check_id.replace('_', ' ')}'.",
    )
    checks.append({"id": check_id, "description": description, "pass": bool(passed), "detail": detail})


def score_from_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for check in checks if check["pass"])
    return {
        "score": passed,
        "max_score": len(checks),
        "pass": passed == len(checks),
        "checks": checks,
    }


def nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def is_bullet(line: str) -> bool:
    return bool(re.match(r"^[-*]\s+\S", line))


def strip_bullet(line: str) -> str:
    return re.sub(r"^[-*]\s+", "", line).strip()


def split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]


def grade_backup_bullets(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = nonempty_lines(answer)
    bullet_lines = [line for line in lines if is_bullet(line)]
    bullet_texts = [strip_bullet(line) for line in bullet_lines]
    counts = [word_count(line) for line in bullet_texts]

    add_check(checks, "exactly_5_bullets", len(bullet_lines) == 5, f"found {len(bullet_lines)} bullet lines")
    add_check(checks, "no_extra_text", len(lines) == len(bullet_lines), f"found {len(lines) - len(bullet_lines)} non-bullet lines")
    add_check(checks, "bullet_word_counts_9_to_13", len(counts) == 5 and all(9 <= count <= 13 for count in counts), f"counts={counts}")
    add_check(checks, "offline_once_total", exact_word_occurrences(answer, "offline") == 1, f"offline_count={exact_word_occurrences(answer, 'offline')}")
    forbidden = ["essential", "critical", "best"]
    found_forbidden = [word for word in forbidden if exact_word_occurrences(answer, word)]
    add_check(checks, "forbidden_words_absent", not found_forbidden, f"found={found_forbidden}")
    add_check(
        checks,
        "final_bullet_exact_ending",
        len(bullet_texts) == 5 and bullet_texts[-1].endswith("before disaster strikes."),
        f"final={bullet_texts[-1] if bullet_texts else ''}",
    )
    grade = score_from_checks(checks)
    grade["word_counts"] = counts
    return grade


def grade_json_backup_plan(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stripped = answer.strip()
    data: Any = None
    parse_error = ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        parse_error = str(exc)

    add_check(checks, "json_parseable", data is not None, parse_error or "parsed")
    add_check(checks, "json_only_no_fence", stripped.startswith("{") and stripped.endswith("}"), "answer starts with { and ends with }")

    expected_keys = ["risks", "actions", "retention_days"]
    add_check(checks, "exact_keys", isinstance(data, dict) and sorted(data.keys()) == sorted(expected_keys), f"keys={sorted(data.keys()) if isinstance(data, dict) else None}")
    add_check(checks, "risks_three_strings", isinstance(data, dict) and isinstance(data.get("risks"), list) and len(data["risks"]) == 3 and all(isinstance(item, str) for item in data["risks"]), "risks must be 3 strings")
    add_check(checks, "actions_two_strings", isinstance(data, dict) and isinstance(data.get("actions"), list) and len(data["actions"]) == 2 and all(isinstance(item, str) for item in data["actions"]), "actions must be 2 strings")
    add_check(checks, "retention_days_integer_30", isinstance(data, dict) and data.get("retention_days") == 30, f"retention_days={data.get('retention_days') if isinstance(data, dict) else None}")
    add_check(checks, "no_markdown", "```" not in answer and not re.search(r"^\s*#", answer, re.MULTILINE), "no fences or headings")
    return score_from_checks(checks)


def grade_concise_restore_summary(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stripped = answer.strip()
    sentences = [item for item in re.split(r"(?<=[.!?])\s+", stripped) if item]
    total_words = word_count(stripped)

    add_check(checks, "exactly_3_sentences", len(sentences) == 3, f"sentences={len(sentences)}")
    add_check(checks, "total_words_45_to_60", 45 <= total_words <= 60, f"words={total_words}")
    add_check(checks, "restore_path_once", stripped.lower().count("restore path") == 1, f"restore_path_count={stripped.lower().count('restore path')}")
    add_check(checks, "no_cloud", exact_word_occurrences(stripped, "cloud") == 0, f"cloud_count={exact_word_occurrences(stripped, 'cloud')}")
    add_check(checks, "no_bullets_or_numbering", not re.search(r"^\s*(?:[-*]|\d+[.)])\s+", stripped, re.MULTILINE), "no bullet or numbered lines")
    return score_from_checks(checks)


def grade_numbered_backup_check(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = nonempty_lines(answer)
    expected_prefixes = [f"{index}." for index in range(1, 5)]
    prefixes_ok = len(lines) == 4 and all(line.startswith(prefix) for line, prefix in zip(lines, expected_prefixes))
    step_texts = [re.sub(r"^\d+\.\s*", "", line).strip() for line in lines if re.match(r"^\d+\.\s+", line)]
    counts = [word_count(text) for text in step_texts]

    add_check(checks, "exactly_4_lines", len(lines) == 4, f"lines={len(lines)}")
    add_check(checks, "numbered_1_to_4", prefixes_ok, f"prefixes={[line[:2] for line in lines]}")
    add_check(checks, "each_step_max_11_words", len(counts) == 4 and all(count <= 11 for count in counts), f"counts={counts}")
    add_check(checks, "verify_word_each_line", len(step_texts) == 4 and all(exact_word_occurrences(text, "verify") == 1 for text in step_texts), "each step must contain verify once")
    add_check(checks, "no_title_or_extra", len(lines) == len(step_texts), "no title or non-step lines")
    return score_from_checks(checks)


def grade_exact_single_line(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stripped = answer.strip()
    lines = stripped.splitlines()
    expected = "Two backups reduce single-point failure."

    add_check(checks, "exact_text", stripped == expected, f"answer={stripped!r}")
    add_check(checks, "single_line", len(lines) == 1, f"lines={len(lines)}")
    add_check(checks, "no_extra_whitespace", answer == expected, "no leading/trailing newline or spaces")
    add_check(checks, "no_markdown", not re.search(r"[*_`#]", answer), "no markdown punctuation")
    return score_from_checks(checks)


def grade_strict_json_schema(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stripped = answer.strip()
    data: Any = None
    parse_error = ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        parse_error = str(exc)

    add_check(checks, "json_parseable", data is not None, parse_error or "parsed")
    add_check(checks, "json_only", stripped.startswith("{") and stripped.endswith("}") and "```" not in answer, "object only, no fences")
    add_check(checks, "top_key_order", isinstance(data, dict) and list(data.keys()) == ["title", "checks", "cadence"], f"keys={list(data.keys()) if isinstance(data, dict) else None}")
    add_check(checks, "title_exact", isinstance(data, dict) and data.get("title") == "Backup check", f"title={data.get('title') if isinstance(data, dict) else None}")
    checks_value = data.get("checks") if isinstance(data, dict) else None
    add_check(checks, "checks_three_objects", isinstance(checks_value, list) and len(checks_value) == 3 and all(isinstance(item, dict) for item in checks_value), f"checks={checks_value!r}")
    add_check(
        checks,
        "check_object_shape",
        isinstance(checks_value, list)
        and len(checks_value) == 3
        and all(list(item.keys()) == ["name", "done"] for item in checks_value if isinstance(item, dict)),
        f"shapes={[list(item.keys()) for item in checks_value] if isinstance(checks_value, list) else None}",
    )
    add_check(
        checks,
        "done_values_false",
        isinstance(checks_value, list)
        and len(checks_value) == 3
        and all(item.get("done") is False for item in checks_value if isinstance(item, dict)),
        "all done values must be false booleans",
    )
    names = [item.get("name") for item in checks_value] if isinstance(checks_value, list) and all(isinstance(item, dict) for item in checks_value) else []
    add_check(checks, "names_one_or_two_words", len(names) == 3 and all(isinstance(name, str) and 1 <= word_count(name) <= 2 for name in names), f"names={names}")
    add_check(checks, "cadence_exact", isinstance(data, dict) and data.get("cadence") == "monthly", f"cadence={data.get('cadence') if isinstance(data, dict) else None}")
    return score_from_checks(checks)


def grade_csv_only(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = nonempty_lines(answer)
    expected_header = "item,frequency,reason"
    rows = [line.split(",") for line in lines[1:]]

    add_check(checks, "exactly_4_lines", len(lines) == 4, f"lines={len(lines)}")
    add_check(checks, "header_exact", bool(lines) and lines[0] == expected_header, f"header={lines[0] if lines else None!r}")
    add_check(checks, "no_markdown_or_intro", not re.search(r"```|^\s*#", answer, re.MULTILINE) and (not lines or lines[0] == expected_header), "no fences, heading, intro")
    add_check(checks, "three_columns_each", len(rows) == 3 and all(len(row) == 3 for row in rows), f"rows={rows}")
    add_check(checks, "frequency_weekly_monthly_yearly", len(rows) == 3 and [row[1] for row in rows] == ["weekly", "monthly", "yearly"], f"frequencies={[row[1] for row in rows] if rows else []}")
    reasons = [row[2] for row in rows if len(row) == 3]
    reason_counts = [word_count(reason) for reason in reasons]
    add_check(checks, "reason_3_to_5_words", len(reason_counts) == 3 and all(3 <= count <= 5 for count in reason_counts), f"counts={reason_counts}")
    add_check(checks, "no_extra_commas", all(line.count(",") == 2 for line in lines), "each line has exactly two commas")
    return score_from_checks(checks)


def grade_alphabetic_bullets(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = nonempty_lines(answer)
    bullet_lines = [line for line in lines if is_bullet(line)]
    texts = [strip_bullet(line) for line in bullet_lines]
    counts = [word_count(text) for text in texts]
    first_words = [words(text)[0].lower() if words(text) else "" for text in texts]

    add_check(checks, "exactly_6_bullets", len(bullet_lines) == 6, f"bullets={len(bullet_lines)}")
    add_check(checks, "no_extra_text", len(lines) == len(bullet_lines), f"extra_lines={len(lines) - len(bullet_lines)}")
    add_check(checks, "each_bullet_6_to_8_words", len(counts) == 6 and all(6 <= count <= 8 for count in counts), f"counts={counts}")
    add_check(checks, "alphabetical_first_words", len(first_words) == 6 and first_words == sorted(first_words) and len(set(first_words)) == 6, f"first_words={first_words}")
    add_check(checks, "backup_exactly_twice", exact_word_occurrences(answer, "backup") == 2, f"backup_count={exact_word_occurrences(answer, 'backup')}")
    forbidden = ["always", "never", "cloud", "critical"]
    found_forbidden = [word for word in forbidden if exact_word_occurrences(answer, word)]
    add_check(checks, "forbidden_words_absent", not found_forbidden, f"found={found_forbidden}")
    add_check(checks, "all_end_period", len(texts) == 6 and all(text.endswith(".") for text in texts), "all bullets end with periods")
    return score_from_checks(checks)


def grade_family_backup_note(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stripped = answer.strip()
    sentences = split_sentences(stripped)
    total_words = word_count(stripped)
    forbidden = ["always", "never", "cloud", "critical"]
    found_forbidden = [word for word in forbidden if exact_word_occurrences(stripped, word)]

    add_check(checks, "exactly_4_sentences", len(sentences) == 4, f"sentences={len(sentences)}")
    add_check(checks, "total_words_70_to_85", 70 <= total_words <= 85, f"words={total_words}")
    add_check(checks, "test_restore_once", stripped.lower().count("test restore") == 1, f"test_restore_count={stripped.lower().count('test restore')}")
    add_check(checks, "forbidden_words_absent", not found_forbidden, f"found={found_forbidden}")
    add_check(checks, "no_list_or_heading", not re.search(r"^\s*(?:[-*]|\d+[.)]|#)", stripped, re.MULTILINE), "no bullets, numbering, or heading")
    add_check(checks, "final_sentence_max_12_words", bool(sentences) and word_count(sentences[-1]) <= 12, f"final_words={word_count(sentences[-1]) if sentences else None}")
    return score_from_checks(checks)


def grade_two_section_checklist(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = nonempty_lines(answer)
    headings = [line for line in lines if line.startswith("## ")]
    bullet_lines = [line for line in lines if is_bullet(line)]
    bullet_texts = [strip_bullet(line) for line in bullet_lines]
    counts = [word_count(text) for text in bullet_texts]
    forbidden = ["always", "never", "critical", "best"]
    found_forbidden = [word for word in forbidden if exact_word_occurrences(answer, word)]

    add_check(checks, "exact_headings", headings == ["## Why it matters", "## What to do"], f"headings={headings}")
    add_check(checks, "exactly_4_bullets", len(bullet_lines) == 4, f"bullets={len(bullet_lines)}")
    add_check(checks, "two_bullets_per_section", lines[:3].count("## Why it matters") == 1 and lines[3:6].count("## What to do") == 1 if len(lines) == 6 else False, f"lines={lines}")
    add_check(checks, "no_extra_lines", len(lines) == 6, f"lines={len(lines)}")
    add_check(checks, "bullet_word_counts_8_to_12", len(counts) == 4 and all(8 <= count <= 12 for count in counts), f"counts={counts}")
    add_check(checks, "backup_exactly_twice", exact_word_occurrences(answer, "backup") == 2, f"backup_count={exact_word_occurrences(answer, 'backup')}")
    add_check(checks, "forbidden_words_absent", not found_forbidden, f"found={found_forbidden}")
    return score_from_checks(checks)


def grade_family_text_lines(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    lines = answer.strip().splitlines()
    stripped_lines = [line.strip() for line in lines if line.strip()]
    bullet_lines = [line for line in stripped_lines if is_bullet(line)]
    sentence_lines = stripped_lines[1:3] if len(stripped_lines) >= 3 else []
    sentence_counts = [word_count(line) for line in sentence_lines]
    bullet_counts = [word_count(strip_bullet(line)) for line in bullet_lines]
    forbidden = ["cloud", "always", "just"]
    found_forbidden = [word for word in forbidden if exact_word_occurrences(answer, word)]

    add_check(checks, "exactly_5_nonempty_lines", len(stripped_lines) == 5, f"lines={len(stripped_lines)}")
    add_check(checks, "greeting_exact", bool(stripped_lines) and stripped_lines[0] == "Hi Sam,", f"first={stripped_lines[0] if stripped_lines else None!r}")
    add_check(checks, "lines_2_and_3_sentences", len(sentence_lines) == 2 and all(len(split_sentences(line)) == 1 and line.endswith(".") for line in sentence_lines), f"sentence_lines={sentence_lines}")
    add_check(checks, "sentence_lines_max_14_words", len(sentence_counts) == 2 and all(count <= 14 for count in sentence_counts), f"counts={sentence_counts}")
    add_check(checks, "exactly_2_bullets", len(bullet_lines) == 2, f"bullets={len(bullet_lines)}")
    add_check(checks, "bullet_words_5_to_9", len(bullet_counts) == 2 and all(5 <= count <= 9 for count in bullet_counts), f"counts={bullet_counts}")
    add_check(checks, "photos_documents_once", exact_word_occurrences(answer, "photos") == 1 and exact_word_occurrences(answer, "documents") == 1, f"photos={exact_word_occurrences(answer, 'photos')} documents={exact_word_occurrences(answer, 'documents')}")
    add_check(checks, "forbidden_words_absent", not found_forbidden, f"found={found_forbidden}")
    return score_from_checks(checks)


TASKS: list[Task] = [
    Task(
        task_id="backup_bullets_annoying_constraints",
        prompt="""Write exactly 5 bullet points on why you should maintain two backups of your important files, documents, images, and videos.

Rules:
- Each bullet must be 9 to 13 words.
- The word "offline" must appear exactly once total.
- Do not use the words "essential", "critical", or "best".
- The final bullet must end with "before disaster strikes."
- Do not add a title, intro, summary, or any text outside the bullets.""",
        grader=grade_backup_bullets,
    ),
    Task(
        task_id="json_only_backup_plan",
        prompt="""Return JSON only. No markdown, no explanation.

Create a compact backup risk plan with exactly these keys:
- "risks": array of exactly 3 short strings
- "actions": array of exactly 2 short strings
- "retention_days": the integer 30

The topic is maintaining two backups of personal files, documents, images, and videos.""",
        grader=grade_json_backup_plan,
    ),
    Task(
        task_id="concise_restore_summary",
        prompt="""In exactly 3 sentences, explain why maintaining two backups protects family photos and documents.

Rules:
- Use 45 to 60 words total.
- Include the exact phrase "restore path" exactly once.
- Do not use the word "cloud".
- Do not use bullets or numbered lists.""",
        grader=grade_concise_restore_summary,
    ),
    Task(
        task_id="numbered_backup_check",
        prompt="""Give exactly 4 numbered steps for checking that two personal backups work.

Rules:
- Use lines numbered 1. through 4.
- Each step must contain the word "verify" exactly once.
- Each step must be 11 words or fewer.
- Do not add a title, intro, or summary.""",
        grader=grade_numbered_backup_check,
    ),
    Task(
        task_id="exact_single_line",
        prompt="""Return exactly this line and nothing else:
Two backups reduce single-point failure.""",
        grader=grade_exact_single_line,
    ),
    Task(
        task_id="strict_json_schema",
        prompt="""Return JSON only, with no markdown and no explanation.

Use exactly this top-level key order: "title", "checks", "cadence".
The value of "title" must be exactly "Backup check".
The value of "checks" must be exactly 3 objects.
Each check object must use exactly this key order: "name", "done".
Each "name" must be one or two words.
Each "done" must be the boolean false.
The value of "cadence" must be exactly "monthly".""",
        grader=grade_strict_json_schema,
    ),
    Task(
        task_id="csv_only_backup_schedule",
        prompt="""Return CSV only. No markdown, no title, no explanation.

Use exactly 4 lines:
item,frequency,reason
Then 3 data rows.

Rules:
- Columns must be exactly item, frequency, reason.
- Frequency values must be exactly weekly, monthly, yearly, in that order.
- Each reason must be 3 to 5 words.
- Do not put commas inside fields.""",
        grader=grade_csv_only,
    ),
    Task(
        task_id="alphabetic_backup_bullets",
        prompt="""Write exactly 6 bullet points about maintaining two copies of personal files.

Rules:
- Each bullet must be 6 to 8 words.
- The first word of each bullet must be in alphabetical order.
- The word "backup" must appear exactly twice total.
- Do not use "always", "never", "cloud", or "critical".
- Every bullet must end with a period.
- Do not add a title, intro, or summary.""",
        grader=grade_alphabetic_bullets,
    ),
    Task(
        task_id="family_backup_note",
        prompt="""A relative asks why two backups matter for personal files. Write a calm, plain-language answer.

Rules:
- Write exactly 4 sentences.
- Use 70 to 85 words total.
- Include the exact phrase "test restore" exactly once.
- Do not use "always", "never", "cloud", or "critical".
- Do not use bullets, numbering, or a heading.
- The final sentence must be 12 words or fewer.""",
        grader=grade_family_backup_note,
    ),
    Task(
        task_id="two_section_backup_checklist",
        prompt="""Write a short Markdown checklist for a family member who wants two backups of personal files.

Rules:
- Use exactly these two headings in order:
## Why it matters
## What to do
- Put exactly 2 bullets under each heading.
- Each bullet must be 8 to 12 words.
- The word "backup" must appear exactly twice total.
- Do not use "always", "never", "critical", or "best".
- Do not add any other lines.""",
        grader=grade_two_section_checklist,
    ),
    Task(
        task_id="family_text_lines",
        prompt="""Write a short text message to a family member about checking two backups.

Rules:
- Use exactly 5 non-empty lines.
- Line 1 must be exactly: Hi Sam,
- Lines 2 and 3 must each be one sentence, 14 words or fewer.
- Lines 4 and 5 must be bullet points, each 5 to 9 words.
- Use "photos" exactly once and "documents" exactly once.
- Do not use "cloud", "always", or "just".""",
        grader=grade_family_text_lines,
    ),
]


SUITE_VERSION = "llama-benchy-local-comparison@1.1"


def tasks_for_suite(version: str = "1.1") -> list[Task]:
    if version not in {"1.1", "1.2"}:
        raise ValueError(f"Unknown suite version: {version}")
    if version == "1.1":
        return TASKS
    return [
        Task(task.task_id, task.prompt.replace(
            "- Put exactly 2 bullets under each heading.",
            "- Put exactly 2 bullets under each heading.\n"
            "- Start every bullet with the Markdown marker `- ` (dash followed by a space).",
        ), task.grader) if task.task_id == "two_section_backup_checklist" else task
        for task in TASKS
    ]


def chat_completion(base_url: str, model: str, prompt: str, timeout: int, max_tokens: int, reasoning_off: bool = False) -> tuple[str, dict[str, Any], str | None]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if reasoning_off:
        payload["reasoning"] = False
        payload["reasoning_effort"] = "off"
    response = requests.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    choice = data["choices"][0]
    return choice["message"].get("content") or "", data.get("usage", {}), choice.get("finish_reason")


def run_task(base_url: str, model: str, label: str, task: Task, run_index: int, timeout: int, max_tokens: int, reasoning_off: bool = False) -> dict[str, Any]:
    started = time.time()
    error = None
    try:
        answer, usage, finish_reason = chat_completion(base_url, model, task.prompt, timeout, max_tokens, reasoning_off)
    except requests.RequestException as exc:
        answer, usage, finish_reason = "", {}, "error"
        error = str(exc)
    elapsed_s = time.time() - started
    diagnostic_grade = task.grader(answer)
    semantic_grade, semantic_meta = judge_result(
        answer, diagnostic_grade, task.task_id, task_prompt=task.prompt, finish_reason=finish_reason
    )
    return {
        "label": label,
        "task_id": task.task_id,
        "run": run_index,
        "elapsed_s": round(elapsed_s, 3),
        "answer": answer,
        "diagnostic_grade": diagnostic_grade,
        "semantic_grade": semantic_grade,
        "semantic_judge": semantic_meta,
        "usage": usage,
        "finish_reason": finish_reason,
        "error": error,
    }


def summarize(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in TASKS:
        task_results = [result for result in results if result["task_id"] == task.task_id]
        if not task_results:
            continue
        complete = all(result["semantic_grade"]["score"] is not None for result in task_results)
        total_score = sum(result["semantic_grade"]["score"] for result in task_results) if complete else None
        total_max = sum(result["semantic_grade"]["max_score"] for result in task_results)
        rows.append(
            {
                "task_id": task.task_id,
                "runs": len(task_results),
                "passes": sum(1 for result in task_results if result["semantic_grade"]["pass"]),
                "score": total_score,
                "max_score": total_max,
                "score_pct": round(total_score / total_max * 100, 1) if complete and total_max else None,
                "avg_elapsed_s": round(sum(result["elapsed_s"] for result in task_results) / len(task_results), 3),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL ending in /v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--suite-version", choices=("1.1", "1.2"), default="1.1")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--task", action="append", choices=[task.task_id for task in TASKS])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--reasoning-off", action="store_true")
    parser.add_argument("--out", default="results/ifeval-lite.json")
    args = parser.parse_args()

    selected = tasks_for_suite(args.suite_version)
    if args.task:
        selected = [task for task in selected if task.task_id in args.task]

    results: list[dict[str, Any]] = []
    for run_index in range(1, args.runs + 1):
        for task in selected:
            print(f"{args.label} {task.task_id} run={run_index}", flush=True)
            results.append(run_task(args.base_url, args.model, args.label, task, run_index, args.timeout, args.max_tokens, args.reasoning_off))

    report = {
        "suite_version": f"llama-benchy-local-comparison@{args.suite_version}",
        "label": args.label,
        "model": args.model,
        "runs": args.runs,
        "tasks": [task.task_id for task in selected],
        "summary": summarize(results),
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"saved {args.out}", flush=True)


if __name__ == "__main__":
    main()
