# ARM Linux migration and model testing

This repository is Python code plus benchmark data. It does not contain a
portable local inference binary. A virtual environment, native inference
server, and MLX model directory copied from macOS must not be reused on ARM
Linux.

## One-time migration

From the Linux checkout, rebuild the environment with the Linux interpreter:

```bash
cd /path/to/llama-benchy
uv sync --all-extras --dev
uv pip install --python .venv/bin/python cmake ninja
PY="$PWD/.venv/bin/python"

"$PY" -m pytest -q
```

Do not copy `.venv` between machines or operating systems. The old copied
environment will usually fail with a `bad interpreter` path pointing back to
the Mac. The `uv.lock` file can select the appropriate Linux ARM wheels.

## Local models on ARM Linux

Use a native Linux build of `llama.cpp` and a GGUF model. The existing MLX
entries are Apple-Silicon/Metal entries; `mlx_lm.server` and MLX model
directories are not replacements for `llama-server` on Linux.

For a CPU build, the upstream build shape is:

```bash
mkdir -p "$HOME/src"
git clone https://github.com/ggml-org/llama.cpp.git "$HOME/src/llama.cpp"
export PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH"
cmake -S "$HOME/src/llama.cpp" -B "$HOME/src/llama.cpp/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON \
  -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DCMAKE_BUILD_RPATH='$ORIGIN'
cmake --build "$HOME/src/llama.cpp/build" --target llama-server -j"$(nproc)"

# Keep the executable and companion libraries together; no sudo is needed.
mkdir -p "$HOME/.local/lib/llama-cpp" "$HOME/.local/bin"
cp -a "$HOME/src/llama.cpp/build/bin"/lib*.so* "$HOME/.local/lib/llama-cpp/"
install -m 0755 "$HOME/src/llama.cpp/build/bin/llama-server" "$HOME/.local/lib/llama-cpp/llama-server"
ln -s "$HOME/.local/lib/llama-cpp/llama-server" "$HOME/.local/bin/llama-server"
```

The `LLAMA_BUILD_TESTS=OFF` and `LLAMA_BUILD_EXAMPLES=OFF` options keep a
server-only build from producing an install manifest for unbuilt test/example
binaries. The explicit copy keeps the user-local server self-contained.

Use the matching llama.cpp backend for the actual Linux accelerator, if one
is available (for example CUDA or Vulkan). Do not enable Apple Metal or copy a
macOS `llama-server` binary. Check the resulting binary with:

```bash
command -v llama-server
llama-server --version
```

Start one GGUF model for a smoke test. Set `GPU_LAYERS=0` for CPU-only; use a
larger value only after confirming that the native accelerator build works.

```bash
MODEL="$HOME/models/vendor/model.Q4_K_M.gguf"
GPU_LAYERS=0
llama-server -m "$MODEL" \
  --host 127.0.0.1 --port 1234 -c 65536 -np 1 \
  -ngl "$GPU_LAYERS" --reasoning off --reasoning-budget 0
```

In another terminal, verify the OpenAI-compatible API before running a long
benchmark:

```bash
curl -fsS http://127.0.0.1:1234/v1/models
curl -fsS http://127.0.0.1:1234/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"model.Q4_K_M.gguf","messages":[{"role":"user","content":"Reply with exactly: ok"}],"temperature":0,"max_tokens":8}'
```

The checked-in `benchy-state/serving-current.json` was copied from the Mac and
currently names a `/Users/...` MLX model. Replace it with a Linux `backend:
llama` configuration and a real `.gguf` path before using
`./ops/serve-current.sh`; otherwise use the direct command above. The macOS
`ops/launchd/*.plist` file is not a Linux service definition.

For the performance suite, model paths are supplied by the local machine, not
by Git:

```bash
export LLAMA_BENCHY_MODEL_ROOT="$HOME/models"
"$PY" scripts/run_new_model_suite.py --only MODEL_LABEL
```

Use the seven-test quality suite only after the endpoint passes the smoke
test. Run two complete passes; add a third manually when grader signatures differ
or a run fails:

```bash
BASE=http://127.0.0.1:1234/v1
LABEL=local-model-label

"$PY" scripts/pinchbench_lite.py --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --task task_csv_finance_report --task task_log_apache_error_summary \
  --task task_access_log_anomaly --runs 2 --timeout 1200 \
  --out "results/$LABEL-pinchbench.json"

"$PY" scripts/ifeval_lite.py --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --task family_backup_note --task two_section_backup_checklist \
  --task family_text_lines --runs 2 --timeout 1200 \
  --out "results/$LABEL-ifeval.json"

"$PY" scripts/long_file_compression.py --base-url "$BASE" --model SERVED_MODEL --label "$LABEL" \
  --note benchmarks-files/compression/ai-frontier-access-risk-fable-gpt56-glm52-2026-06-26.md \
  --runs 2 --timeout 1200 --out "results/$LABEL-compression.json"
```

Record the GGUF quant, context size, resident memory, swap use, prompt
processing (PP), and generation (TG) throughput. An incomplete response is a
missing result, not a zero score.

## OpenRouter models

OpenRouter needs no local model, compiler, or GPU. Keep the key out of Git and
provide it through the environment (the runner also checks `~/.hermes/.env`):

```bash
export OPENROUTER_API_KEY='...'
OPENROUTER_CAMPAIGN_STATE=results/openrouter-MODEL.json \
OPENROUTER_CAMPAIGN_EVENTS=results/openrouter-MODEL-events \
"$PY" scripts/openrouter_benchmark_campaign.py run \
  --passes 2 --only-config mercury-2
```

The runner uses `https://openrouter.ai/api/v1`, sends the seven shared tasks,
keeps raw answers and usage in `results/`, and reports provider cost and token
rates. For a new model, add its provider model ID to `CONFIGS` in
`scripts/openrouter_benchmark_campaign.py`; use `effort=None` when the
provider supplies the reasoning setting. Use the model's documented effort
values only.

## Add a result to the browser spreadsheet

The presentation chart is `codex_claude_matrix.html`. Add a row only after
reading the saved JSON/state artifact, not from a terminal summary. Keep the
seven per-test semantic means, the actual complete-pass totals, and a note
with quant, memory, PP/TG, cost or token usage, and any incomplete/retried
task. Do not add API keys, raw answers, server logs, or temporary absolute
paths. A new local or OpenRouter row remains marked for regrading until its
saved answers have passed the chart's declared rescore process.

Useful references: the [llama.cpp build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md),
`BENCHMARKING_HANDOFF.md`, and `leaderboards/README.md`.
