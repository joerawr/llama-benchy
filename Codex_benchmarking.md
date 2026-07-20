# Codex Benchmarking

## Scope

This comparison measures the work this system is intended to perform: finance-report extraction, Apache-log summarization, access-log anomaly analysis, constrained family-facing writing, and long-file compression.

Scores are per-run averages. The adaptive runner starts with two runs and adds a third when the complete grader signatures differ or a run fails. A matching scalar score is not enough to skip the third run; every rubric check must match.

The six core tests total 50 points:

| Test | Maximum |
|---|---:|
| Finance | 12 |
| Apache | 10 |
| Access anomaly | 7 |
| Family note | 6 |
| Two-section checklist | 7 |
| Family text message | 8 |

Compression adds 12 points, producing a combined maximum of 62.

## All Codex Results

The bold row is the best core `/50` result within each model family. Results are ordered Sol, Terra, Luna as requested.

| Model | Effort | Finance `/12` | Apache `/10` | Access `/7` | Family `/6` | Checklist `/7` | Text `/8` | Core `/50` | Compression `/12` | Combined `/62` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sol | low | 8.00 | 7.67 | 7.00 | 6.00 | 7.00 | 7.33 | 43.00 | 11.00 | 54.00 |
| **Sol** | **medium** | **9.00** | **8.33** | **7.00** | **6.00** | **7.00** | **7.00** | **44.33** | **11.00** | **55.33** |
| Sol | high | 8.00 | 9.00 | 7.00 | 6.00 | 7.00 | 7.00 | 44.00 | 10.67 | 54.67 |
| Terra | low | 9.00 | 7.67 | 7.00 | 6.00 | 7.00 | 7.00 | 43.67 | 9.67 | 53.34 |
| **Terra** | **medium** | **10.67** | **7.33** | **7.00** | **5.67** | **7.00** | **7.00** | **44.67** | **9.67** | **54.34** |
| Terra | high | 10.33 | 6.67 | 7.00 | 6.00 | 7.00 | 7.00 | 44.00 | 9.33 | 53.33 |
| Terra | xhigh | 11.00 | 6.67 | 7.00 | 5.67 | 7.00 | 7.00 | 44.34 | 10.00 | 54.34 |
| Luna | low | 8.00 | 8.00 | 7.00 | 5.67 | 6.67 | 7.00 | 42.34 | 10.33 | 52.67 |
| Luna | medium | 9.00 | 8.33 | 7.00 | 6.00 | 7.00 | 7.00 | 44.33 | 11.00 | 55.33 |
| **Luna** | **high** | **11.33** | **7.67** | **7.00** | **6.00** | **7.00** | **7.00** | **46.00** | **9.67** | **55.67** |
| Luna | xhigh | 8.67 | 8.33 | 7.00 | 6.00 | 7.00 | 7.00 | 44.00 | 10.67 | 54.67 |

Reasoning effort is not a monotonic quality control. Luna peaks at high and regresses at xhigh. Terra peaks at medium on the core suite; xhigh spends substantially more time for a slightly lower core result. Sol peaks at medium overall, while high is specifically stronger on Apache.

## Best Configuration Per Family

| Rank | Model | Effort | Finance `/12` | Apache `/10` | Access `/7` | Strict subtotal `/21` | Core `/50` | Compression `/12` | Combined `/62` |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Luna | high | 11.33 | 7.67 | 7.00 | 20.00 | **46.00** | 9.67 | **55.67** |
| 2 | Terra | medium | 10.67 | 7.33 | 7.00 | 19.67 | **44.67** | 9.67 | **54.34** |
| 3 | Sol | medium | 9.00 | 8.33 | 7.00 | 20.00 | **44.33** | 11.00 | **55.33** |

Luna high is the strongest general configuration. Terra medium is the best Terra setting and avoids xhigh's large reasoning cost. Sol medium nearly matches Luna high after compression is included, and Sol high remains the strongest Codex Apache configuration at 9/10.

## Local Models Versus Lowest Codex Configuration

This chart selects the lowest core-scoring tested effort from each Codex family, then adds the current local finalists. Ranking uses all seven common tests, including compression, for a combined `/62`.

| Rank | Model | Type | Finance `/12` | Apache `/10` | Access `/7` | Family `/6` | Checklist `/7` | Text `/8` | Core `/50` | Compression `/12` | Combined `/62` |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Sol low | Codex | 8.00 | 7.67 | 7.00 | 6.00 | 7.00 | 7.33 | 43.00 | 11.00 | **54.00** |
| 2 | Terra low | Codex | 9.00 | 7.67 | 7.00 | 6.00 | 7.00 | 7.00 | 43.67 | 9.67 | **53.34** |
| 3 | Gemma 4 26B QAT Q4_K_XL | Local | 8.00 | 8.00 | 7.00 | 4.00 | 7.00 | 8.00 | 42.00 | 11.00 | **53.00** |
| 3 | Gemma 4 26B Q4_K_S | Local | 9.00 | 6.00 | 7.00 | 5.00 | 6.00 | 8.00 | 41.00 | 12.00 | **53.00** |
| 5 | Luna low | Codex | 8.00 | 8.00 | 7.00 | 5.67 | 6.67 | 7.00 | 42.34 | 10.33 | **52.67** |
| 6 | Qwen APEX-MTP Balanced | Local | 11.00 | 6.00 | 5.00 | 5.00 | 7.00 | 7.00 | 41.00 | 11.00 | **52.00** |
| 6 | Gemma 4 12B QAT Q4_K_XL | Local | 7.00 | 8.00 | 7.00 | 4.00 | 7.00 | 8.00 | 41.00 | 11.00 | **52.00** |
| 8 | Qwen3.5 9B Q4_K_M | Local | 8.00 | 8.00 | 5.00 | 4.00 | 4.00 | 7.00 | 36.00 | 11.00 | **47.00** |

On the core `/50`, none of the local models beats the lowest tested Codex configuration from any family. Once compression is included, both Gemma 26B variants edge past Luna low: 53.00 versus 52.67. This supports a practical conclusion: if Luna low is the affordable Codex tier, a strong local Gemma may be competitive for these workloads and can be better for compression while avoiding remote usage cost.

## Efficiency Notes

`codex exec --json` reports input, cached-input, output, and reasoning tokens. Effective output rate is end-to-end output tokens divided by elapsed wall time; it is not pure inference throughput.

The corrected high-compute campaign removed the agent-imposed five-minute timeout. The earlier cutoff censored valid slow responses: Luna xhigh Apache later completed in 158 seconds, while Terra xhigh Apache completed in 214 and 173 seconds. Same-task latency varied widely between runs, so elapsed time and token use must be treated as distributions rather than fixed model speeds.

The xhigh configurations did not justify their additional cost for this workload:

| Configuration | Calls | Total wall time | Output tokens | Reasoning tokens | Effective output rate |
|---|---:|---:|---:|---:|---:|
| Luna xhigh | 17 | 19.9 min | 90,528 | 40,147 | 75.9 tok/s |
| Terra xhigh | 16 | 15.9 min | 72,727 | 52,920 | 76.1 tok/s |
| Sol high | 16 | 10.7 min | 40,748 | 26,650 | 63.6 tok/s |

## Artifacts

- `results/codex-agent-quality-luna-low-medium.json`
- `results/codex-agent-quality-luna-high-terra-low-medium.json`
- `results/codex-agent-quality-terra-high-sol-low.json`
- `results/codex-apples-gap-campaign-20260714.json`
- `results/codex-apples-gap-events-20260714/`
- `scripts/codex_gap_campaign.py`
