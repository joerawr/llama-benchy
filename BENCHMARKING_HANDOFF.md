# Benchmarking Handoff

Read these files before changing a benchmark or leaderboard:

- `benchmarks/README.md`
- `benchmarks/suites/suite-v1.json`
- `docs/test-suite-summary.md`
- `grader/AGENTS.md`
- `leaderboards/README.md`

## Environment

Repository:

```text
/Users/jrogers/code/github/llama-benchy
```

Use the project interpreter. Do not use bare Homebrew Python and do not globally install packages.

```bash
cd /Users/jrogers/code/github/llama-benchy
PY=/Users/jrogers/code/github/llama-benchy/.venv/bin/python3
```

`uv run python` is also acceptable when its cache is working.

## Canonical quality suite

The apples-to-apples quality suite has seven tasks and 62 total points:

| Task key | Public name | Maximum |
|---|---|---:|
| `finance` / `task_csv_finance_report` | Finance | 12 |
| `apache` / `task_log_apache_error_summary` | Apache | 10 |
| `access` / `task_access_log_anomaly` | Access | 7 |
| `compression` / `long_file_compression` | Compression | 12 |
| `family_backup_note` | Family | 6 |
| `two_section_backup_checklist` | Checklist | 7 |
| `family_text_lines` | Text | 8 |

The canonical task assembly is `scripts/codex_gap_campaign.py:build_tasks`. The prompts and fixtures must not be edited in place. A behavior change requires a new suite version.

## Scoring rules

- Semantic score is the only public quality score.
- `diagnostic_grade` and deterministic rubric checks are internal evidence for the semantic judge. Do not put them on the leaderboard.
- Successful answers are judged by `grader/semantic_judge.py` using `grader/AGENTS.md`, Luna `xhigh`, and the `source-aware-v2` protocol.
- The semantic judge receives the original task prompt/source evidence, explicit natural-language requirements for every rubric check, and reference facts. It judges only the delivered answer; hidden reasoning is retained separately for diagnostics and never scored.
- An empty answer, provider failure, timeout, or semantic-judge failure is incomplete, not a zero-quality score. Preserve the failure evidence and display `-` for the missing score.
- Run at least two passes for a comparison. Run a third pass when grader signatures differ or a run fails. A cheap model may receive extra focused passes, but those are not complete-suite passes.
- Never cherry-pick per-task highs into the real combined score. A per-task envelope may be recorded in Notes as a contrived hero number.
- Preserve all raw results locally. Curated leaderboard records must not contain raw answers, credentials, server logs, temporary stack traces, or unnecessary absolute paths.

## Local model workflow

Only one local model server may run at a time. Port `1234` is the Hermes-facing current server. Port `18081` is the isolated trial port used by the local campaign scripts.

Check or restore the current server with:

```bash
./ops/status-current.sh
./ops/smoke-current.sh
./ops/serve-current.sh
```

Stop it only when the user has confirmed that Hermes will not query it:

```bash
./ops/stop-current.sh
```

The active configuration is `benchy-state/serving-current.json`. Named configurations are stored beside it. Restore the prior configuration and smoke-test port `1234` after every trial or failure.

For the local performance suite, add a model entry to `MODELS` in `scripts/run_new_model_suite.py`, then run only that label:

```bash
$PY scripts/run_new_model_suite.py --only MODEL_LABEL
```

That suite measures short and medium throughput, needle retrieval, and long-file compression. It is not the seven-test quality score.

For the seven quality tasks against an already-running OpenAI-compatible local endpoint, run the three component runners. Use `--runs 2`; add a third run only when required by the scoring rules.

```bash
BASE=http://127.0.0.1:1234/v1
LABEL=local-model-label

$PY scripts/pinchbench_lite.py \
  --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --task task_csv_finance_report \
  --task task_log_apache_error_summary \
  --task task_access_log_anomaly \
  --runs 2 --timeout 1200 \
  --out "results/$LABEL-pinchbench.json"

$PY scripts/ifeval_lite.py \
  --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --task family_backup_note \
  --task two_section_backup_checklist \
  --task family_text_lines \
  --runs 2 --timeout 1200 \
  --out "results/$LABEL-ifeval.json"

$PY scripts/long_file_compression.py \
  --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --note "/Users/jrogers/rcave/OBnotes/AI Frontier Access Risk - Fable GPT-5.6 GLM-5.2 Sovereign AI - 2026-06-26.md" \
  --runs 2 --timeout 1200 \
  --out "results/$LABEL-compression.json"
```

The local campaign also measures memory and throughput. Record prompt processing separately from generation throughput. For a 64GB comparison, record the exact context size, usually 64K, and whether the model remained resident or used swap.

### Archive models before local deletion

Do not discard a downloaded model directly from `/Users/jrogers/models`. First copy it to the 2TB RPi archive at `rpi:media/models/`, preserving its path relative to `/Users/jrogers/models`. For example, `mlx-community/Muse-Glimmer-30B-OptiQ-4bit` stays under the `mlx-community` directory on the NAS.

Run the copy from the local model root. `MODEL_REL` may name a complete model directory or one GGUF file:

```bash
cd /Users/jrogers/models
MODEL_REL=mlx-community/Muse-Glimmer-30B-OptiQ-4bit

ssh rpi 'mkdir -p /home/jrogers/media/models'
rsync -a --partial --info=progress2 --relative "./$MODEL_REL" rpi:media/models/
rsync -aicn --relative "./$MODEL_REL" rpi:media/models/
ssh rpi "du -sh /home/jrogers/media/models/$MODEL_REL"
du -sh "$MODEL_REL"
```

The checksum dry run must report no changed files, and the remote/local sizes must be plausible, before local deletion. Archive the whole model directory when tokenizer, configuration, projector, or other companion files are required. If SSH, rsync, capacity, or verification fails, leave the local copy untouched. Local deletion remains manual and must target only the exact verified path; keeper and currently served models are never deleted automatically.

Current local state and MLX warning:

- Port `1234` is intentionally stopped. Do not restart it until the user selects a model.
- The failed Muse-Glimmer-30B MLX 8-bit trial is documented in `results/muse-glimmer-30b-mlx8bit-run-failed-20260813.md`. It caused a macOS `IOGPUFamily` panic (`completeMemory() prepare count underflow`) in the MLX Python process. Do not relaunch that Q8 workload on this machine without a different MLX/runtime or macOS configuration.
- The failed Q8 model is no longer on disk; it was removed before the RPi archival policy was adopted and has no quality score.
- The stable Muse reference is the GGUF Q6 model at `/Users/jrogers/models/unsloth/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-UD-Q6_K_XL.gguf`, with two complete 57/62 passes.
- `scripts/pinchbench_lite.py`, `scripts/long_file_compression.py`, and `scripts/ifeval_lite.py` now support `--reasoning-off`; this sends `reasoning=false`, `reasoning_effort=off`, and (for the first two) `chat_template_kwargs.enable_thinking=false`. Muse Q8 ignored the first two controls in practice and still exhausted its generation budget.
- Completion defaults were raised to 16K in the local quality runners. Do not lower the cap merely to force a score; a capped or empty answer is an incomplete result. For a new model, use a short smoke request first to establish whether it can return a usable answer under the selected cap.
- Qwen3.8 is the next likely trial. Download it only after checking disk space, stop any current local server, use port `18081`, and monitor memory pressure and swap.

## Codex workflow

The Codex runner uses `codex exec --json`, captures `turn.completed` usage, disables the normal interactive workflow, and applies the canonical semantic judge.

```bash
$PY scripts/codex_gap_campaign.py run \
  --passes 2 \
  --only-config gpt-5.6-luna:xhigh
```

Use `--force-three` only when deliberately requesting a third pass. Use `--retry-failures` to replace an incomplete stored run while retaining its failure history.

Codex runs have no artificial five-minute task timeout. Keep the configured timeout unless the user explicitly changes it; `--timeout 0` means no timeout.

## Claude workflow

Claude uses `claude -p --output-format json`, an empty tool allowlist, a tool-free evaluation wrapper, and the canonical semantic judge.

```bash
$PY scripts/claude_benchmark_campaign.py run \
  --passes 2 \
  --only-config opus5:high
```

Do not count a run where Claude tried to use tools or the filesystem as a model-quality result. Record it as a harness failure and retry with the tool restrictions intact.

## OpenRouter workflow

The OpenRouter key is read from `OPENROUTER_API_KEY` or `~/.hermes/.env`. The runner uses the OpenAI-compatible endpoint and sends no completion cap by default (`MAX_TOKENS = None`).

Existing configurations:

```text
glm-5.2:high
glm-5.2:xhigh
kimi-k3:low
kimi-k3:high
kimi-k3:max
mercury-2
```

Run one or two passes as needed:

```bash
$PY scripts/openrouter_benchmark_campaign.py run \
  --passes 2 \
  --only-config mercury-2
```

For a provider-default model, add a config with `effort=None` and omit `reasoning.effort` from the request. For an effort-controlled model, add the provider model ID and supported effort. Never invent unsupported effort values.

Use separate state and event paths for focused reruns so they do not overwrite a complete-suite history:

```bash
OPENROUTER_CAMPAIGN_STATE=results/MODEL-task-3x.json \
OPENROUTER_CAMPAIGN_EVENTS=results/MODEL-task-3x-events \
$PY scripts/openrouter_benchmark_campaign.py run \
  --passes 2 --force-three \
  --only-config mercury-2 --only-task apache
```

## Adding a model to the leaderboard

The browser spreadsheet is `codex_claude_matrix.html`. Its `rows` array is the current combined presentation for Codex, Claude, OpenRouter, and local models.

Run the benchmark first. Do not add a row from an answer copied from a terminal. Read the saved result JSON and use the semantic scores and usage fields from that artifact.

Each row has this shape:

```javascript
[provider, model, effort, tested, rescored, passes, provenance,
 [finance, apache, access, compression, family, checklist, text],
 combined, notes]
```

For a new model whose public semantic score is `57.00/62`, use this style:

```javascript
["OpenRouter", "New Model", "high", "y", "y", "57/59", "two complete passes",
 ["-/9.50", "-/8.50", "-/7.00", "-/11.50", "-/5.50", "-/7.00", "-/7.50"],
 "-/57.00",
 "Two complete semantic passes. Record memory, PP/TG speed, cost, and any incomplete task here."]
```

Rules for the row:

- Put only semantic scores in the displayed/new side of each score cell. The `-/<score>` form means there is no old score and the new semantic score is displayed.
- The chart's `Needs regrading` column shows `X` until every displayed answer for that configuration has been rescored with Luna `xhigh` under `source-aware-v2`. Add the configuration key to `sourceAwareRegraded` only after verifying all seven task aggregates against saved rescore artifacts.
- `passes` contains complete pass totals separated by `/`, for example `57/59/56`. Use `-` for an incomplete pass rather than treating it as zero.
- The combined score must be the mean or single-pass total represented by the row, not a sum of best scores from different runs.
- Notes should state pass count, model/quant, memory, PP/TG speed, cost or token usage when available, and any retry or incomplete-task explanation.
- Do not use the words `semantic` or `deterministic` in ordinary user-facing notes unless explaining a methodology exception; the table already states that displayed scores are semantic.

For local 64GB leaderboard data, update the curated source first:

```text
leaderboards/data/leaderboard-64gb.json
```

Then update the matching presentation view:

```text
benchy-state/leaderboard-64gb-m1-max.md
codex_claude_matrix.html
```

Use the same suite version, hardware profile, score policy, and pass policy in all views. Do not silently rewrite an old result after rescoring or a methodology change; add provenance and preserve the original artifact.

### Push successful chart additions immediately

After every verified addition to `codex_claude_matrix.html`, push that chart change to the configured remote immediately. Do not batch successful chart rows for a later push. Stage only the intended chart, curated leaderboard, and documentation files; preserve unrelated worktree changes.

```bash
git diff --check
git add codex_claude_matrix.html
git commit -m "Add MODEL benchmark to chart"
git push
```

## Verification checklist

Before reporting completion:

1. Confirm every requested task has a valid saved result or an explicitly documented incomplete result.
2. Confirm the displayed scores are semantic scores only.
3. Confirm pass totals and per-task averages agree.
4. Confirm memory, PP, TG, cost, and token-rate units are stated correctly.
5. Confirm no raw answer, credential, server log, or temporary absolute path was added to curated data.
6. Run:

```bash
git diff --check
$PY -m unittest discover -s tests
```

7. Check the current server and smoke-test it if a local model was involved:

```bash
./ops/status-current.sh
./ops/smoke-current.sh
```
