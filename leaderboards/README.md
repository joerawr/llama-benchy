# Leaderboards

Leaderboard data is the canonical structured record of benchmark outcomes. Markdown tables and HTML dashboards are presentation views and must not contain scores that are absent from the structured data.

## Update procedure

1. Run a versioned benchmark suite and preserve the raw output locally.
2. Create a curated run record containing model, quant, backend, hardware, suite version, task scores, semantic scores, PP/TG throughput, memory, run count, and artifact references.
3. Record the benchmark Git commit and hashes for public fixtures or private inputs.
4. Add or update the appropriate JSON file under `leaderboards/data/`.
5. Regenerate Markdown and HTML views from the structured data.
6. Review the diff for accidental raw answers, logs, secrets, local paths, or unsupported methodology changes.
7. Commit the curated data and generated views together.

## Ranking policy

Quality is primary. For ties, use memory fit/headroom, then generation throughput, then prompt-processing throughput. Hosted and local models may be displayed together only when they used the same task definitions, scoring method, and valid-run policy.

Never replace an old score silently. Record rescoring or methodology changes as a new result record with its provenance.
