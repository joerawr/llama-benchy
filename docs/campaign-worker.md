# Campaign worker

`campaign_worker.py` is the durable single-worker coordinator for a `main64` campaign. It never accepts executable commands in a manifest. Start one real worker (the normal supervisor path):

```sh
uv run python scripts/campaign_worker.py launch --manifest campaign.json --execute
# immediately prints: campaign_id, pid, state_path, log_path
```

`launch` atomically writes `benchy-state/campaign-state.json`, starts detached `uv run python ... worker`, and records the exact worker command/PID/log. `--foreground` is test/development-only. Inspect without service control:

```sh
uv run python scripts/campaign_worker.py status
uv run python scripts/campaign_worker.py cancel
```

## Safe manifest

```json
{
  "campaign_id": "2026-07-10-main64",
  "lane": "main64",
  "retain_top_n": 4,
  "candidates": [{
    "id": "mlx-example",
    "backend": "mlx",
    "model_dir": "/Users/jrogers/models/_nightly-candidates/mlx-example",
    "repo_id": "org/model"
  }, {
    "id": "gguf-example",
    "backend": "llama",
    "file": "/Users/jrogers/models/_nightly-candidates/gguf-example/model-IQ4_XS.gguf",
    "mmproj": "/Users/jrogers/models/_nightly-candidates/gguf-example/mmproj.gguf"
  }]
}
```

All model/projector paths must be absolute and resolve beneath the scratch root. GGUF Q4+ including IQ4 is allowed; Q3/lower is rejected. `commands` is rejected. A canonical immutable manifest hash prevents resume with edited or reordered candidates.

## Workflow and supervision

The lock at the repository-absolute `benchy-state/campaign.lock` is held for a worker’s lifetime. Candidates run serially: exact HF download (or existing-path validation), managed-server status/stop, only a loopback `127.0.0.1:18081` trial server, readiness, 64K gate, short throughput, medium throughput, and direct three-run PinchBench. Commands use `sys.executable` for project Python. Every phase records command, return code, log, result path, error, and transition atomically.

The worker owns only its spawned trial process group. `current_server.py start` then `smoke` is performed after **every** candidate in `finally`, including failure/cancel. It never edits `serving-current.json`. It refuses to *start* a disruptive candidate during local `:12`–`:25`; `--allow-protected-window` only overrides that dynamic gate. Restoration remains permitted.

Two weak Apache results (score below `0.60`) record `early_stop`; credible candidates may continue to IFEval/compression as future phase extensions. Terminal state is persisted **before** Telegram. Notification records are independently `sent`, `failed`, or `skipped`, so retry never reruns benchmarks or relabels a benchmark failure.

Campaign ranking is quality score first, then 64K fit, then short generated-token throughput. Only terminal tested candidates with 64K and quality result evidence can be retained. After ranking, exactly the non-kept candidate’s own scratch directory may be deleted—never the scratch root, and never with missing result evidence. State contains job, log/server-log and per-result links for live supervisors.
