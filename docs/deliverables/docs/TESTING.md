# CODI Testing Guide

CODI ships with a comprehensive pytest suite covering parsing, rendering, CLI/API flows, LLM integration, and data pipelines. This guide details available tests and how to run them.

## 1. Test Environment

- Requires Python 3.12 with dev dependencies (`make setup`).
- Optional: Docker for integration tests that interact with containers.
- Set `AIRGAP_ALLOWLIST="testserver"` when running FastAPI tests to avoid air-gap violations.

## 2. Running Tests

```bash
make test          # python -m pytest
python -m pytest   # direct invocation
python -m pytest -k render
python -m pytest --cov=core --cov-report=html
```

Use `-m "not slow"` once slow tests exist; currently all tests run quickly.

## 3. Test Categories

| Module | Location | Focus |
| --- | --- | --- |
| Parser & detector | `tests/test_parse.py`, `tests/test_detect.py` | Dockerfile parsing, stack detection heuristics. |
| Analyzer | `tests/test_analyzer.py` (if present) / `tests/test_rules.py` | Smell detection, rule selection. |
| Renderer | `tests/test_render.py` | Template rendering, CMD rewrites, rationale comments. |
| Build runner | `tests/test_build.py` | Metrics estimation, policy enforcement. |
| Store & RAG | `tests/test_store.py` | Run directory handling, SQLite index updates. |
| Security | `tests/test_security.py` | Air-gap guard, adapter path validation. |
| CLI/API | `tests/test_cli.py`, `tests/test_api.py` | Command behaviours, FastAPI endpoints. |
| Dashboard | `tests/test_dashboard.py` | Dataset aggregation, JSON schema validation. |
| Performance | `tests/test_perf.py` | CPU perf harness. |
| LLM | `tests/test_llm.py`, `tests/test_llm_ranking.py` | Local server stub, ranking logic, telemetry. |
| Data pipeline | `tests/test_data_pipeline.py` | Collection/labeling/standardisation scripts. |
| Eval suite | `tests/test_eval_suite.py` | Evaluation harness sanity checks. |
| Training | `tests/test_training.py` | Ensures training script arguments and configs stay consistent. |
| Smoke | `tests/test_smoke.py` | End-to-end validations across demo stacks. |

## 4. Adding Tests

1. Place new tests under `tests/` with descriptive filenames.
2. Import modules using absolute paths (project root already in `PYTHONPATH`).
3. Use fixtures for run directories to keep tests isolated.
4. For CLI tests, use Typer’s `CliRunner` to capture output.
5. For API tests, use FastAPI `TestClient` and configure allowlists as needed.

## 5. Test Data

- Demo projects in `demo/node`, `demo/python`, `demo/java` act as fixtures for rendering tests.
- Sample runs under `docs/examples/dashboard/` serve as references for dashboard tests.
- Data pipeline tests use fixtures within `data/` to avoid hitting external APIs.

## 6. Continuous Integration

- Recommended to run `make test` on every pull request.
- Container images can run tests as part of release pipeline if desired (`docker run codi:slim python -m pytest`).

## 7. Debugging Failures

| Failure Type | Tips |
| --- | --- |
| Parser errors | Print problematic Dockerfile snippet; ensure parser handles instruction permutations. |
| Renderer assertions | Regenerate expected outputs by running CLI and comparing to tests; ensure templates remained deterministic. |
| CLI/API snapshot mismatches | Update fixtures if output schema changed intentionally. |
| LLM tests failing | Check adapter environment variables; use stub mode by setting `LLM_ENABLED=false`. |

## 8. Coverage Expectations

- Aim for high coverage on `core/` modules (parser, analyzer, render, build, report, security).
- Keep CLI/API tests up-to-date when adding commands or endpoints.
- When introducing new stacks or rules, add dedicated tests before merging.

## Related Documentation

- [PERFORMANCE.md](./PERFORMANCE.md) for interpreting timing data captured during tests.
- [CONTRIBUTING.md](./CONTRIBUTING.md) for development workflow expectations tied to testing.
- [ARCHITECTURE.md](./ARCHITECTURE.md) for context when adding coverage to new modules.
