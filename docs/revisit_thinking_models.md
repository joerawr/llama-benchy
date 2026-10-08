# Revisit: Thinking Models and the Ornith 1.5 Result

## Why Ornith 1.5 looked subpar in our benchmark

Our first complete Ornith 1.5 35B-A3B result was not an apples-to-apples test. We ran the model with reasoning disabled, even though Ornith is a thinking model whose intended mode has thinking enabled by default.

The reasoning-off run scored **51/62**:

| Test | Score |
|---|---:|
| Finance | 7/12 |
| Apache | 7/10 |
| Access | 5/7 |
| Compression | 11/12 |
| Family | 6/6 |
| Checklist | 7/7 |
| Text | 8/8 |
| **Total** | **51/62** |

Disabling reasoning is a plausible contributor; the partial rerun does not establish its effect on the full-suite gap. The later LM Studio test, with default thinking enabled, improved Access from 5/7 to 7/7; Apache remained 7/10, but Finance exceeded the 30-minute timeout before producing a result. It was therefore incomplete, not evidence that the model failed Finance.

## The benchmark mismatch

The vendor chart and our suite measure substantially different things.

The vendor results emphasize coding, terminal use, SWE-bench, MCP/tool use, and agentic software tasks. Their chart reports Ornith 1.5 ahead of Qwen3.6-35B-A3B on several of those evaluations.

Our suite puts more weight on:

- finance calculations and date interpretation;
- log counting and anomaly analysis;
- source-grounded, structured reports;
- compression and instruction-following constraints;
- exact output structure and rubric-sensitive formatting.

Strong performance on coding and tool-use benchmarks does not guarantee strong performance on this particular mixture. The result can reflect task specialization and evaluation design, not a general model-quality ranking.

There is also a scale difference: the OpenRouter Qwen3.6-35B-A3B result averaged **54.5/62** across two passes, while the local Qwen3.6 APEX I-Quality result is **54/62**. Ornith's 51/62 reasoning-off score is therefore about 3–3.5 points behind our best Qwen 35B-A3B results, not a collapse.

## Settings matter

“Reasoning parsing enabled” in LM Studio only tells the client how to display or separate `<think>...</think>` content. It does not by itself prove that the model's native thinking behavior was enabled through the correct chat template and generation configuration.

For a fair Ornith test, we should verify that:

1. the model's chat template is applied;
2. thinking is enabled;
3. the response parser is configured for `<think>` and `</think>`;
4. context length and output limits are identical across models;
5. the timeout is long enough for reasoning-heavy tasks;
6. sampling settings are recorded and held constant.

The output limit needs an explicit policy too. A 16K cap found in our local
quality runners is an operational guard against runaway reasoning and KV/Metal
memory growth; it is not a quality requirement of the suite. If a response
hits that cap, the task is incomplete and must be shown as `-`, not scored as
zero. A lower-cap diagnostic run may help establish hardware behavior, but it
must be labeled separately and must not be placed on the standard chart.

The Ornith model guidance commonly used for reproducing its reported results is thinking enabled with approximately `temperature=1.0`, `top_p=0.95`, and `top_k=20`. For a deterministic local comparison, we can instead use the benchmark's fixed low-temperature settings, but then those same settings must be used for both Ornith and Qwen3.6.

## What we can conclude now

We should not conclude that Ornith 1.5 is worse than Qwen3.6 from the current local result. The cleanest conclusion is:

- the first full run disabled reasoning and needs a matched comparison;
- the thinking-on rerun was only partial;
- the completed results are broadly consistent with a model that is competitive but not clearly ahead on our suite;
- the vendor chart demonstrates an advantage on its selected coding and agentic tasks, not necessarily on our benchmark's tasks.

The next fair comparison is two full passes of Ornith 1.5 with thinking on, documented sampling, identical prompts and output limits, and the same timeout policy used for the comparable Qwen3.6-35B-A3B runs. Until that is complete, the 51/62 result should be labeled **reasoning-off** rather than treated as the model's definitive score.

## References

- [Ornith-1.5-35B-A3B model card](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B-MLX-8bit)
- [Ornith 1.5 local-run guidance and reported benchmark context](https://atomic.chat/blog/guides/how-to-run-ornith-1-5-35b-locally)

## Experiment protocol

The thinking runners use `llama-benchy-thinking-comparison@1.0`, defined in
`benchmarks/suites/thinking-comparison-v1.json`. They remove the leading
`/no_think` directive from Compression and record the actual prompt hash.
These diagnostic results must not be pooled with the standard suite 1.1.
Model-card samplers differ between models; that is not a controlled quality
comparison until sampling is matched. Resume requires matching suite and
prompt provenance; select a new output path for older unversioned artifacts.
Ornith's MLX runner requires macOS/Metal; Linux trials need GGUF.
