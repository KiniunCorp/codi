# CODI Overview

CODI (Container Dietician) is an offline-first optimisation system that analyses Dockerfiles, rewrites them using deterministic templates, benchmarks the results, and produces auditable reports. It focuses on three production stacks—Node.js/Next.js, Python/FastAPI, and Java/Spring Boot—and provides identical functionality through both a Typer-based CLI and a FastAPI service. Two container footprints are available:

- **Slim container** – ships the rules-first engine for air-gapped or CI usage.
- **Complete container** – layers an embedded llama.cpp runtime and a fine-tuned adapter on top of the Slim image to provide local LLM ranking and rationale services without leaving the host network.

The platform keeps optimisation decisions deterministic while still surfacing ML-driven insights. Every run emits reproducible artefacts under `runs/<timestamp>-<stack>-<label>/`, making it straightforward to audit recommendations, diff Dockerfiles, or feed data into dashboards.

## Key Capabilities

| Capability | Description |
| --- | --- |
| Stack-aware analysis | Tolerant parser, stack detector, CMD/ENTRYPOINT inspection, security smell detection, and RAG-backed history lookup. |
| Deterministic rendering | Rules catalog in `patterns/rules.yml` backed by Jinja2 templates, security allowlists, and runtime-aware rewrites. |
| Build simulation | Dry-run metrics estimator that reports size, layers, and timing projections before invoking Docker BuildKit. |
| Reporting | Markdown + handcrafted HTML reports summarising findings, metrics, diffs, CMD rewrites, and LLM insights. |
| CLI & API parity | `codi` CLI mirrors the FastAPI service (`/analyze`, `/rewrite`, `/run`, `/report`, `/llm/*`). |
| Dashboard tooling | `codi dashboard` aggregates multiple runs into JSON datasets consumed by a static viewer in `docs/dashboard/`. |
| Performance instrumentation | `codi perf` captures analysis/render timings and stores structured JSON for trend tracking. |
| Security posture | Enforced air-gap mode, outbound HTTP allowlists, template allowlists, non-root containers, and full artefact provenance. |
| Local LLM assist | Complete container embeds llama.cpp with a Qwen2.5-Coder-1.5B adapter that ranks candidates and generates rationales offline. |

## Supported Usage Models

1. **Workstation CLI** – Developers run `codi run` directly against repositories, inspect generated reports, and iterate on local Dockerfiles.
2. **FastAPI service** – Teams integrate the API (`/run`, `/report`) into internal tooling or IDE extensions.
3. **Slim container in CI/CD** – Pipelines run the containerised CLI in deterministic, network-restricted environments.
4. **Complete container with embedded LLM** – Offline data centres mount adapters under `/models` and use the bundled llama.cpp server.
5. **Reporting and dashboards** – Analysts share `report.html` artefacts or publish curated dashboards powered by `codi dashboard` datasets.

## Why CODI

- **Rules-first by design** – Templates capture vetted best practices, guaranteeing reproducible Dockerfiles with traceable rationale comments.
- **Security-conscious** – Air-gap guardrails, non-root containers, and policy checks prevent accidental network exposure or unsafe rewrites.
- **Offline LLM integration** – The embedded adapter delivers ranking and explanatory power without ever emitting raw Dockerfile content.
- **Auditable artefacts** – Every run stores inputs, candidates, logs, metrics, RAG outputs, and reports in a standardised structure.
- **Extensible** – New rules, stacks, or adapters can be added without rewriting the orchestration pipeline.

## Use Cases

| Persona | Scenario |
| --- | --- |
| Platform engineer | Integrate CODI into internal portals so teams can upload Dockerfiles and receive optimised variants and reports. |
| Security team | Enforce container hardening policies by reviewing the policy notes and CMD rewrite rationale emitted per run. |
| DevEx team | Provide curated dashboards that highlight aggregate savings across services. |
| ML engineer | Train or evaluate new adapters using the documented data pipeline, evaluation harness, and runtime hooks. |
| SRE | Run the Complete container in isolated environments to obtain human-readable rationales without connecting to external LLMs. |

## Release Status

The current release (v0.1.0) contains the complete CLI, API, Slim image, Complete image, performance harness, dashboard tooling, and local LLM runtime. Features that depend on Docker BuildKit execution remain in dry-run mode by default, but the CLI exposes the necessary hooks for future build integration. Container images can be built locally via `make build-slim` / `make build-complete` or published through the automated release workflow described in `CICD_RELEASE.md`.

## Documentation Map

| If you want to… | Read |
| --- | --- |
| Understand the system architecture | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Review the complete tech stack | [TECH_STACK.md](./TECH_STACK.md) |
| Install or configure the CLI | `INSTALLATION.md` (Phase 2 deliverable) |
| Work with containers | `SLIM_CONTAINER.md`, `COMPLETE_CONTAINER.md` |
| Dive into the LLM module | `LLM_MODULE.md` |
| Operate CODI day-to-day | `OPERATIONS.md`, `SECURITY.md` |
| Explore reporting assets | `REPORTING.md`, dashboard how-to |
| Extend CODI | `RULES_GUIDE.md`, `CONTRIBUTING.md`, `REFERENCE.md` |

Each document within `docs/deliverables/docs/` is designed to stand on its own while cross-linking to neighbouring topics, enabling readers to jump directly to the depth they need.

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) for system-level design details.
- [TECH_STACK.md](./TECH_STACK.md) for dependency and tooling specifics.
- [INSTALLATION.md](./INSTALLATION.md) for environment setup steps.
- [CLI_GUIDE.md](./CLI_GUIDE.md) for detailed command usage.
