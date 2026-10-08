# Benchmark Definitions

Benchmark definitions are versioned inputs. A result must identify the suite version, task files, grader version, model, hardware profile, and run date.

## Rules

- Do not change a prompt, fixture, rubric, or semantic-judge instruction in place.
- Create a new suite version when behavior changes.
- Keep public fixtures and prompts under `benchmarks/suites/`.
- Keep private research notes out of Git; record their filename and SHA-256 in the run manifest.
- Record semantic score as the only public quality score. Preserve deterministic rubric checks only as internal diagnostic evidence for the judge.
- Record prompt-processing and generation throughput separately.
- Record memory measurements and the exact workload shape.
- Preserve historical results; do not silently rewrite scores after a methodology change.

## Current suite

The current apples-to-apples comparison suite is defined in `suites/suite-v1.json`. It contains Finance, Apache, Access anomaly, Compression, Family note, Checklist, and Text lines.

The implementation currently lives in the repository scripts referenced by that manifest. Future changes should move canonical prompts and graders into versioned suite directories rather than relying only on runner source code.

## Checklist prompt versions

Suite 1.1 remains the default and keeps its original checklist prompt.
Suite 1.2 (`benchmarks/suites/suite-v1.2.json`) adds the explicit `- ` Markdown
bullet requirement and is selected with `scripts/ifeval_lite.py --suite-version 1.2`.
Do not combine 1.1 and 1.2 passes or substitute a 1.2 retry into a 1.1 total.
Source-aware-v2 changes the judge protocol separately from the task version;
retain the original score and the saved prompt hash when recording a rescore.
Local incomplete outputs have a null quality score and display `-`.
Historical files without matching task hashes remain unverified observations.
