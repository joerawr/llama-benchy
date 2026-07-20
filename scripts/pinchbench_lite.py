#!/usr/bin/env python3
import argparse
import csv
import json
import math
import re
import statistics
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests


DEFAULT_PINCHBENCH_DIR = Path(".bench-pinchbench-skill")


@dataclass
class TaskResult:
    task_id: str
    elapsed_s: float
    answer: str
    grade: dict[str, Any]
    usage: dict[str, Any]
    finish_reason: str | None


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def has_all(text: str, patterns: list[str]) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in patterns)


def load_csv_rows(path: Path) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append((date.fromisoformat(row["AAPL_x"]), float(row["AAPL_y"])))
    return rows


def longest_streak(rows: list[tuple[date, float]], direction: int) -> tuple[int, date, date]:
    best_len = 0
    best_start = rows[0][0]
    best_end = rows[0][0]
    cur_len = 0
    cur_start = rows[0][0]
    for index in range(1, len(rows)):
        previous = rows[index - 1][1]
        current = rows[index][1]
        ok = current > previous if direction > 0 else current < previous
        if ok:
            if cur_len == 0:
                cur_start = rows[index - 1][0]
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
                best_end = rows[index][0]
        else:
            cur_len = 0
    return best_len, best_start, best_end


def finance_reference(rows: list[tuple[date, float]]) -> dict[str, Any]:
    start_date, start_price = rows[0]
    end_date, end_price = rows[-1]
    returns = [
        (rows[index][1] / rows[index - 1][1]) - 1.0
        for index in range(1, len(rows))
    ]
    high_date, high_price = max(rows, key=lambda item: item[1])
    low_date, low_price = min(rows, key=lambda item: item[1])
    best_index, best_return = max(enumerate(returns, start=1), key=lambda item: item[1])
    worst_index, worst_return = min(enumerate(returns, start=1), key=lambda item: item[1])
    annualized_vol = statistics.stdev(returns) * math.sqrt(252)
    up_streak = longest_streak(rows, 1)
    down_streak = longest_streak(rows, -1)

    peak_date = start_date
    peak_price = start_price
    max_dd = 0.0
    dd_start = start_date
    dd_end = start_date
    for row_date, price in rows:
        if price > peak_price:
            peak_price = price
            peak_date = row_date
        drawdown = (price / peak_price) - 1.0
        if drawdown < max_dd:
            max_dd = drawdown
            dd_start = peak_date
            dd_end = row_date

    return {
        "trading_days": len(rows),
        "start_date": start_date.isoformat(),
        "start_price": start_price,
        "end_date": end_date.isoformat(),
        "end_price": end_price,
        "total_return": (end_price / start_price) - 1.0,
        "high_date": high_date.isoformat(),
        "high_price": high_price,
        "low_date": low_date.isoformat(),
        "low_price": low_price,
        "annualized_vol": annualized_vol,
        "best_date": rows[best_index][0].isoformat(),
        "best_return": best_return,
        "worst_date": rows[worst_index][0].isoformat(),
        "worst_return": worst_return,
        "up_streak": {
            "length": up_streak[0],
            "start": up_streak[1].isoformat(),
            "end": up_streak[2].isoformat(),
        },
        "down_streak": {
            "length": down_streak[0],
            "start": down_streak[1].isoformat(),
            "end": down_streak[2].isoformat(),
        },
        "max_drawdown": max_dd,
        "max_drawdown_start": dd_start.isoformat(),
        "max_drawdown_end": dd_end.isoformat(),
    }


def pct_pattern(value: float, tolerance: float = 0.35) -> str:
    pct = value * 100.0
    lower = pct - tolerance
    upper = pct + tolerance
    return rf"(?<!\d)({lower:.2f}|{pct:.2f}|{upper:.2f}|{pct:.1f}|{round(pct):.0f})\s*%"


def price_pattern(value: float, tolerance: float = 0.20) -> str:
    rounded = round(value, 2)
    lower = rounded - tolerance
    upper = rounded + tolerance
    return rf"\$?\s*(?:{rounded:.2f}|{lower:.2f}|{upper:.2f}|{rounded:.1f})"


def build_finance_prompt(csv_text: str) -> str:
    return f"""You are completing a PinchBench-lite finance report task.

Use only the CSV data below. Do not assume external facts.

Return the content of `finance_report.md` directly as Markdown. Include exactly these sections:
1. Executive Summary
2. Price Performance
3. Volatility Analysis
4. Notable Trading Days
5. Trend Analysis
6. Risk Metrics
7. Conclusion

The report should be suitable for an investor or analyst review. Compute metrics from the data:
- starting and ending adjusted close, total return
- monthly average prices or quarterly returns
- year high and low with dates
- daily return mean/std dev, annualized volatility, quarterly volatility comparison
- top 3 best and worst daily percentage moves with dates
- major trend periods and longest up/down streaks
- maximum drawdown with dates and a simple risk-adjusted return measure

<CSV apple_stock_2014.csv>
{csv_text}
</CSV>
"""


def grade_finance(answer: str, ref: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, description: str) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "description": description})

    text = answer
    lower = answer.lower()
    sections = [
        "executive summary",
        "price performance",
        "volatility analysis",
        "notable trading days",
        "trend analysis",
        "risk metrics",
        "conclusion",
    ]
    add("all_sections", all(section in lower for section in sections), "Contains all seven requested report sections.")
    add(
        "start_end_return",
        has_all(text, [ref["start_date"], ref["end_date"], price_pattern(ref["start_price"]), price_pattern(ref["end_price"])])
        and has_any(text, [pct_pattern(ref["total_return"], 1.0), r"42(?:\.\d+)?\s*%"]),
        "Includes correct start/end dates, prices, and ~42% total return.",
    )
    add(
        "high_low",
        has_all(text, [ref["high_date"], ref["low_date"], price_pattern(ref["high_price"]), price_pattern(ref["low_price"])]),
        "Identifies year high and low prices with dates.",
    )
    add(
        "monthly_or_quarterly",
        has_any(lower, [r"monthly average", r"quarterly return", r"\bq1\b", r"\bq2\b", r"\bq3\b", r"\bq4\b"])
        and has_any(text, [r"\|.*\|", r"jan(?:uary)?", r"feb(?:ruary)?", r"quarter"]),
        "Presents monthly or quarterly price/performance data.",
    )
    add(
        "volatility",
        has_any(lower, [r"annualized volatility", r"volatility"])
        and has_any(text, [pct_pattern(ref["annualized_vol"], 1.0), r"23(?:\.\d+)?\s*%"])
        and has_any(lower, [r"standard deviation", r"std", r"daily return"]),
        "Computes daily return statistics and ~23% annualized volatility.",
    )
    add(
        "best_worst_days",
        has_all(text, [ref["best_date"], ref["worst_date"]])
        and has_any(text, [r"7\.4\d?\s*%", r"\+7"])
        and has_any(text, [r"-7\.5\d?\s*%", r"7\.5\d?\s*%"]),
        "Identifies best and worst daily moves with dates.",
    )
    add(
        "trend_streaks",
        has_any(text, [r"9\s+(?:day|trading day).*up", r"up\s+streak.*9", r"Aug(?:ust)?\s+11.*Aug(?:ust)?\s+21"])
        and has_any(text, [r"5\s+(?:day|trading day).*down", r"down\s+streak.*5", r"Jan(?:uary)?\s+27.*Jan(?:uary)?\s+31"]),
        "Mentions longest up and down streaks.",
    )
    add(
        "max_drawdown",
        has_any(lower, [r"maximum drawdown", r"max drawdown"])
        and has_any(text, [r"10\.\d+\s*%", r"11(?:\.\d+)?\s*%"])
        and has_any(text, [ref["max_drawdown_end"], r"2014-01-31"]),
        "Includes maximum drawdown magnitude and dates.",
    )
    add(
        "risk_adjusted_return",
        has_any(lower, [r"risk-adjusted", r"return divided by volatility", r"return/volatility", r"sharpe"]),
        "Includes a simple risk-adjusted return measure.",
    )
    add(
        "professional_markdown",
        answer.count("#") >= 4 and (("|" in answer and "---" in answer) or len(answer.splitlines()) >= 25),
        "Uses professional Markdown structure and readable data presentation.",
    )
    add(
        "insight_quality",
        has_any(lower, [r"rally", r"selloff", r"risk", r"reward", r"accumulation", r"momentum", r"investor"])
        and has_any(lower, [r"takeaway", r"assessment", r"conclusion"]),
        "Provides qualitative investment interpretation, not just raw numbers.",
    )
    add(
        "no_bad_core_inversion",
        not has_any(lower, [r"negative return", r"declined over(?:all)?", r"worst day.*2014-04-24", r"best day.*2014-01-28"]),
        "Does not invert core performance facts.",
    )

    return {
        "score": sum(1 for check in checks if check["pass"]),
        "max_score": len(checks),
        "word_count": len(re.findall(r"\b\w+\b", answer)),
        "checks": checks,
        "reference": ref,
    }


def build_log_prompt(log_text: str) -> str:
    return f"""You are completing a PinchBench-lite Apache log analysis task.

Use only the log below. Return the content of `error_summary.md` directly as Markdown.

Include these sections:
1. Overview: total log entries, date range, error vs notice breakdown
2. Server Configuration Issues: startup/module/configuration problems, separated from client errors
3. Client Error Summary: unique client IPs, client-associated errors, and major categories
4. Security Assessment: scanning/probing/attack activity with specific evidence
5. Recommendations: top 3 actionable recommendations

<APACHE_ERROR_LOG>
{log_text}
</APACHE_ERROR_LOG>
"""


def load_access_events_csv(pinchbench_dir: Path) -> str:
    task_text = (pinchbench_dir / "tasks" / "task_access_log_anomaly.md").read_text(encoding="utf-8")
    match = re.search(r"content:\s*\|\n(.*?)\n---", task_text, flags=re.DOTALL)
    if not match:
        raise ValueError("could not extract embedded access_events.csv from task_access_log_anomaly.md")
    lines = []
    for line in match.group(1).splitlines():
        lines.append(line[6:] if line.startswith("      ") else line)
    return "\n".join(lines).strip() + "\n"


def build_access_anomaly_prompt(csv_text: str) -> str:
    return f"""You are completing a PinchBench-lite physical access anomaly detection task.

Use only the CSV data below. Return only a JSON array, with no Markdown and no prose outside the JSON.

Rules:
- HQ Building and Annex Building are physically separate and 15 minutes apart on foot.
- Business hours are 07:00-19:00 Monday-Friday.
- Restricted doors are any `door_id` containing `SRV`.
- Flag `impossible_travel` when the same badge scans at both HQ and Annex within 15 minutes.
- Flag `after_hours_restricted` when a GRANTED event occurs at an SRV door outside business hours.
- Flag `repeated_denials` when the same badge has four or more DENIED events at the same door within any 10-minute window.
- Do not flag badges below a rule threshold.

Each JSON array item must include:
{{
  "badge_id": "1042",
  "anomaly_type": "impossible_travel",
  "description": "Brief explanation referencing timestamps and locations"
}}

<CSV access_events.csv>
{csv_text}
</CSV>
"""


def extract_json_array(text: str) -> list[Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", stripped)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if isinstance(parsed, dict):
        parsed = parsed.get("anomalies", parsed.get("findings", []))
    return parsed if isinstance(parsed, list) else None


def grade_access_anomaly(answer: str) -> dict[str, Any]:
    anomalies = extract_json_array(answer)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, description: str) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "description": description})

    add("valid_json_array", anomalies is not None, "Returns a parseable JSON array.")
    if anomalies is None:
        anomalies = []

    def entry_text(entry: Any) -> str:
        if isinstance(entry, dict):
            return " ".join(str(entry.get(key, "")) for key in ["badge_id", "anomaly_type", "description"]).lower()
        return str(entry).lower()

    entries = [entry_text(entry) for entry in anomalies]

    def badge_with_keywords(badge: str, keywords: list[str]) -> bool:
        return any(badge in text and any(keyword in text for keyword in keywords) for text in entries)

    def badge_present(badge: str) -> bool:
        return any(badge in text for text in entries)

    add(
        "impossible_travel_1042",
        badge_with_keywords("1042", ["impossible", "travel", "annex", "15", "inter-building", "interbuilding"]),
        "Flags badge 1042 for impossible travel between HQ and Annex.",
    )
    add(
        "after_hours_restricted_2371",
        badge_with_keywords("2371", ["after", "hours", "restricted", "server", "srv", "02:", "outside"]),
        "Flags badge 2371 for after-hours restricted server-room access.",
    )
    add(
        "repeated_denials_3819",
        badge_with_keywords("3819", ["denied", "denial", "repeated", "multiple", "consecutive", "attempt"]),
        "Flags badge 3819 for four denied attempts within 10 minutes.",
    )
    add("no_false_positive_6601", not badge_present("6601"), "Does not flag badge 6601 with only three denials.")
    add(
        "specific_evidence",
        any("08:05:33" in text and "08:05:58" in text for text in entries)
        and any("02:17:44" in text for text in entries)
        and any("14:22" in text and "14:23" in text for text in entries),
        "Descriptions cite the relevant timestamps for each anomaly.",
    )
    add(
        "reasonable_count",
        3 <= len(anomalies) <= 5,
        "Returns roughly the expected anomaly count without excessive false positives.",
    )

    return {
        "score": sum(1 for check in checks if check["pass"]),
        "max_score": len(checks),
        "word_count": len(re.findall(r"\b\w+\b", answer)),
        "checks": checks,
        "parsed_anomaly_count": len(anomalies),
    }


def build_iris_prompt(csv_text: str) -> str:
    return f"""You are completing a PinchBench-lite Iris outlier detection task.

Use only the CSV data below. Return the content of `iris_outliers.md` directly as Markdown.

Your report must include:
- Outlier detection method: explain IQR, z-score, or both
- Overall outliers: outliers across the full dataset for each numeric column, with values and row/sample identification
- Within-species outliers: outliers within each species group
- Unusual observations: atypical samples for their species when considering multiple features together
- Summary: how many outliers were found, affected features/species, and whether any samples might be mislabeled

<CSV iris_flowers.csv>
{csv_text}
</CSV>
"""


def grade_iris(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    content = answer.lower()

    def add(check_id: str, passed: bool, description: str) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "description": description})

    add(
        "method_explained",
        sum(
            1
            for pattern in [
                r"iqr|inter\s*-?\s*quartile",
                r"z\s*-?\s*score",
                r"1\.5\s*(?:\*|x|×)?\s*iqr",
                r"upper|lower.*fence|fence",
            ]
            if re.search(pattern, content)
        )
        >= 2,
        "Explains a statistical outlier method.",
    )
    add(
        "sepalwidth_outliers",
        has_any(content, [r"sepal\s*width.*outlier", r"sepalwidth.*outlier", r"outlier.*sepal\s*width"]),
        "Identifies SepalWidth as the main overall outlier column.",
    )
    add(
        "specific_overall_values",
        all(re.search(pattern, answer, flags=re.IGNORECASE) for pattern in [r"4\.4", r"4\.1", r"4\.2", r"2\.0"])
        and has_any(content, [r"row\s*(?:16|15)", r"sample\s*(?:16|15)", r"index\s*(?:16|15)"])
        and has_any(content, [r"row\s*(?:61|60)", r"sample\s*(?:61|60)", r"index\s*(?:61|60)"]),
        "Reports the four key SepalWidth overall outlier values with row/sample references.",
    )
    add(
        "iqr_fences",
        has_any(answer, [r"Q1\s*=?\s*2\.8", r"2\.8.*Q1"])
        and has_any(answer, [r"Q3\s*=?\s*3\.3", r"3\.3.*Q3"])
        and has_any(answer, [r"IQR\s*=?\s*0\.5"])
        and has_any(answer, [r"2\.05", r"4\.05"]),
        "Includes the expected SepalWidth IQR quartiles/fences.",
    )
    add(
        "no_other_overall_iqr",
        has_any(content, [r"no outliers.*sepal length", r"sepal length.*no outliers"])
        and has_any(content, [r"no outliers.*petal length", r"petal length.*no outliers"])
        and has_any(content, [r"no outliers.*petal width", r"petal width.*no outliers"]),
        "Notes no overall IQR outliers in the other numeric columns.",
    )
    add(
        "within_species",
        has_any(content, [r"within[- ]species", r"by species", r"per species", r"species-level", r"species specific"])
        and all(species in content for species in ["setosa", "versicolor", "virginica"]),
        "Performs within-species analysis across species groups.",
    )
    add(
        "unusual_row_42",
        has_any(content, [r"row\s*42", r"sample\s*42", r"observation\s*42", r"index\s*41"])
        and has_any(answer, [r"2\.3"])
        and "setosa" in content,
        "Mentions the low SepalWidth setosa observation around row 42.",
    )
    add(
        "unusual_row_107",
        has_any(content, [r"row\s*107", r"sample\s*107", r"observation\s*107", r"index\s*106"])
        and has_any(answer, [r"4\.9"])
        and "virginica" in content,
        "Mentions the small SepalLength virginica observation around row 107.",
    )
    add(
        "mislabeling_discussion",
        has_any(content, [r"mislabel", r"misclassif", r"wrong label", r"measurement error", r"data entry"]),
        "Discusses whether outliers may indicate measurement error or mislabeling.",
    )
    add(
        "summary",
        has_any(content, [r"summary", r"conclusion", r"overall"])
        and has_any(content, [r"4\s+overall", r"four\s+overall", r"4\s+outlier"])
        and has_any(content, [r"sepal\s*width"]),
        "Includes a concise summary of outlier count and affected feature.",
    )
    add(
        "structured_markdown",
        answer.count("#") >= 3 and len(answer.splitlines()) >= 20,
        "Uses readable Markdown report structure.",
    )

    return {
        "score": sum(1 for check in checks if check["pass"]),
        "max_score": len(checks),
        "word_count": len(re.findall(r"\b\w+\b", answer)),
        "checks": checks,
    }


def grade_log(answer: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    content = answer.lower()

    def add(check_id: str, passed: bool, description: str) -> None:
        checks.append({"id": check_id, "pass": bool(passed), "description": description})

    add(
        "overview_counts",
        has_any(content, [r"jun 9", r"june 9"]) and has_any(content, [r"jun 16", r"june 16"])
        and has_any(content, [r"\b1000\b", r"1,000"])
        and has_any(content, [r"\b753\b", r"\b75[0-9]\b", r"\berror"])
        and has_any(content, [r"\b247\b", r"\b25[0-9]\b", r"\bnotice"]),
        "Includes date range, total entries, and error/notice breakdown.",
    )
    add(
        "server_config_issues",
        has_any(content, [r"mod_jk", r"jk2", r"jk connector"])
        and has_any(content, [r"createbean", r"factory error", r"channel\.jni", r"worker\.jni"])
        and has_any(content, [r"startup", r"configuration", r"initialization", r"init"]),
        "Separately identifies JK/createBean server configuration issues.",
    )
    add(
        "startup_timeline",
        has_any(content, [r"jun 9.*06:07", r"jun 10.*11:32", r"jun 12.*04:04", r"graceful restart"])
        and has_any(content, [r"3\s+(?:server\s+)?start", r"three\s+(?:server\s+)?start", r"restart"]),
        "Mentions repeated startup/restart timing or count.",
    )
    add(
        "client_error_summary",
        has_any(content, [r"159", r"unique client"])
        and has_any(content, [r"630", r"client-associated", r"client errors"])
        and has_any(content, [r"directory index forbidden", r"file does not exist", r"script not found", r"invalid method"]),
        "Summarizes client errors with unique IPs, total client errors, and categories.",
    )
    add(
        "security_worms",
        has_any(content, [r"cmd\.exe", r"root\.exe"])
        and has_any(content, [r"nimda", r"code red", r"worm", r"iis"]),
        "Identifies IIS worm probes with cmd.exe/root.exe evidence.",
    )
    add(
        "security_traversal",
        has_any(content, [r"traversal", r"encoded path", r"unicode"])
        and has_any(content, [r"%5c", r"%c0", r"%c1", r"%e0", r"%252e"]),
        "Identifies directory traversal / encoded path probes.",
    )
    add(
        "scanner_ips",
        has_any(content, [r"202\.133\.98\.6"])
        and has_any(content, [r"awstats"])
        and has_any(content, [r"212\.238\.198\.203", r"openwebmail", r"_vti_bin", r"frontpage"]),
        "Includes specific scanner IPs and targets.",
    )
    add(
        "recommendations",
        len([line for line in content.splitlines() if has_any(line, [r"recommend", r"should", r"implement", r"block", r"fix", r"add", r"configure", r"enable"])]) >= 3
        and has_any(content, [r"directoryindex", r"default page", r"index"])
        and has_any(content, [r"block", r"rate limit", r"firewall"])
        and has_any(content, [r"jk", r"connector", r"mod_jk"]),
        "Provides at least three actionable recommendations covering index noise, scanners, and JK config.",
    )
    add(
        "structured_markdown",
        all(section in content for section in ["overview", "server configuration", "client error", "security", "recommendation"])
        and answer.count("#") >= 4,
        "Uses the requested Markdown section structure.",
    )
    add(
        "no_bad_core_inversion",
        not has_any(content, [r"no security", r"no attack", r"no scanning", r"only notice", r"windows server"]),
        "Does not invert the core security/server facts.",
    )

    return {
        "score": sum(1 for check in checks if check["pass"]),
        "max_score": len(checks),
        "word_count": len(re.findall(r"\b\w+\b", answer)),
        "checks": checks,
    }


def run_once(base_url: str, model: str, prompt: str, max_tokens: int, timeout: int) -> dict[str, Any]:
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


def run_task(
    task_id: str,
    base_url: str,
    model: str,
    pinchbench_dir: Path,
    runs: int,
    timeout: int,
) -> dict[str, Any]:
    assets = pinchbench_dir / "assets"
    if task_id == "task_csv_finance_report":
        csv_path = assets / "csvs" / "apple_stock_2014.csv"
        csv_text = csv_path.read_text(encoding="utf-8")
        ref = finance_reference(load_csv_rows(csv_path))
        prompt = build_finance_prompt(csv_text)
        max_tokens = 2800
        grader = lambda answer: grade_finance(answer, ref)
    elif task_id == "task_log_apache_error_summary":
        log_text = (assets / "logs" / "apache_error.log").read_text(encoding="utf-8", errors="replace")
        prompt = build_log_prompt(log_text)
        max_tokens = 3000
        grader = grade_log
    elif task_id == "task_access_log_anomaly":
        access_csv = load_access_events_csv(pinchbench_dir)
        prompt = build_access_anomaly_prompt(access_csv)
        max_tokens = 800
        grader = grade_access_anomaly
    elif task_id == "task_csv_iris_outliers":
        iris_text = (assets / "csvs" / "iris_flowers.csv").read_text(encoding="utf-8")
        prompt = build_iris_prompt(iris_text)
        max_tokens = 1800
        grader = grade_iris
    else:
        raise ValueError(f"unsupported task: {task_id}")

    task_results: list[dict[str, Any]] = []
    for index in range(runs):
        print(f"{task_id} run {index + 1}/{runs}: prompt chars={len(prompt)}", flush=True)
        result = run_once(base_url, model, prompt, max_tokens, timeout)
        result["run"] = index + 1
        result["grade"] = grader(result["answer"])
        print(
            f"  score={result['grade']['score']}/{result['grade']['max_score']} "
            f"elapsed={result['elapsed_s']:.2f}s finish={result['finish_reason']} "
            f"words={result['grade']['word_count']}",
            flush=True,
        )
        print(f"  answer={result['answer'][:180]!r}", flush=True)
        task_results.append(result)

    scores = [result["grade"]["score"] for result in task_results]
    return {
        "task_id": task_id,
        "model": model,
        "runs": task_results,
        "score_summary": {
            "min": min(scores),
            "max": max(scores),
            "avg": sum(scores) / len(scores),
            "max_score": task_results[0]["grade"]["max_score"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--task",
        action="append",
        choices=[
            "task_csv_finance_report",
            "task_log_apache_error_summary",
            "task_access_log_anomaly",
            "task_csv_iris_outliers",
        ],
        help="Task to run. Repeatable. Defaults to both.",
    )
    parser.add_argument("--pinchbench-dir", default=str(DEFAULT_PINCHBENCH_DIR))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    tasks = args.task or ["task_csv_finance_report", "task_log_apache_error_summary"]
    pinchbench_dir = Path(args.pinchbench_dir)
    if not pinchbench_dir.exists():
        raise FileNotFoundError(f"PinchBench directory not found: {pinchbench_dir}")

    reports = [
        run_task(task, args.base_url, args.model, pinchbench_dir, args.runs, args.timeout)
        for task in tasks
    ]
    report = {
        "label": args.label,
        "model": args.model,
        "pinchbench_dir": str(pinchbench_dir),
        "tasks": reports,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved {out_path}", flush=True)


if __name__ == "__main__":
    main()
