# Nightly Model Scouts

Two alternating Hermes cron jobs discover and test local-model candidates without ever running concurrently or leaving the Hermes-facing model down:

| Lane | Schedule (local) | Hermes cron job | Focus |
|---|---|---|---|
| 16GB M1 Mac mini | Sun / Mon / Wed / Fri at 02:00 | `llama-benchy — 16GB Mac mini scout` | Dense ≤12B or low-active MoE below 10 GiB at 64K; quality per GiB and throughput |
| 64GB M1 Max | Tue / Thu / Sat at 02:00 | `llama-benchy — 64GB quant scout` | Main-machine candidates with headroom; investigate fitting Q4, Q5, Q6, and Q8 variants |

The legacy launchd job `com.jrogers.llama-benchy.nightly-test` is intentionally unloaded. Do not reload it or schedule either Hermes job on a night used by the other lane.

## Server safety

The Hermes-facing model is configured in `benchy-state/serving-current.json`.

```bash
python3 scripts/current_server.py status
python3 scripts/current_server.py stop
python3 scripts/current_server.py start
python3 scripts/current_server.py smoke
```

Each scout stops the current server before testing, uses an exit trap to restore it, and reports a smoke-test failure through Telegram. It may never modify `benchy-state/serving-current.json`; promotion is manual.

## Candidate discovery

`scripts/hf_model_scout.py` mirrors the Apple-Silicon browsing workflow:

1. Browse Hugging Face **Trending MLX**.
2. Browse Hugging Face **Trending GGUF**.
3. Supplement GGUF trending with fresh and popular GGUF candidates.
4. Record each candidate's source library in the generated JSON.

MLX candidates are retained as Apple-Silicon discovery candidates. GGUF candidates are additionally dry-run probed for usable Q4-or-better files because the current llama.cpp suite requires GGUF.

## Separate leaderboards

- `benchy-state/leaderboard-16gb-mini.md` is authoritative for mini runs.
- `benchy-state/leaderboard-64gb-m1-max.md` is authoritative for 64GB runs.
- `benchy-state/current-rankings.md` is a cross-lane summary only.

The 16GB lane accepts Q4/Q5/Q6/Q8 only if that exact quant projects below 10 GiB at 64K. The 64GB lane must explicitly examine fitting Q4, Q5, Q6, and Q8 options and choose one quant that answers a concrete quality-versus-memory question rather than defaulting to Q4.

## Manual dry run

Use the target explicitly. This interrupts and restores the current server, so do not run it during the protected `:12`–`:25` window.

```bash
NIGHTLY_TARGET=mini NIGHTLY_DRY_RUN=1 NIGHTLY_SCOUT_LIMIT=8 NIGHTLY_FILE_LIMIT=3 ./ops/nightly-scout.sh
NIGHTLY_TARGET=main64 NIGHTLY_DRY_RUN=1 NIGHTLY_SCOUT_LIMIT=8 NIGHTLY_FILE_LIMIT=3 ./ops/nightly-scout.sh
```

## Guardrails

- The selector chooses at most one candidate/quant per run.
- Candidate downloads must stay under `/Users/jrogers/models/_nightly-candidates`.
- Only rejected downloads under that scratch directory may be deleted.
- Keeper models and the serving configuration are never changed automatically.
- Telegram delivery is handled by `ops/telegram-report.sh`; do not print its credential file.
