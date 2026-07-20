# Nightly Model Scout Guidelines

## Goal

Find at most one new local model candidate worth benchmarking. Prefer models that could improve either the 64GB main machine leaderboard or the 16GB mini offline-batch slot.

## Target Lanes

The two scheduled scouts are deliberately separate. A report must name its lane and compare only to that lane's leaders unless the cross-lane comparison is material.

### 16GB Mac mini

- Select dense models at or below 12B, or low-active MoEs, with projected 64K Metal memory under 10 GiB.
- Evaluate Q4, Q5, Q6, or Q8 only when that exact quant fits the 10 GiB target; optimize quality-per-GiB and throughput, not merely Q4 file size.
- Do not spend a mini run on a model that only fits the 64GB Mac.

### 64GB Mac

- Select candidates that fit at 64K with meaningful operating headroom; dense models above 12B are allowed.
- Explicitly inspect available Q4, Q5, Q6, and Q8 GGUF quants. Test the single quant that answers the strongest quality-versus-memory question for the family; do not default to Q4 just because it is smaller.
- A different quant of an established family is valid only when it fills an untested quality/memory lane and could plausibly beat a 64GB leader.

## General Prefer

- GGUF models that run with llama.cpp on Metal.
- MoE models with low active parameters.
- Dense models at or below 12B for the mini lane; larger dense models only for the 64GB lane when they fit with headroom.
- QAT, imatrix, dynamic, XL, or other improved quants of families that already score well here.
- Q4 or better quantization. Q4_K_S, Q4_K_M, Q4_K_XL, IQ4, MXFP4/FP4, Q5, Q6, and Q8 are acceptable.
- Models likely useful for summarization, log triage, webpage/file compression, finance-style reports, or retrieval.
- 64K context or better when available.
- A single high-signal candidate over several marginal downloads.

## Consider With Caution

- MLX models: useful on Mac, but only test if they look clearly better than GGUF options.
- Coding-focused models: test only when they also claim strong general instruction/report quality.
- Higher quants: test when they fit a known memory target and could plausibly improve a current keeper.

## Avoid

- Dense models above 12B for the mini lane, or for the 64GB lane without a clear fit-and-quality rationale.
- Q3 or lower quantization, including IQ1/IQ2/IQ3, Q2, Q3, and UD-Q2/UD-Q3 variants.
- Server/GPU formats that do not run in the current harness, such as AWQ, NVFP4, FP8 safetensors, or vendor-specific stacks.
- Vision-only value where the text model is not independently useful.
- Duplicate quants that do not answer a specific question.
- Filling disk with multiple candidates in one run.
- Deleting or replacing keeper models automatically.

## Memory Targets

- 64GB main machine: compare against the top 64GB leaderboard.
- 16GB mini: prefer projected 64K memory under 10 GiB. If a model needs more, it must be compelling enough to test at a smaller context later.

## Decision Policy

The nightly job may recommend a promotion but must not change `benchy-state/serving-current.json`.
The nightly job may delete only files under `/Users/jrogers/models/_nightly-candidates`.
