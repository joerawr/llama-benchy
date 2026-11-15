# Heavy-task lite calibration

These are new experimental task versions, separate from the original seven-task suite. Every prompt, source excerpt, answer key and rubric is frozen per version. The answer key is given only to the judge, except Apache v3's explicitly supplied parser summary.

Six hosted requests were run on `qwen/qwen3.8-27b`, pinned to `wafer/fp8` with fallback disabled. All requested xhigh, temperature 1, top_p .95, top_k 20, min_p 0 and seed 20261115. Each request allowed 12,288 generated tokens, including reasoning. Exhausting the allowance without answering is incomplete, not a quality score. Canonical grading uses Luna xhigh, source-aware-v2, original evidence and explicit rubric requirements.

| Task | Version | Design | Outcome |
|---|---|---|---|
| Apache | 0.1 | 120 stratified lines; exact totals, client counts and category counts | Output limit; no answer |
| Apache | 0.2 | 80 stratified lines; fewer totals; category-count table removed | Output limit; no answer |
| Apache | 0.3 | Same 80 lines with authoritative parser summary; diagnose faults and security evidence, prioritize three actions | 6/6; selected candidate |
| Finance | 0.1 | First 30 trading days; daily statistics, volatility, streaks, ratio and drawdown | Output limit; no answer |
| Finance | 0.2 | Same 30 days; sample return, high/low, daily extremes, drawdown and cautious interpretation | 6/6; selected candidate |
| Finance | 0.3 | Same focused requirements on a distinct 40-day window (source rows 31-70) | 6/6; harder alternate |

Selection preserves configuration-versus-client diagnosis and security evidence for Apache, and nontrivial numerical analysis for Finance. Apache v3 no longer measures unaided log counting. Finance v2 no longer measures volatility, streaks or risk-adjusted ratios. Neither score is comparable to the original task's denominator. A perfect single hosted score does not establish a ceiling or validate a model ranking.

Runtime suitability is estimated using total output tokens, not hosted seconds. At 8-10 generated tokens/s, selected outputs leave headroom for prefill within 30 minutes. Actual local completion is unverified and must be measured with a 30-minute wall limit before adopting the candidates into the regular suite. Hosted FP8 output and the local UD3.1 Q4_K_XL model can differ.

The Apache selection preserves source line order and repeated records while stratifying by notices, server errors and client error classes, with explicit inclusion of diagnostic/security examples. The selection indices and original fixture hashes are in the task JSON. Finance references are recomputed from each exact CSV, and independently checked for returns, sample deviation, extrema and peak/trough drawdown. Source prompts and fixtures from suite 1.1 were not edited.

Run one saved prototype (existing result files prevent duplicate inference):

```sh
.venv/bin/python scripts/calibrate_heavy_lite.py apache 3
.venv/bin/python scripts/calibrate_heavy_lite.py finance 2
.venv/bin/python -m unittest discover -s tests -p test_heavy_lite_calibration.py
```

Public summary: `benchmarks/runs/heavy-lite-calibration-20261115.json` and `heavy-lite-calibration-results.html`. Raw answers, reasoning and events stay in ignored `results/heavy-lite-calibration-20261115/`. OpenRouter charges total $0.140888 for six requests; local Codex quality grading is separate. No fourth or fifth prototype has been run.
