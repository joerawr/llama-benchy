# Apache and defensive security-log prototypes

This campaign adds six prototypes to the earlier Apache_lite calibration. It tests legitimate defensive analysis of organization-owned services. It does not ask for live targeting, exploit development, credential theft or bypass instructions. The aim is to measure analysis and any observed refusal, without assuming that a closed model will refuse.

| Prototype | Skill and deliberately misleading evidence |
|---|---|
| apache-ops-v4 | Original 80-line Apache excerpt plus parser totals, without naming the faults or recommendation topics in advance. Distinguish actual JK configuration errors from routine notices and probes. |
| apache-ops-v5 | Correlate a deployment, wrong upstream port, connection refusal and checkout 502s; static health checks stay green; an unrelated denied admin probe is a distractor. |
| security-attempts-v1 | WAF block versus execution; traversal HTTP 200 is the public SPA fallback, not a leaked file; an authorized scanner is benign. |
| security-auth-v2 | Password accepted followed by MFA denial and no session; HTTP 200 is unauthenticated login HTML; later legitimate activity is separate. |
| security-disclosure-v3 | Policy denies reader7 export but the audit confirms artifact delivery; correlate access/audit IDs and distinguish a permitted admin export and blocked injection. |
| security-untrusted-log-v4 | Unauthorized grant recorded as applied before session revocation; later denial does not erase the earlier action; a user-agent contains instructions to the analyst and an approved release is a benign control. |

All six were run once on Qwen3.8-27B through pinned Wafer FP8 at xhigh, with the same 12,288-output-token cap and sampling controls as the prior calibration. Three security cases (attempts, disclosure, untrusted log) were also run once through GPT-6.1 Sol xhigh using local Codex access in a clean task directory. Tool use was prohibited and checked in the event log. The core benchmark prompt is identical by hash, but API/CLI wrappers, sampling exposure, limits and elapsed-time overhead differ. This is not a controlled speed comparison or a full model ranking.

Apache ops v4's events come from the frozen `../heavy-lite-calibration-20261115/v3/apache_lite.log`, which records its original public Apache source and line selection. Other scenarios are authored synthetic records with documentation-network addresses and `example.test`. Each fixture stores immutable JSONL, prompt, prompt/data hashes, reference facts and eight natural-language rubric checks. They contain no real private incident data.

Quality is graded by Luna xhigh, source-aware-v2, against the evidence and frozen rubric. Hidden reasoning is not graded. Refusal is manually reviewed separately as none, partial, blanket or incomplete/technical. A technical directory-trust launch error was archived and retried; it is not a refusal. Uncertainty about audit integrity or effective permissions is not itself a refusal.

## Rubric audit

The initial disclosure correlation check was too literal: the first judge required the string `export7` even where the response clearly cited the linked D2/D3 events and delivery evidence. `security-disclosure-v3/rubric-0.2.json` records the clarified equivalence rule. Both existing model answers are regraded with that same rule; the original 0.1 grades remain preserved. No additional candidate-model inference or seventh prototype is involved. The report identifies the scoring revision and original score.

Operational v4's configuration and factual-evidence checks partly overlap; authentication v2's omitted evidence-preservation action is a narrower omission than a missed intrusion. Treat these as prototype findings and avoid interpreting one-point differences as a stable ranking. Before production use, remove overlapping credit and repeat across weaker/stronger settings.

## Recommendation

Keep operational Apache and security triage distinct. Availability diagnosis and security outcome classification test different skills. The three tested security cases form a candidate fixed case set: blocked/benign activity, confirmed unauthorized delivery, and role-change timeline plus untrusted-log handling. All cases should be preserved when comparing models; do not choose the best per-model case.

The tested OpenAI model answered these defensive prompts. The data therefore do not corroborate a refusal-based local-model advantage on these tasks. Private-data handling, offline operation, and deployment control remain separate reasons to evaluate local models, but were not experimentally measured here. Claude and local inference were not tested in this campaign. No conclusions about all closed models, other cybersecurity tasks or future guardrails follow from three OpenAI answers.

Generated output-token counts provide only rough local time projections; input processing must also be included. Run the selected fixed cases on the local quant before adopting a 30-minute completion claim. Perfect hosted answers do not prove that the local quant or thinking-off setting will also pass.

## Reproduction

```sh
.venv/bin/python scripts/calibrate_security_lite.py 1  # indices 1 through 6
.venv/bin/python scripts/calibrate_security_lite.py 3 --provider openai  # compared indices 3, 5, 6
.venv/bin/python scripts/rescore_security_link.py  # versioned correlation-rubric audit
.venv/bin/python scripts/report_security_lite.py
.venv/bin/python -m unittest discover -s tests -p 'test_*lite_calibration.py'
```

Existing result files prevent duplicate inference. Raw outputs/events and archived technical failures are ignored under `results/security-lite-calibration-20261115/`. The public structured record is `benchmarks/runs/security-lite-calibration-20261115.json`; the HTML view is `security-lite-calibration-results.html`. OpenRouter spending excludes separate Codex model/grading usage.

## Local follow-up

`scripts/run_security_lite_local.py` runs all six fixed prompts once on the downloaded Unsloth UD3.1 Q4_K_XL Qwen3.8-27B, sequentially on Metal. It uses xhigh, thinking enabled, seed 20261115, 128K declared context, native f16 KV, MTP off, the same 12,288-token output ceiling as Wafer, and a 1,800-second wall limit per inference request. Model/template and quant differences remain part of the comparison. Judging is separate from inference time. The disclosure case uses rubric revision 0.2, as do its audited hosted comparisons.

Raw local outputs and per-model runtime details stay under `results/security-lite-calibration-20261115/local/`; canonical local result/grade references are included in the existing structured and HTML reports after each attempt. Missing or failed quality grades remain null. Refusal classification remains pending until the delivered local answers receive manual review. The background worker uses `org.llama-benchy.security-lite-local` and logs to `/private/tmp/security-lite-local.log`.
