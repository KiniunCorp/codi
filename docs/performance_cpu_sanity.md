# CPU Performance Sanity Results

This document records end-to-end CODI pipeline performance on CPU-only hardware against the three demo stacks. The acceptance criteria require:

- Analysis phase ≤ **5 seconds** per project.
- Full run (analysis → render → assist) ≤ **180 seconds** (3 minutes) per project.

## Summary

- **Execution time:** 2025-10-31T14:47:05Z (UTC)
- **Command:**

```bash
python3 -m cli.main --out runs/perf-baseline perf --analysis-budget 5 --total-budget 180
```

- **Artefacts:** `runs/perf-baseline/perf/`
- **Report JSON:** `runs/perf-baseline/perf/cpu_perf_report.json`

## Detailed Metrics

| Stack  | Analysis (s) | Render (s) | Total (s) | Original Build (s) | Status |
| ------ | ------------:| ----------:| ---------:| ------------------:| :------ |
| node   | 0.0002 | 0.0032 | 0.0083 | 29.10 | ✅ Passed |
| python | 0.0002 | 0.0026 | 0.0041 | 33.10 | ✅ Passed |
| java   | 0.0002 | 0.0024 | 0.0039 | 28.25 | ✅ Passed |

All stacks completed comfortably within the CPU-only thresholds, with total pipeline times remaining under 10 milliseconds in the dry-run configuration. Complete run artefacts (candidate Dockerfiles, metrics, reports, and environment snapshots) are available under the corresponding run directories in `runs/perf-baseline/perf/`.

To reproduce the results on another machine:

1. Ensure dependencies are installed via `python3 -m pip install -r requirements.txt`.
2. Execute the CLI command above (adjust `--out` if a different artefact directory is preferred).
3. Review the generated JSON report or rendered CLI table for status and timing details.
