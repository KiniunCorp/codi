# CODI Performance Guide

This guide explains how CODI measures performance, how to interpret results, and how to troubleshoot slow runs.

## 1. Performance Objectives

| Metric | Target |
| --- | --- |
| Analysis duration | ≤ 3 seconds per Dockerfile (rules-only) |
| Render duration | ≤ 2 seconds per candidate |
| Total dry-run pipeline | < 10 seconds for demo projects |
| Size reduction | ≥ 30% improvement for sample stacks |
| Layer reduction | ≥ 3 layers (sample stacks) |

Actual numbers depend on hardware and Dockerfile complexity.

## 2. CPU Sanity Suite (`codi perf`)

Run the suite to capture timings and verify that budgets are respected.

```bash
codi perf --out runs/perf \
  --analysis-budget 5 \
  --total-budget 180
```

Outputs:
- Console summary per stack (analysis, render, total time).
- JSON file `runs/perf/cpu_perf_report.json` with detailed results.

Example JSON excerpt:

```json
{
  "analysis": {"duration_ms": 215},
  "render": {"duration_ms": 310},
  "total": {"duration_ms": 610},
  "budget": {"analysis": 5000, "total": 180000}
}
```

## 3. Metrics Collection during `codi run`

`core/build.py` records estimated improvements in `metadata/metrics.json`:

```json
{
  "estimated_original_size_mb": 320,
  "estimated_candidate_size_mb": 205,
  "estimated_size_reduction_pct": 35.9,
  "estimated_layers": {"original": 18, "candidate": 12},
  "analysis_time_ms": 230,
  "render_time_ms": 320,
  "total_time_ms": 650
}
```

These figures appear in both CLI output and reports.

## 4. Smoke Suite

Run multi-stack smoke tests to ensure regressions are caught early:

```bash
python -m pytest tests/test_smoke.py
```

The suite verifies that rendered Dockerfiles achieve minimum percentage improvements and that reports are generated.

## 5. Optimisation Tips

| Scenario | Recommendations |
| --- | --- |
| Slow analysis on large repos | Use `--context dockerfile_path` to point directly to Dockerfile; exclude unnecessary files from project directory. |
| Disk I/O bottlenecks | Place `runs/` on SSD storage and avoid network filesystems. |
| Container cold starts | Pre-build images or keep container warm in CI. |
| CPU contention with llama.cpp | Reduce `LLAMA_CPP_THREADS` or run CLI commands outside Complete container when LLM not needed. |
| Dashboard export delays | Limit `--runs` scope to necessary directories before generating dataset. |

## 6. Monitoring Performance Over Time

- Keep historical `cpu_perf_report.json` files to track trends.
- Feed JSON data into internal dashboards for SLA tracking.
- Include performance metrics in release notes.

## 7. Troubleshooting

| Symptom | Actions |
| --- | --- |
| `codi perf` exceeds budget | Investigate stacks that violate thresholds; check recent template changes or new rules. |
| CLI run stalls | Enable debug logging (`CODI_LOG_LEVEL=DEBUG`) to see which module is blocking. |
| Reports show `N/A` metrics | Ensure `metrics.json` exists; rerun `codi run`. |
| LLM ranking slow | Confirm llama.cpp is running locally; adjust thread count or limit tokens in runtime script. |

## Related Documentation

- [OPERATIONS.md](./OPERATIONS.md) for incorporating performance checks into runbooks.
- [TESTING.md](./TESTING.md) for smoke suites that validate performance expectations.
- [LLM_MODULE.md](./LLM_MODULE.md) for tuning the embedded runtime when it affects timings.
