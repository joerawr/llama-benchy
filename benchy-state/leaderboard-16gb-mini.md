# 16GB M1 Mac mini Leaderboard

## Eligibility

A candidate must be a useful text model for summarization, log triage, webpage/file compression, finance-style reports, or retrieval, and project under 10 GiB of Metal memory at 64K context. Dense models must be at or below 12B unless a low-active MoE demonstrably fits the same envelope.

## Rankings

| Rank | Model | Quant | Role | Evidence | Generated-token speed |
|---:|---|---|---|---|---|
| 1 | Gemma 4 12B QAT | Q4_K_XL | Offline log/triage batch model | 7.88 GiB @64K; Apache 8/10; access anomaly 7/7; compression 11/12 | 30.9 tok/s short; 29.4 tok/s at 2K; 28.7 tok/s at 4K context |
| 2 | Qwen3.5 9B | Q4_K_M | Cheap general fallback | 6.90 GiB @64K; Apache 8/10; finance 8/12; compression 11/12 | 30.4 tok/s short; 31.7 tok/s at 2K; 30.3 tok/s at 4K context; 341 tok/s prompt ingestion at 2K |
| 3 | Open slot | — | Discovery target | A candidate that beats an incumbent on a relevant task without exceeding the 10 GiB @64K envelope | — |

### Speed measurement notes

Generated-token speed is measured at short, 2K-prompt, and 4K-context workloads. Qwen is modestly faster for normal 2K+ inputs and substantially faster at 2K prompt ingestion (341 tok/s versus Gemma's 234 tok/s). Sources: `results/gemma4-12b-qat-q4xl-medium.json` and `results/qwen35-9b-q4km-medium.json`.

## Evaluation and Promotion

Test Q4, Q5, Q6, or Q8 only when the exact quant remains within the 10 GiB 64K target. Rank quality first, then memory headroom and throughput. Promotion remains manual and must not change `benchy-state/serving-current.json` automatically.
