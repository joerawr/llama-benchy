#!/usr/bin/env python3
"""Keep a human-readable report up to date while the durable worker runs."""
import csv
import html
import json
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/swift-qwen-thinking-20261019"
UNIT = "swift-qwen-thinking-20261019.service"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def render():
    report = json.loads((OUT / "report.json").read_text())
    manifest = json.loads((OUT / "manifest.json").read_text())
    rows = []
    for label, summary in report["summary"].items():
        records = [r for r in report["records"].values() if r["label"] == label]
        tasks = summary["tasks"]
        elapsed = [mean(t["elapsed_s"]) for t in tasks.values()]
        reasoning = [mean(t["reasoning_tokens"]) for t in tasks.values()]
        rows.append({
            "model": manifest["models"][label]["name"], "label": label,
            "finance_out_of_12": tasks["finance"]["mean_score"],
            "compression_out_of_12": tasks["compression"]["mean_score"],
            "combined_out_of_24": summary["score_out_of_24"],
            "mean_task_pair_wall_minutes": sum(elapsed) / 60 if all(v is not None for v in elapsed) else None,
            "mean_task_pair_reasoning_tokens": sum(reasoning) if all(v is not None for v in reasoning) else None,
            "prompt_tokens_per_s": mean([r.get("timings", {}).get("prompt_per_second") for r in records]),
            "generation_tokens_per_s": mean([r.get("timings", {}).get("predicted_per_second") for r in records]),
            "completed_scored_attempts": sum(r.get("semantic_grade", {}).get("score") is not None for r in records),
            "attempts": len(records),
            "failures": [r.get("error") or r.get("semantic_grade", {}).get("error") for r in records
                         if r.get("semantic_grade", {}).get("score") is None],
        })
    valid = [r for r in rows if r["combined_out_of_24"] is not None]
    status = report["status"]
    if status == "complete" and len(valid) == len(rows):
        best_score = max(r["combined_out_of_24"] for r in valid)
        tied = [r for r in valid if r["combined_out_of_24"] == best_score]
        winner = min(tied, key=lambda r: r["mean_task_pair_wall_minutes"])
        recommendation = f"{winner['model']} has the best observed focused result ({best_score:.2f}/24)."
        if len(tied) > 1:
            recommendation += " It is the faster of the models tied on accuracy."
        recommendation += " This is a small Finance/Compression comparison, not an overall capability ranking."
    elif status == "paused_by_user":
        recommendation = "Quality campaign paused at user request. ThinkingCap was cancelled without a final answer and remains unscored. Only five-minute Swift speed probes are authorized next; select a quality-test priority afterward."
    elif status in {"error", "incomplete", "interrupted"}:
        recommendation = "Comparison incomplete. Preserve missing scores and inspect failures before selecting a winner."
    else:
        recommendation = "Comparison running; no winner established yet."
    result = {"status": status, "current": report.get("current"), "recommendation": recommendation,
              "rows": rows, "updated_at": report["updated_at"], "service_restored": report.get("service_restored")}
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2))
    with (OUT / "comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != "failures"])
        writer.writeheader(); writer.writerows({k: v for k, v in r.items() if k != "failures"} for r in rows)
    columns = [("model", "Model"), ("finance_out_of_12", "Finance /12"), ("compression_out_of_12", "Compression /12"),
               ("combined_out_of_24", "Total /24"), ("mean_task_pair_wall_minutes", "Mean pair, minutes"),
               ("mean_task_pair_reasoning_tokens", "Mean pair, thinking tokens"),
               ("prompt_tokens_per_s", "Prompt tok/s"), ("generation_tokens_per_s", "Generation tok/s"),
               ("completed_scored_attempts", "Scored"), ("attempts", "Attempts")]
    def display(value):
        if value is None:
            return "—"
        return f"{value:.2f}" if isinstance(value, float) else html.escape(str(value))
    table = "<tr>" + "".join(f"<th>{title}</th>" for _, title in columns) + "</tr>"
    for row in rows:
        table += "<tr>" + "".join(f"<td>{display(row[key])}</td>" for key, _ in columns) + "</tr>"
    failure_notes = "".join(f"<p>{html.escape(r['model'])}: {html.escape(str(f))}</p>" for r in rows for f in r["failures"])
    page = f"""<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<title>Swift 1.5 and Qwen focused comparison</title>
<style>body{{font:16px system-ui;max-width:1400px;margin:40px auto;padding:0 24px;color:#17212b;background:#f8fafc}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;text-align:right;border-bottom:1px solid #ddd}}td:first-child,th:first-child{{text-align:left}}p{{line-height:1.6}}small{{color:#52606d}}</style>
<h1>Swift 1.5 and dense Qwen: focused thinking comparison</h1>
<p><b>{html.escape(recommendation)}</b></p>
<p>Status: {html.escape(status)} · Current: {html.escape(str(report.get('current') or '—'))}</p>
<table>{table}</table>
<p>Apple M1 Max Vulkan · 32K context · f16 KV · xhigh thinking · MTP off · temperature 1, top-p .95, top-k 20. No completion-token cap; one-hour wall limit per attempt. Two passes, with a third when checks differ or a pass fails. Missing quality remains unscored.</p>
<p>All models receive the same publisher Swift/Qwen3.8 chat template and rendered prompt. ThinkingCap is a Qwen3.6 derivative with no native named effort control; the shared template supplies its xhigh instruction. Compression has a separately versioned thinking prompt with its original /no_think directive removed. This /24 experiment is distinct from the seven-task /62 leaderboard.</p>
<p>Latency includes prompt processing, thinking and the final answer; it excludes loading and grading. Token rates are backend timings. Thinking-token counts are separate retokenizations of extracted reasoning. Timeouts and failures remain in the attempt history. Averages are over all attempts for each task, not best-of scores.</p>
{failure_notes}
<p><a href="report.json">Raw report</a> · <a href="manifest.json">Protocol and model identities</a> · <a href="comparison.csv">CSV</a></p>
<small>Updates every minute while the worker runs. Last saved {time.strftime('%Y-%m-%d %H:%M:%S %Z', time.localtime(report['updated_at']))}.</small>"""
    temp = OUT / "comparison.html.tmp"; temp.write_text(page); temp.replace(OUT / "comparison.html")
    return status


if __name__ == "__main__":
    while True:
        status = render()
        active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT]).returncode == 0
        if not active and status != "running":
            break
        if not active:
            break
        time.sleep(30)
