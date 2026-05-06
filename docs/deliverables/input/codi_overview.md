# CODI Overview

## Purpose and Value
- CODI (Container Dietician) optimizes Dockerfiles for Node.js, Python, and Java projects by analyzing, rewriting, and benchmarking builds to deliver smaller and safer images without sacrificing determinism.
- The toolkit reduces build times and image sizes through rules-driven templates and measurable metrics, providing reproducible improvements with policy guardrails.
- Offline defaults and air-gap enforcement keep sensitive environments protected while still enabling AI-assisted guidance when desired.

## Deployment Options
- **Slim runtime (`codi:slim`)**: rules-based CLI and API with deterministic template rendering, suitable for locked-down environments and CI runners.
- **Complete runtime (`codi:complete`)**: ships everything in Slim plus an embedded offline LLM service and lightweight RAG memory to enhance explanations and ranking while keeping Dockerfile output template-driven.
- Both images use non-root defaults, health checks, and multi-stage builds; they expose CLI or FastAPI entrypoints for flexible automation.

## Core Capabilities
- **Analysis**: tolerant Dockerfile parser with stack detection, policy validation, and CMD/ENTRYPOINT insight to spot runtime anti-patterns.
- **Rewrite**: deterministic templates in `patterns/rules.yml` render optimized candidates, including exec-form CMD conversions and builder-stage promotions.
- **Run & Benchmark**: Dry-run metrics estimator records size, layer count, and timing heuristics; outputs structured metrics for comparison. Real BuildKit builds are planned for v0.2.
- **Reporting**: Markdown and handcrafted HTML reports summarize changes, diffs, rationale, environment configuration, and LLM assist notes.
- **Dashboard Export**: `codi dashboard` aggregates runs into JSON for the static viewer in `docs/dashboard/`, enabling sharing of optimization impact.
- **Security & Policy**: air-gap guard blocks outbound HTTP by default; security allowlists, environment snapshots, and validation checks keep runs reproducible.

## Usage Highlights
- **CLI**: `codi run <project>`, `codi report <run_dir>`, `codi all`, `codi dashboard`, and performance checks via `codi perf`.
- **API**: FastAPI service exposes `/analyze`, `/rewrite`, `/run`, `/report`, plus LLM endpoints when enabled.
- **Containers**: launch Slim or Complete images as API servers or run the CLI directly with bind mounts for project code and artefact storage.
- **Environment Controls**: variables such as `LLM_ENABLED`, `AIRGAP`, `MODEL_MOUNT_PATH`, `CODI_OUTPUT_ROOT`, and `RULES_PATH` tailor behavior without code changes.

## Outputs and Metrics
- **Reports**: Markdown and HTML files per run with diffs, rationale, CMD changes, environment metadata, and assist summaries.
- **Metrics**: size, layer count, and timing statistics recorded in run metadata; CPU sanity outputs quantify analysis, render, and total durations.
- **LLM Artefacts**: optional `llm_metrics.json` captures ranking confidence and adapter lineage when the Complete runtime is used.
- **Dashboard Data**: exportable JSON datasets power the static dashboard with stack aggregates and links to reports.

## Compatibility and Tooling
- Built with Python 3.12, Typer/Rich CLI, FastAPI API server, Jinja2 renderer, and SQLite-backed RAG index.
- Testing via pytest; formatting and linting enforced through Black and Ruff targets.
- Intended for reproducible use in offline or regulated environments while still offering explainability and guided optimizations.
