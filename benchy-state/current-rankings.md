# Current Rankings — Cross-Lane Summary

The authoritative per-machine leaderboards are `benchy-state/leaderboard-16gb-mini.md` and `benchy-state/leaderboard-64gb-m1-max.md`. This file is a compact cross-lane view only.

## 64GB Main Machine

| Rank | Model | Role | Evidence |
|---:|---|---|---|
| 1 | Gemma 4 26B QAT Q4_K_XL | Fast/log-heavy default candidate | 14.96 GiB @64K, 56.8 tok/s at 2048/d4096, Apache 8/10, access 7/7, compression 11/12 |
| 2 | Gemma 4 26B A4B Q4_K_S | Best compression-quality default | 16.95 GiB @64K, compression 12/12, finance 9/12, access 7/7 |
| 3 | Qwen APEX-MTP Balanced | Analytical/report specialist | 25.56 GiB @64K, finance 11/12, compression 11/12 |

## 16GB Mini

| Rank | Model | Role | Evidence |
|---:|---|---|---|
| 1 | Gemma 4 12B QAT Q4_K_XL | Offline log/triage batch model | 7.88 GiB @64K, Apache 8/10, access 7/7, compression 11/12 |
| 2 | Qwen3.5 9B Q4_K_M | Cheap general fallback | 6.90 GiB @64K, Apache 8/10, finance 8/12, compression 11/12 |
| 3 | Open slot | Nightly discovery target | Prefer <=12B dense or low-active MoE GGUF |

## Promotion Rule

Nightly scouts can recommend a replacement. Promotion is manual and requires updating `benchy-state/serving-current.json`, then restarting the Hermes-facing server.
