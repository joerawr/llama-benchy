# Needle Depth Sweep

`scripts/needle_depth_sweep.py` is the harder replacement for the original single-note hackstack test.

It builds synthetic private audit records, inserts them into noisy haystacks, and grades exact JSON answers. Haystacks can be generated from local files or from redacted private log seed corpora.

## Collect NUC8 Seed Logs

The helper copies the requested Hermes log directories from `rawrclaw@nuc8` into `/private/tmp`, then writes a redacted seed corpus:

```bash
./ops/collect-nuc8-seeds.sh
```

Default output:

```text
/private/tmp/llama-benchy-haystack-seeds/nuc8
```

The redactor removes common token, API key, bearer, password, long hex/base64, and private-key patterns. The seed corpus is not written into the repository.

## Adaptive 32K-First Run

Run the hardest context first and skip lower contexts when it passes:

```bash
uv run python scripts/needle_depth_sweep.py \
  --base-url http://127.0.0.1:18081/v1 \
  --model gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
  --label gemma4-12b-qat-q4xl \
  --seed-dir /private/tmp/llama-benchy-haystack-seeds/nuc8 \
  --ctx 32768 16384 8192 \
  --depth 0.1 0.5 0.9 \
  --runs 3 \
  --difficulty decoy \
  --adaptive \
  --out results/needle-depth-gemma4-12b-qat-q4xl.json
```

For a quick integration test:

```bash
uv run python scripts/needle_depth_sweep.py \
  --base-url http://127.0.0.1:18081/v1 \
  --model gemma-4-12B-it-qat-UD-Q4_K_XL.gguf \
  --label gemma4-12b-qat-q4xl \
  --seed-dir /private/tmp/llama-benchy-haystack-seeds/nuc8 \
  --ctx 32768 16384 8192 \
  --depth 0.5 \
  --runs 1 \
  --difficulty decoy \
  --adaptive \
  --out results/needle-depth-gemma4-12b-qat-q4xl-smoke.json
```

## Difficulties

- `single`: one exact field.
- `multi`: several fields from one inserted record.
- `decoy`: current value plus old/revoked and nearby-packet distractors.
- `reasoning`: join packet-to-valve and valve-to-risk facts.

`decoy` is the default because `single` is likely too easy for the current top models.
