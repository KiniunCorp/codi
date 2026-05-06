## Main features and value
- Rules-first optimization that analyzes, rewrites, benchmarks, and reports deterministic improvements for Node.js, Python, and Java Dockerfiles, with offline defaults and policy guardrails.
- Rich pipeline components: tolerant parser, stack detector, policy validation, templated renderer, build runner with metrics, structured run storage, regression-tested CLI/API, and a Markdown/HTML reporter with diffs and rationale.
- CMD optimization track adds analysis, schema-driven rewrite catalog, renderer integration, and surfaced CMD insights across CLI/API/reports with regression coverage.

## Slim vs. Complete containers
- **`codi:slim`**: rules-based CLI/API, no external models; built via multi-stage Dockerfile, non-root defaults, air-gapped, health checks, and Makefile helpers for build/run/test.
- **`codi:complete`**: extends Slim with bundled offline LLM + lightweight RAG, shared artefact volume, dual health checks (API + LLM), and runtime launcher wiring model endpoint before FastAPI starts.

## Model training and runtime enablement
- Training prep includes QLoRA configs, Colab notebooks, and adapter packaging for `qwen15b-lora-v0.1`, plus llama.cpp/Ollama stubs and adapter verification scripts for runtime use.
- Service-level LLM features expose `/llm/rank` and `/llm/explain` endpoints with CLI verbs and schema-validated responses, alongside reporting/evaluation artifacts (`llm_metrics.json`, HTML harness).
- Rule-promotion guardrails add compatibility labels, promotion metadata in `patterns/rules.yml`, and operator guides to keep model outputs policy-compliant.

## Data management (collect, extract, label, prepare)
- Data foundation pipeline collects Dockerfiles from GitHub, applies quality labeling and standardization, generates synthetic pairs from rules, and creates stratified train/val/test splits; automated via `make data-collect` and `make data-prepare`.
- Repository layout dedicates `data/raw`, `data/curated`, `data/pairs`, and `data/splits` folders for the respective stages, ensuring traceable preparation steps.

## Incremental tuning & evaluation
- Lightweight RAG index (SQLite) surfaces similar historical runs, enabling iterative tuning with contextual recall; LLM assist summaries feed recommendations while logging promotion metadata.
- CPU-only performance sanity suite (`codi perf`) records timings per stage, supporting feedback loops; security verification harness guards regressions in async guards and policy enforcement.
- Reporting/evaluation pipeline exports `llm_metrics.json` and HTML evaluations to quantify assist quality over time.

## Ways to use the tool
- **CLI**: Typer commands for analyze, rewrite, run, report, perf, dashboard, and all-in-one flows; honors env snapshots (e.g., `LLM_ENABLED`, `AIRGAP`, `CODI_OUTPUT_ROOT`).
- **API**: FastAPI service exposing `/analyze`, `/rewrite`, `/run`, `/report`, plus LLM endpoints; default CMD in containers starts the API server for immediate consumption.
- **Dashboard**: `codi dashboard` exporter and static viewer (`docs/dashboard/`) backed by curated sample runs for storytelling and KPI sharing.

## Reporting and artefacts
- Reporter produces Markdown and handcrafted HTML with diffs, rationale, environment configuration, CMD insights, metrics, and LLM assist summaries; outputs live under `runs/<timestamp>` for reproducibility.
- Dashboard-ready datasets and static site enable visual storytelling of optimization impact across sample stacks.
