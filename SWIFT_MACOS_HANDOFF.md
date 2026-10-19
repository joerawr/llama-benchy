# Swift 1.5: Linux results and macOS handoff

Test date: 2026-10-19. The next experiment is the same two GGUF files on the
same M1 Max after rebooting into macOS, using Metal instead of Linux Vulkan.
The full quality campaign is paused. Do not start it automatically.

## What we measured

Five-minute, sequential speed probes on an M1 Max with 64 GB RAM, Arch Linux
aarch64 / Asahi, Honeykrisp Mesa 26.2.4-arch1.1. The GPU runtime was
`ggml-org/llama.cpp` commit `9c2e0e491a822adae1f0b1c831adb4160057d24f`,
build `b1-9c2e0e4`, compiled with GNU 16.1.1.

| Model | Model file, decimal GB | Generation tok/s | Prompt tok/s | Generated tokens | Completed answers |
|---|---:|---:|---:|---:|---:|
| Swift 1.5 GSQ-RCO IQ3_S | 11.77 | **1.28** | 13.05 | 369 | 0 |
| Swift 1.5 Q6_K | 23.86 | **5.22** | 17.61 | 1,421 | 2 |

Q6_K was about **4.08 times faster** on this Linux Vulkan setup. Joe rejected
IQ3_S's 1.28 tok/s as unusable for this workflow on this backend. Both models
are still worth reproducing on macOS to measure the backend difference.
Metal performance has not been measured in this session.

These are throughput observations, **not accuracy scores**. Completed answers
were not graded. The final response of each probe was intentionally cut off
when its five-minute window expired. That is not a quality failure or a zero.

Curated measurements, including individual backend timings, live in
[the run record](benchmarks/runs/swift-1.5-linux-vulkan-speed-20261019.json).
Raw responses, reasoning traces, SSE streams and logs are retained locally in
`results/swift-five-minute-speed-20261019/`; they are intentionally excluded
from Git. The curated record and this handoff will be available after a pull.

### Earlier 27B reference speeds

The saved August macOS throughput artifacts recorded **9.77–10.18 tok/s** for
Qwen3.8 27B GGUF UD-Q6_K_XL, and **12.78–13.57 tok/s** for Qwen3.6 27B MTPLX
Optimized Speed V2. Those medium sweeps used 512/2,048-token prompts,
128-token responses, and either no preceding context or 4,096 tokens of
preceding context. The older MTPLX short sweep reached 13.59 tok/s.
The curated run record includes extracted sweep values and source hashes.

Exact hardware and all serving controls were not recorded in those throughput
artifacts, and MTPLX used its optimized MTP path. They are historical reference
points rather than matched Swift OS measurements. The October 8 Linux/Vulkan
short tests recorded Swift 1.0 Q6_K at 5.69 tok/s and ThinkingCap Q6_K at
5.29 tok/s, with different task/sampling controls from today's probe.

## Exact probe settings

- Task: the existing `family_text_lines` benchmark, a short five-line family
  message with exact formatting and vocabulary constraints. Its frozen prompt
  is [swift-speed-family-text-v1.txt](benchmarks/suites/swift-speed-family-text-v1.txt).
- Each model gets a 300-second wall window **after loading and verification**.
  Prompt processing counts against the window. If an answer finishes early,
  repeat the same task with the next seed until the window ends.
- Thinking enabled; `reasoning_effort=xhigh`; unrestricted reasoning budget.
  The rendered chat prompt was checked for the actual xhigh instruction and
  open thinking prefix. Merely sending an effort field is insufficient.
- Both pinned GGUFs contain the same native chat template. Its SHA-256 is
  `c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041`.
  The portable runner extracts it directly from the weights and verifies it.
- Context 32,768; one slot; batch/microbatch 128; four CPU threads; 99 GPU
  layers requested; f16 K and V cache; MTP/speculative decoding off; context
  shift off; prompt caching off. No completion-token cap.
- Sampling: temperature 1.0, top-p 0.95, top-k 20, min-p 0, presence penalty 0,
  repetition penalty 1. Seeds are `20261019 + request_index`, starting at 1,
  reset for each model.
- Generation rate = summed backend `predicted_n` divided by summed
  `predicted_ms / 1000`; it includes thinking and final/control tokens.
  Prompt rate is computed separately from `prompt_n` and `prompt_ms`.
  Model loading, hashing, and grading are excluded from these token rates.

## ThinkingCap was stopped

ThinkingCap is a **Qwen3.6-27B fine-tune**, not stock Qwen3.8. It was selected
because its Q6_K file was already local, not because we had established that
it beat other Qwen variants. There is no such accuracy result in this session.

The cancelled Finance attempt processed 5,732 prompt tokens and had generated
6,748 thinking tokens after **27.8 minutes**, with **no final answer** at the
cancellation snapshot. The prompt asked for returns, volatility, best/worst
days, streaks and drawdown from the 2014 Apple stock CSV. It remains unscored.
The trace and cancellation evidence are saved under
`results/swift-qwen-thinking-20261019/` on Linux; a concise observation is also
included in the committed run record.

An older October 8 diagnostic only tested a short family-message task:
ThinkingCap exhausted a 1,536-token cap without answering twice, while Swift
1.0 completed both runs. That narrow, capped test does not establish general
model quality. ThinkingCap has no native named effort control; the cancelled
attempt used the shared Swift/Qwen3.8 template to supply the xhigh instruction.

The proposed harder quality subset was Finance plus Compression (/24).
Compression's embedded `/no_think` directive was removed only in a new frozen
thinking experiment, not in the canonical suite. No complete quality result
was produced. Do not treat these speed probes as a seven-task /62 benchmark.

## Why Swift was prioritized

Monthly Hugging Face repository download counts observed on October 19:

| Repository | Downloads |
|---|---:|
| [Swift 1.5 GSQ-RCO GGUF](https://huggingface.co/ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF) | 1,188,036 |
| [Swift 1.5 standard GGUF](https://huggingface.co/ukisai/Swift-1.5-Qwen3.8-27B-GGUF) | 247,100 |
| [Swift 1.5 4-bit MLX](https://huggingface.co/ukisai/Swift-1.5-4bit-MLX) | 4,364 |
| [Swift 1.5 5-bit MLX](https://huggingface.co/ukisai/Swift-1.5-5bit-MLX) | 2,951 |
| [GazTrab RCO-DWQ MLX](https://huggingface.co/GazTrab/Swift-1.5-Qwen3.8-27b-RCO-DWQ-MLX) | 329 |

These are repository-level adoption signals, not per-quant counts or accuracy
rankings. The original MLX options need macOS; the Linux pair used official
GGUF IQ3_S and higher-precision Q6_K. For the OS comparison, keep the same
GGUFs and change the inference backend to Metal. Testing MLX would be a
separate experiment that changes the format/runtime as well.

## Model archive on the RPi

Both models are archived under `rpi:media/models/ukisai/`, preserving the local
model-directory names. A `download-provenance.json` travels with each model.
Local originals remain in `~/models/ukisai/` on Linux; no model was deleted.

| Model directory | File | Bytes |
|---|---|---:|
| `Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF` | `Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` | 11,771,546,912 |
| `Swift-1.5-Qwen3.8-27B-GGUF` | `Swift-1.5-Qwen3.8-27B-Q6_K.gguf` | 23,860,565,696 |

Pinned revisions and SHA-256:

```text
GSQ-RCO repository revision: d74895bbe5db4bec1e0024e7cc87d59c02d7631a
IQ3_S SHA256: 1333c6ea70ef348d4ac6d62732772e8ad6571ac5b3754c14ed54f1a0d904a786

Standard GGUF repository revision: 14bfe4b42be4a925d98816db830155f476c605e7
Q6_K SHA256: cd2eb6597026ce4eb86100e830be24f01461f84b89d4708634c2ec3d43b67fa8
```

Archive verification status is recorded in the run JSON. Final verification
requires the remote SHA-256 values to match and the checksum rsync dry run to
report no differences. Do not reboot until the session reports that complete.

## Repeat on macOS

Run inside the existing macOS clone. Its `main` should track
`joerawr/llama-benchy`, not the original `eugr` upstream.

```bash
git pull --ff-only
uv sync --all-extras --dev
mkdir -p "$HOME/models/ukisai"

rsync -a --partial --progress \
  rpi:media/models/ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF/ \
  "$HOME/models/ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF/"
rsync -a --partial --progress \
  rpi:media/models/ukisai/Swift-1.5-Qwen3.8-27B-GGUF/ \
  "$HOME/models/ukisai/Swift-1.5-Qwen3.8-27B-GGUF/"
```

Use a native GPU-enabled `llama-server`. To keep the llama.cpp revision
matched, build the Linux-tested commit with Metal. This needs Xcode Command
Line Tools and CMake already available on macOS:

```bash
mkdir -p "$HOME/src"
git clone https://github.com/ggml-org/llama.cpp.git \
  "$HOME/src/llama.cpp-swift-comparison"
git -C "$HOME/src/llama.cpp-swift-comparison" checkout \
  9c2e0e491a822adae1f0b1c831adb4160057d24f
cmake -S "$HOME/src/llama.cpp-swift-comparison" \
  -B "$HOME/src/llama.cpp-swift-comparison/build-metal" \
  -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON -DGGML_NATIVE=ON \
  -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TESTS=OFF
cmake --build "$HOME/src/llama.cpp-swift-comparison/build-metal" \
  --target llama-server -j4
```

Check the model copies, native template and Metal device without inference:

```bash
.venv/bin/python scripts/run_swift_speed_probe.py \
  --server "$HOME/src/llama.cpp-swift-comparison/build-metal/bin/llama-server" \
  --models-root "$HOME/models" \
  --out results/swift-macos-preflight-20261019 \
  --prepare-only
```

Then run the same five-minute probe for each model:

```bash
.venv/bin/python -u scripts/run_swift_speed_probe.py \
  --server "$HOME/src/llama.cpp-swift-comparison/build-metal/bin/llama-server" \
  --models-root "$HOME/models" \
  --out results/swift-five-minute-speed-20261019-darwin \
  --seconds 300
```

The runner verifies both complete model hashes, extracts the native template,
checks the rendered xhigh prompt, runs the models sequentially on port 18081,
and stops afterward. On macOS it selects the runtime's Metal GPU, does not
invoke systemd, and refuses to compete with another `llama-server` process.
Use a fresh output directory for every rerun. `--only-model swift15-q6` or
`--only-model swift15-gsq-iq3s` restricts the probe when desired.

Inspect `report.json` under the selected output directory. Record the actual
runtime version and GPU inventory (the runner saves both). Keep the Linux
record intact and add a separate macOS result. Choose the next quality test
only after reviewing the OS comparison together.

## Background service clarification

Before this session's tests, Linux already had an enabled, running
`joe-local-model.service` serving **Swift 1.0 Q6_K**, context 2,048, on
`localhost:18082`. It came from the October 8 setup. The `llama-server` on PATH
was a different CPU-only build, and the initial sandbox hid `/dev/dri`; those
checks initially led to an incorrect CPU-only conclusion. Host checks
confirmed the existing Vulkan runtime and GPU service.

The probes temporarily stopped that existing service and restarted it afterward.
Its configuration and selected model were not changed. After both probes,
the original service was active and its health check returned `ok`.
No benchmark or full quality campaign is left running. Model copying and
verification are separate from inference.
