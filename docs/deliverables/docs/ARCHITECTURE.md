# CODI Architecture

CODI is organised as a modular Python system with optional container runtimes. This document describes the architecture, how data flows through the system, and how each module contributes to deterministic Dockerfile optimisation.

## High-Level System Diagram

```
Dockerfile + Context
        |
        v
+-------------------+
| Parser & Detector |
+-------------------+
        |
        v
+-------------------+
| Analyzer (smells) |
+-------------------+
        |
        v
+-------------------------+
| Renderer & Rules Engine |
+-------------------------+
        |
        +------------+
        |            |
        v            v
  +-----------+  +----------------+
  | Build Sim |  | Local LLM Assist|
  +-----------+  +----------------+
        |            |
        +------------+
               |
               v
      +------------------+
      | Reporter & Store |
      +------------------+
               |
               v
      Dashboards / API / CLI
```

The same pipeline powers both the CLI (`cli/main.py`) and the FastAPI service (`api/server.py`).

## Deployments

### Local Environment
- Developers install CODI via `make setup`.
- CLI writes artefacts under `runs/`.
- Optional RAG index stored in `runs/_rag/index.sqlite3`.

### Slim Container
- Built from `docker/Dockerfile.slim`.
- Runs non-root `codi` user.
- Ships CLI + API without LLM runtime.
- Default entrypoint launches FastAPI server on port 8000.

### Complete Container
- Extends Slim image via `docker/Dockerfile.complete`.
- Adds llama.cpp build, adapter validation scripts, and runtime orchestrator (`docker/runtime_complete.py`).
- Exposes both FastAPI (8000) and LLM server (8081).
- Mounts `/models` for adapters and base weights.

## Core Modules

### Parser (`core/parse.py`)
- Implements a tolerant Dockerfile parser that preserves comments and whitespace where possible.
- Normalises instructions, tracks ARG/ENV scope, and produces a `DockerfileDocument` object.
- Emits structured errors (`DockerfileParseError`) consumed by CLI/API for user-friendly messaging.

### Stack Detector (`core/detect.py`)
- Analyses parsed instructions and file context to classify stacks (Node, Python, Java).
- Outputs `DetectionResult` with confidence, heuristics, and suggested rules catalog entries.
- Also detects multi-stage topology and builder/runtime stage names.

### Analyzer (`core/analyzer.py`)
- Aggregates parser + detector output and inspects Dockerfiles for quality issues.
- Labels smells such as `latest_tag`, `shell_form_cmd`, `apt_no_clean`, `root_user`, etc.
- Invokes CMD parser/script analyzer to expand runtime entrypoints.
- Generates analysis payload stored under `metadata/run.json`.

### CMD Parser & Script Analyzer (`core/cmd_parser.py`, `core/script_analyzer.py`)
- Parses CMD/ENTRYPOINT instructions, supports both shell-form and exec-form.
- Resolves scripts referenced via `COPY`/`ADD` when accessible.
- Flags risky behaviours (runtime package installs, shell shims, signal handling issues).
- Provides structured context for CMD rewrites.

### Rules Engine (`core/rules.py`)
- Loads `patterns/rules.yml`, validates the schema, and exposes a `RulesCatalog` class.
- Each rule defines metadata, supported stacks, security requirements, templates, and CMD rewrites.
- Catalog resolves compatibility flags and emits template references used by the renderer.

### Renderer (`core/render.py`)
- Builds a `RenderContext` with stack-specific settings, detected smells, CMD analysis, and rule metadata.
- Renders deterministic Dockerfile candidates using Jinja2 templates.
- Injects rationale comments and builder/runtime stage promotions.
- Integrates CMD rewrite catalog to convert shell-form commands to exec-form and promote runtime installs into builder stages.

### Build Runner (`core/build.py`)
- Currently operates in dry-run mode to estimate improvements before Docker builds are executed.
- Calculates projected image size reduction, layer counts, and time savings using heuristics that consider base images, package managers, and multi-stage strategies.
- Executes sanity checks (air-gap enforcement, path validation) before handing off to actual builds when enabled.
- Outputs `metrics.json` stored under `runs/<id>/metadata/`.

### Reporter (`core/report.py`)
- Generates Markdown (`report.md`) and handcrafted HTML (`report.html`).
- Sections include: Overview, Key Metrics, Candidate Summaries, CMD Rewrites, Security Notes, Environment Snapshot, LLM Assist Summaries, and Diffs.
- Embeds links to inputs/candidates to aid manual review.

### Security Module (`core/security.py`)
- Centralises policy enforcement such as outbound HTTP blocking.
- `enforce_airgap_guard` hooks into CLI/API flows; environment variables toggle behaviour (`AIRGAP`, `AIRGAP_ALLOWLIST`).
- Provides helper utilities for validating model mount paths and reporting security policy violations.

### Configuration (`core/config.py`)
- Defines `CodiEnvironment` snapshot describing runtime configuration.
- Tracks toggles like `LLM_ENABLED`, `AIRGAP`, `RULES_PATH`, `CODI_OUTPUT_ROOT`.
- Reporter embeds environment snapshot in generated artefacts.

### Store & RAG Index (`core/store.py`)
- Manages run directory creation, naming, and metadata writes.
- Maintains a lightweight SQLite-based RAG index containing embeddings of past runs.
- Enables similarity search used by LLM assist and dashboards.

### Dashboard Aggregator (`core/dashboard.py`)
- Consumes run directories and produces JSON suitable for the static dashboard viewer.
- Calculates per-stack improvements, environment flags, and links to reports.

### Performance Harness (`core/perf.py`)
- Instruments analysis/render durations via `codi perf`.
- Stores CPU performance reports with budgets (`analysis_budget`, `total_budget`).
- Provides CLI output for trend analysis and JSON for automation.

### Local LLM Module (`core/llm.py`)
- Defines `LocalLLMServer`, `LocalLLMClient`, and `LLMRankingService`.
- In Complete deployments, this module communicates with the embedded llama.cpp process.
- Provides deterministic stub mode for Slim builds or when adapters are unavailable.
- Exposes health checks, ranking, explanation, and telemetry recording (`llm_metrics.json`).

## Data Flow Details

1. **Input ingestion** – CLI/API accepts a path to a project directory; Dockerfile is read and parsed.
2. **Detection and analysis** – Stack detection + smell labeling; CMD analyzer extracts scripts and risk signals.
3. **Rendering** – Rules catalog chooses appropriate templates; renderer produces 1–2 candidates with metadata.
4. **Metrics estimation** – Build runner estimates size/layer reductions and writes `metrics.json`.
5. **LLM assist (Complete only)** – Candidates + metrics + analysis context are sent to `LLMRankingService`; ranking + rationale appended to metadata.
6. **Reporting** – Reporter compiles Markdown and HTML with diffs, metrics, CMD rewrites, and LLM insights.
7. **Storage** – `core/store.py` persists inputs, candidates, logs, metadata, reports, and updates RAG index.
8. **Dashboards** – `codi dashboard` exports aggregated JSON referencing stored run artefacts.

## Slim vs Complete Architecture

| Aspect | Slim | Complete |
| --- | --- | --- |
| Base image | `python:3.12-slim` multi-stage | Slim image + llama.cpp build stage |
| LLM runtime | Disabled by default (`LLM_ENABLED=false`) | Enabled with embedded server on port 8081 |
| Environment defaults | `AIRGAP=true`, `CODI_RULESET_VERSION` label set | Same plus adapter metadata logging |
| Additional scripts | N/A | `docker/runtime_complete.py`, `docker/scripts/mount_adapter.sh`, `docker/scripts/verify_adapter.py` |
| Ports | 8000 | 8000 (API) + 8081 (LLM) |
| Volume mounts | `/work` | `/work` + `/models` (weights/adapters) |

## Interfaces

### CLI (`cli/main.py`)
- Built with Typer + Rich.
- Commands: `analyze`, `rewrite`, `run`, `report`, `all`, `serve`, `dashboard`, `perf`, `llm rank`, `llm explain`.
- Shares implementation with API via helper functions that call into `core` modules.

### API (`api/server.py`)
- FastAPI application wiring CLI-equivalent flows into HTTP endpoints.
- Dependency-injected `AppConfig` holds `CodiEnvironment` snapshot and candidate limits.
- Endpoints mirror CLI verbs; responses include structured metadata and environment details.

## Artefact Layout

```
runs/<timestamp>-<stack>-<label>/
├── inputs/
│   └── Dockerfile
├── candidates/
│   ├── candidate_1.Dockerfile
│   └── candidate_2.Dockerfile
├── logs/
│   └── build.log (future BuildKit integration)
├── metadata/
│   ├── run.json
│   ├── metrics.json
│   ├── llm_metrics.json (Complete)
│   ├── rag.json
│   └── environment.json
└── reports/
    ├── report.md
    └── report.html
```

A shared `_rag/index.sqlite3` database stores embeddings referenced by `metadata/rag.json`.

## Extensibility Points

- **Rules catalog** – Add new stacks or refine templates by editing `patterns/rules.yml` and supplying corresponding Jinja2 templates.
- **CMD rewrites** – Extend the CMD catalog to support additional runtime promotion patterns.
- **LLM adapters** – Train adapters via the documented pipeline and mount them under `/models/adapters/<id>/`.
- **Dashboards** – Custom datasets can be produced by pointing `codi dashboard` at arbitrary `runs/` roots.
- **API** – Additional endpoints can reuse core modules thanks to the consistent `RenderContext` and `BuildRunner` interfaces.

## Observability Hooks

- CLI outputs Rich panels with metrics and summaries.
- `codi perf` writes JSON timing reports.
- Complete container logs adapter metadata, LLM status, and health checks to stdout.
- FastAPI includes `/healthz` and `/metrics` (via future extensions) for infrastructure monitoring.

## Security Considerations

- Air-gap guard intercepts outbound HTTP requests via `httpx` patching.
- Only allowlisted hosts may be contacted when `AIRGAP_ALLOWLIST` is set.
- Containers run as non-root `codi` user with locked-down defaults.
- Templates enforce policy notes and require explicit allowlist entries for certain instructions.

## Roadmap Hooks

The architecture intentionally separates deterministic rules from ML-driven insights so that future enhancements (additional stacks, BuildKit integration, policy packs, remote adapters) can be implemented without changing the fundamental pipeline. Refer to `REFERENCE.md` for formal schemas and to `LLM_MODULE.md` for model lifecycle details.

## Related Documentation

- [TECH_STACK.md](./TECH_STACK.md) for detailed dependency information.
- [CLI_GUIDE.md](./CLI_GUIDE.md) and [API_GUIDE.md](./API_GUIDE.md) for interface specifics.
- [LLM_MODULE.md](./LLM_MODULE.md) for in-depth coverage of the embedded model lifecycle.
- [RULES_GUIDE.md](./RULES_GUIDE.md) to understand how templates and CMD rewrites are structured.
