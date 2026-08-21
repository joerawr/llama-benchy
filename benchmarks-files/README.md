# Benchmark input files

This directory contains the exact task inputs sent to models. It is part of
the benchmark, not disposable setup data.

- `compression/` contains the research note used by the Compression task.
- `pinchbench/` contains the pinned PinchBench inputs used by Finance, Apache,
  and Access anomaly.

`MANIFEST.sha256` records the exact input hashes. The PinchBench task input was
copied from upstream commit `819384a`.

When adding a task or changing an input, update the suite documentation and
commit the input with the resulting scores. Never replace these files with a
fresh download without recording the new source version and hashes.
