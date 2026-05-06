# Changelog

All notable changes to CODI are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). CODI uses [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-05-04 — Initial public release

### Added

**Core rules pipeline**
- `codi analyze` — Dockerfile parsing, stack detection, policy validation
- `codi rewrite` — deterministic candidate generation via `patterns/rules.yml` and Jinja2
- `codi run` — dry-run metrics harness (size, layers, build time estimates)
- `codi report` — Markdown and HTML reporter with diffs and rationale sections
- `codi all` — single command runs the full Analyze → Rewrite → Benchmark → Report pipeline
- `codi serve` — launches FastAPI REST service on configurable host/port
- `codi perf` — CPU-only performance sanity check with JSON output
- `codi dashboard` — aggregates run directories into a JSON dataset for the static viewer

**REST API** (`api/server.py`)
- `POST /analyze` — stack detection and feature extraction
- `POST /rewrite` — generate optimized Dockerfile candidates
- `POST /run` — execute pipeline and return metrics
- `POST /report` — generate Markdown/HTML report from a run
- `POST /llm/rank` — rank candidates with LLM assist (Complete image)
- `POST /llm/explain` — generate explanation for analysis (Complete image)

**Rules engine**
- `patterns/rules.yml` — deterministic templates for Node/Next.js, Python/FastAPI, Java/Spring Boot
- `cmd_rewrites` schema — shell-form → exec-form conversion with builder-stage promotions
- `RulesCatalog` helper — rule selection with predicate matching

**CMD/ENTRYPOINT analysis**
- `core/cmd_parser.py` — normalizes shell-form and exec-form instructions
- `core/script_analyzer.py` — static analysis of referenced shell scripts for runtime installs

**Security & environment**
- Air-gap guard (`core/security.py`) — blocks outbound HTTP(S) when `AIRGAP=true`
- `AIRGAP_ALLOWLIST` — opt-in selective outbound access
- `CodiEnvironment` config snapshot (`core/config.py`) — harmonizes CLI/API/container toggles
- Policy gates rejecting risky patterns (`ADD http://`, `--privileged`, `sudo`)

**Local LLM assist**
- `core/llm.py` — `LocalLLMServer` stub and `LLMAssist` with strict guardrails
- `LLMRankingService` — candidate ranking and explanation with Dockerfile-token validation
- SQLite-backed `RAGIndex` (`core/store.py`) — per-run similarity retrieval

**Containers**
- `docker/Dockerfile.slim` — multi-stage, non-root `codi` user, `AIRGAP=true`, API default CMD
- `docker/Dockerfile.complete` — extends Slim with offline LLM runtime, `/models` mount, dual health checks
- `docker/runtime_complete.py` — orchestrator that boots `LocalLLMServer` before FastAPI

**LLM training pipeline**
- `data/` — GitHub Dockerfile collector, quality labelling, standardization, synthetic pair generation
- Stratified train/val/test splits under `data/splits/`
- `training/qwen15b_lora/` — QLoRA config for Qwen2.5-Coder-1.5B, Colab notebook, adapter packaging
- `models/adapters/qwen15b-lora-v0.1` — adapter metadata for v0.1 LoRA weights

**Evaluation**
- `eval/` — LLM evaluation harness (`eval_suite.py`, `build_and_measure.py`)

**Release automation**
- `.github/workflows/release-images.yml` — builds and publishes `codi:slim` and `codi:complete` to GHCR on version tags
- cosign keyless image signatures and SPDX SBOM attestations
- `make release-images` / `make publish-images` Makefile targets

**Supported stacks**

| Stack | Builder | Runtime |
|---|---|---|
| Node.js / Next.js | `node:20-slim` | `node:20-alpine` |
| Python / FastAPI | `python:3.12-slim` | `python:3.12-slim` |
| Java / Spring Boot | `maven:3.9-eclipse-temurin-21` | `eclipse-temurin:21-jre` |

### Known limitations in v0.1.0

- Build runner operates in **dry-run mode** — metrics are heuristic estimates, not real Docker build results; BuildKit integration is planned for v0.2.0
- `codi:complete` LLM inference requires bind-mounting model weights at `/models`; the container does not bundle weights
- `test_training.py` and `test_data_pipeline.py` require optional GPU/R2 dependencies and are skipped in standard CI

---

*Older internal development history is preserved in `archive/pre-public-cleanup/` within the private repository.*
