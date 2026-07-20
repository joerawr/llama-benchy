# 64GB M1 Max Leaderboard

## Eligibility

A candidate must be a useful text model for summarization, log triage, webpage/file compression, finance-style reports, or retrieval, and fit at 64K context with meaningful operating headroom on the 64GB M1 Max.

## Rankings

| Rank | Model | Quant | Role | Evidence | Generated-token speed |
|---:|---|---|---|---|---|
| 1 | Gemma 4 26B QAT | Q4_K_XL | Fast/log-heavy default candidate | 14.96 GiB @64K; Apache 8/10; access anomaly 7/7; compression 11/12 | 62.9 tok/s short; 59.7 tok/s at 2K; 56.8 tok/s at 4K context + 2K prompt |
| 2 | Gemma 4 26B A4B | Q4_K_S | Best compression-quality default | 16.95 GiB @64K; compression 12/12; finance 9/12; access anomaly 7/7 | 52.3 tok/s short; 46.7 tok/s at 2K; 45.3 tok/s at 4K context + 2K prompt |
| 3 | Qwen APEX-MTP Balanced | Balanced | Analytical/report specialist | 25.56 GiB @64K; finance 11/12; compression 11/12 | 27.9 tok/s short; 43.2 tok/s at 2K; 35.9 tok/s at 4K context + 2K prompt |

### Speed measurement notes

Generated-token speed uses single-concurrency llama.cpp results. The comparison columns are: short (256-token prompt / 32-token response), normal 2K prompt (2K / 128), and a 4K context with a 2K prompt (4K context / 2K / 128). Prompt-ingestion throughput at the normal 2K workload is 611.5 tok/s for Gemma QAT, 598.3 tok/s for Gemma A4B, and 546.3 tok/s for Qwen APEX-MTP Balanced.

Sources: `results/gemma4-26b-a4b-qat-q4xl-short.json`, `results/gemma4-26b-a4b-qat-q4xl-medium.json`, `results/gemma4-26b-a4b-short.json`, `results/gemma4-26b-a4b-medium.json`, `results/qwen-apex-mtp-balanced-short.json`, and `results/qwen-apex-mtp-balanced-medium.json`.

## Evaluation and Promotion

For a credible family, explicitly inspect fitting Q4, Q5, Q6, and Q8 GGUF files. Benchmark the one quant that best answers a concrete quality-versus-memory question; do not default to Q4 solely because it is smaller. Promotion remains manual and must not change `benchy-state/serving-current.json` automatically.
