# Benchmark Definitions

Benchmark definitions are versioned inputs. A result must identify the suite version, task files, grader version, model, hardware profile, and run date.

## Rules

- Do not change a prompt, fixture, rubric, or semantic-judge instruction in place.
- Create a new suite version when behavior changes.
- Keep public fixtures and prompts under `benchmarks/suites/`.
- Keep private research notes out of Git; record their filename and SHA-256 in the run manifest.
- Record deterministic and semantic scores separately.
- Record prompt-processing and generation throughput separately.
- Record memory measurements and the exact workload shape.
- Preserve historical results; do not silently rewrite scores after a methodology change.

## Current suite

The current apples-to-apples comparison suite is defined in `suites/suite-v1.json`. It contains Finance, Apache, Access anomaly, Compression, Family note, Checklist, and Text lines.

The implementation currently lives in the repository scripts referenced by that manifest. Future changes should move canonical prompts and graders into versioned suite directories rather than relying only on runner source code.
