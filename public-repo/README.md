# 🧠 CODI (Container Dietician)

[![CI](https://github.com/KiniunCorp/codi/actions/workflows/ci.yml/badge.svg)](https://github.com/KiniunCorp/codi/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-MVP%20Active-success.svg)](#-roadmap)

**CODI** is a rules-first, AI-assisted container optimisation toolkit that **analyses**, **rewrites**, **benchmarks**, and **reports** deterministic improvements across Node, Python, and Java stacks. The MVP ships:

- End-to-end CLI/API pipelines with embedded offline LLM + RAG memory (`codi:complete`)
- Air-gapped security enforcement, environment-aware config snapshots, and CPU/security validation suites
- Curated example runs, a `codi dashboard` aggregator, and a static browser dashboard (`docs/dashboard/`) for showcasing optimisation impact
- Schema-validated CMD/ENTRYPOINT rewrite catalog (`cmd_rewrites`) with a `RulesCatalog` helper and regression coverage for deterministic rule selection
- Renderer-aware CMD rewrites with template promotions ensuring shell-form commands convert to exec-form with rationale comments
- Full report/API/CLI surfacing of CMD analysis, dedicated report sections, and per-run metadata for CMD rewrites

All flows honour offline defaults, policy guardrails, and reproducible artefact layouts.

## 🎯 Project Overview

The MVP roadmap delivers two runtimes:

- **`codi:slim`** — Rules-based CLI and API without external model dependencies
- **`codi:complete`** — Slim runtime bundled with an offline LLM and lightweight RAG memory

## 📁 Repository Structure

```
codi/
├── core/            # parse, detect, render, build, report, store, security
├── cli/             # Typer/Rich-based CLI interface
├── api/             # FastAPI REST service
├── patterns/        # rules.yml templates for supported stacks
├── models/          # Local LLM documentation and configs
├── docker/          # Dockerfiles for Slim and Complete containers
├── data/            # LLM training data pipeline
│   ├── raw/         # Collected Dockerfiles + metadata
│   ├── curated/     # Standardized, deduplicated data
│   ├── pairs/       # Training pairs (JSONL)
│   └── splits/      # Train/val/test splits
├── training/        # QLoRA training config, notebooks, and adapter packaging
├── eval/            # LLM evaluation harness and metrics
├── tune_module/     # Analyzer and Docker best-practice docs
├── demo/            # Sample applications for testing (Node.js, Python, Java)
├── tests/           # Test suite (unit + CLI + reporter)
├── docs/            # PRD, task plan, estimates, quickstart, runbook
├── Makefile         # Build automation and shortcuts
├── pyproject.toml   # Python project configuration
└── requirements.txt # Core dependencies
```

## ✅ Shipped Capabilities

**Core rules pipeline**
- Typer/Rich CLI with `analyze`, `rewrite`, `run`, `report`, `all`, `perf`, `dashboard`, and `serve` commands
- Tolerant Dockerfile parser + stack detector + policy validation
- Stack-specific renderer sourcing `patterns/rules.yml`
- Metrics harness capturing size, layer, and timing estimates (dry-run)
- `RunStore` for reproducible artefact layout under `runs/<timestamp>`
- Markdown and HTML reporter with diffs and rationale sections

**API service**
- FastAPI application in `api/server.py` exposing `/analyze`, `/rewrite`, `/run`, `/report`
- `codi serve` command launching uvicorn with configurable host/port
- OpenAPI metadata aligned with PRD schemas and response contracts

**Container packaging**
- Multi-stage `docker/Dockerfile.slim` (Python 3.12-slim, non-root `codi` user, `AIRGAP=true`)
- `docker/Dockerfile.complete` extending Slim with offline LLM runtime, shared `/work/runs` volumes, and dual health checks
- `docker/runtime_complete.py` orchestrator that boots `LocalLLMServer` before FastAPI

**Security and environment**
- `httpx` air-gap guard enforcing zero outbound calls by default; `AIRGAP_ALLOWLIST` for selective access
- Central `CodiEnvironment` config snapshot (`core/config.py`) with CLI/API/container toggle support
- Security gates rejecting risky Dockerfile patterns (privileged, `ADD http://`, sudo)

**LLM and RAG**
- SQLite-backed `RAGIndex` in `core/store.py` with cosine retrieval, persisted per run
- Guarded `LLMAssist` functions generating summaries and template recommendations without emitting raw Dockerfiles
- `/llm/rank` and `/llm/explain` API endpoints with schema-validated responses
- QLoRA training pipeline for Qwen2.5-Coder-1.5B (`training/qwen15b_lora/`)
- Adapter v0.1 metadata and packaging under `models/adapters/qwen15b-lora-v0.1`
- LLM evaluation harness under `eval/`

**CMD/ENTRYPOINT optimisation**
- `core/cmd_parser.py` and `core/script_analyzer.py` for deterministic CMD/ENTRYPOINT analysis
- Schema-driven `cmd_rewrites` catalog in `patterns/rules.yml` with `RulesCatalog` selector
- Renderer integration converting shell-form to exec-form with rationale comments
- Full CLI/API/report surfacing of CMD analysis and per-run metadata

**Dashboard**
- `codi dashboard` command aggregating runs to a JSON dataset
- Static browser dashboard in `docs/dashboard/` with run cards and stack aggregates

**Release automation**
- `.github/workflows/release-images.yml` publishing `codi:slim` and `codi:complete` to GHCR
- cosign keyless signatures + SPDX SBOM attestations
- `make release-images` / `make publish-images` Makefile targets

**Data pipeline** (for LLM training)
- GitHub Dockerfile collector, quality labelling, standardisation, and synthetic pair generation
- Stratified train/val/test splits under `data/splits/`

## 🧪 Technical Specifications

| Component | Technology | Status |
|-----------|------------|--------|
| Language | Python 3.12 | ✅ Production-ready |
| CLI Framework | Typer + Rich | ✅ Operational |
| Renderer | Jinja2 + policy guards | ✅ Operational |
| CMD Rewrite Catalog | YAML schema + RulesCatalog helper + renderer integration | ✅ Operational |
| Build Runner | Dry-run metrics estimator | ✅ Operational |
| Reporter | Markdown + handcrafted HTML | ✅ Operational |
| API Framework | FastAPI + Uvicorn | ✅ Operational |
| Container Packaging | Multi-stage Dockerfiles (Slim & Complete) | ✅ Production-ready |
| Complete Runtime Launcher | Python orchestrator (`docker/runtime_complete.py`) | ✅ Operational |
| Container Runtime | Dry-run heuristics (real BuildKit builds planned for v0.2) | ⏳ In progress |
| Code Quality | Ruff, Black, mypy | ✅ Enforced via Makefile |
| Local LLM Server | Threaded HTTP stub (`core/llm.py`) | ✅ Assist-ready |
| RAG Memory | SQLite-based `RAGIndex` with cosine retrieval | ✅ Operational |
| LLM Assist Functions | `LLMAssist` summary + template recommendation | ✅ Integrated |
| Dashboard Aggregator | `core/dashboard.py` + static viewer (`docs/dashboard/`) | ✅ Operational |
| Air-gap Guard | `httpx` outbound interceptor + env toggles | ✅ Enforced |
| Environment Configuration | `core/config.py` snapshots + environment metadata | ✅ Operational |
| Testing | pytest (49 tests incl. `tests/test_rules.py`) | ℹ️ Run `python3 -m pytest` |

> **Note:** Size and layer metrics are heuristic estimates produced by the dry-run build runner — no real Docker builds are executed in the current release. Reported reductions reflect template-level analysis. Real BuildKit integration is planned for v0.2.

## 🚀 Quick Start

> 📘 Prefer copy-paste commands? See [`docs/quickstart.md`](docs/quickstart.md).

### Prerequisites
- Python 3.12+ (for local development)
- Docker (for containerized deployment)
- Make

### Option 1: Local Development

```bash
git clone https://github.com/KiniunCorp/codi.git
cd codi
make setup                    # create .venv and install all dev dependencies
source .venv/bin/activate     # activate the virtual environment
make test                     # execute pytest suite
```

#### End-to-End Run + Report

```bash
# Execute deterministic optimisation against a project directory
codi run demo/node

# Generate human-readable report for the latest run folder
LATEST_RUN=$(ls -dt runs/* | head -n 1)
codi report "$LATEST_RUN"

# Reporter writes Markdown and HTML under runs/<id>/reports/
```

> ℹ️ `codi run` emits "LLM Assist" and "CMD Summary" panels detailing template recommendations and applied CMD rewrites alongside metrics.

#### Inspect CMD rewrite comments

```bash
# Run the optimiser on the Node demo and capture the latest run directory
codi run demo/node
LATEST_RUN=$(ls -dt runs/* | head -n 1)

# Inspect promoted builder steps and CMD rewrite rationale comments
grep -n "CMD rewrite" "$LATEST_RUN"/candidates/*.Dockerfile
grep -n "RUN pip wheel" "$LATEST_RUN"/candidates/*.Dockerfile
```

> Renderer outputs include CMD rewrite rationale comments and builder-stage promotions sourced from `cmd_rewrites`.

#### Run Smoke Validation

```bash
# Execute the automated smoke suite across Node/Python/Java demos
python3 -m pytest tests/test_smoke.py
```

#### CPU Sanity Check

```bash
python3 -m cli.main perf --out runs/perf --analysis-budget 5 --total-budget 180
cat runs/perf/cpu_perf_report.json | jq
```

> Detailed guidance lives in [`docs/performance_cpu_sanity.md`](docs/performance_cpu_sanity.md).

#### Dashboard Dataset & Viewer

```bash
# Aggregate runs into a dashboard-ready dataset
python3 -m cli.main dashboard \
  --runs docs/examples/dashboard \
  --export-json docs/dashboard/data/sample_runs.json \
  --relative-to docs/dashboard

# Serve the static dashboard (opens on http://127.0.0.1:8001)
python3 -m http.server --directory docs/dashboard 8001
```

> The dashboard fetches JSON generated by `codi dashboard` and renders run cards, stack aggregates, and links to Markdown/HTML reports. See [`docs/dashboard.md`](docs/dashboard.md) for full instructions.

#### Exercise the Local LLM stub

```bash
python3 - <<'PY'
from core.llm import LocalLLMClient, LocalLLMServer

with LocalLLMServer() as server:
    client = LocalLLMClient(server.base_url)
    print(client.complete("Summarise CODI smoke test benefits."))
PY
```

#### Environment toggles & defaults

```bash
# Persist runs somewhere else without passing --out to every CLI command
export CODI_OUTPUT_ROOT="$HOME/codi-runs"

# Allow-lists make it easy to invoke the FastAPI test client while keeping AIRGAP enabled
export AIRGAP_ALLOWLIST="testserver,internal.example.com"

# Disable assist calls (fallback summaries still render) or point to a remote endpoint
export LLM_ENABLED=false
# export LLM_ENDPOINT="http://127.0.0.1:8081"

# Override the default rules file if you want to experiment with custom templates
# export RULES_PATH=/path/to/custom/rules.yml

# Run the suite afterwards to verify everything remains green
python3 -m pytest
```

#### Launch FastAPI Service

```bash
# Serve the CODI API (defaults: host=127.0.0.1, port=8000)
codi serve --host 0.0.0.0 --port 8000

# Analyze a project via HTTP
curl -X POST "http://localhost:8000/analyze" \
  -H 'Content-Type: application/json' \
  -d '{"project_path": "demo/node"}' | jq

# Generate a full run over the same project
curl -X POST "http://localhost:8000/run" \
  -H 'Content-Type: application/json' \
  -d '{"project_path": "demo/node"}' | jq
```

### Option 2: Containerized Deployment

#### Build the Slim Container

```bash
# Build the multi-stage Slim container image
make build-slim

# Or directly with Docker
docker build -f docker/Dockerfile.slim -t codi:slim .
```

#### Build the Complete Container

```bash
# Build the Complete container image with embedded offline LLM runtime
make build-complete

# Or directly with Docker
docker build -f docker/Dockerfile.complete -t codi:complete .
```

#### Run as API Server (Default)

```bash
# Start the API server with volume mount
make run-slim

# Or directly with Docker
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim

# Access the API at http://localhost:8000
curl http://localhost:8000/
```

#### Run the Complete Container (API + LLM)

```bash
# Start the Complete image with API, embedded LLM, and mounted model weights
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$HOME/.codi-models:/models" \
  -e AIRGAP=true \
  -p 8000:8000 -p 8081:8081 \
  codi:complete

# Verify both services respond
curl http://localhost:8000/docs
curl http://localhost:8081/healthz
```
> ℹ️ `LLM_ENABLED`, `AIRGAP`, and `MODEL_MOUNT_PATH` default to secure offline values; mount your own weight directory at `/models` (or set `MODEL_MOUNT_PATH`) to inject larger models without rebuilding the image.
> 🔒 Need selective outbound access? Provide `AIRGAP_ALLOWLIST=internal.example.com` (comma-separated) or disable temporarily with `AIRGAP=false` for controlled testing.

### Tagged Releases & Verification

Automated GHCR publishing with provenance:

1. **Dry-run builds locally**
   ```bash
   # Loads release-tagged images into Docker without pushing
   make release-images RELEASE_VERSION=v1.4.0 IMAGE_NAMESPACE=my-org/codi
   ```
2. **Publish from a workstation** (requires `docker login ghcr.io`):
   ```bash
   make publish-images \
     RELEASE_VERSION=v1.4.0 \
     IMAGE_NAMESPACE=my-org/codi \
     REGISTRY=ghcr.io
   ```
3. **Tag + push (`git tag v1.4.0 && git push origin v1.4.0`)** to invoke `.github/workflows/release-images.yml`, which:
   - Builds `ghcr.io/<namespace>/codi-slim` and `ghcr.io/<namespace>/codi-complete`
   - Publishes `v1.4.0`, `latest`, and digest tags
   - Generates SPDX SBOMs and uploads them as workflow artifacts
   - Signs images + SBOM attestations with cosign keyless (OIDC)

4. **Verify signatures anywhere**
   ```bash
   OWNER=my-org
   REPO=codi
   IMAGE=ghcr.io/$OWNER/$REPO/codi-slim:v1.4.0

   cosign verify \
     --certificate-identity "https://github.com/${OWNER}/${REPO}/.github/workflows/release-images.yml@refs/tags/v1.4.0" \
     --certificate-oidc-issuer https://token.actions.githubusercontent.com \
     "$IMAGE"

   cosign verify-attestation \
     --type spdxjson \
     "$IMAGE"
   ```
   Substitute `OWNER/REPO` with your fork if publishing under a different org.

Refer to [`docs/runbook.md`](docs/runbook.md#9-release-publishing--rollback) for the end-to-end release checklist, approval gates, and rollback plan.


#### Run CLI Commands

```bash
# Override the default entrypoint to run CLI commands
docker run --rm -v "$PWD:/work" codi:slim \
  codi all /work/demo/node --dry-run

# Or get an interactive shell with all CLI verbs available
make run-slim-cli

# Inside the container you can verify the installation
codi --version
codi report --in /work/runs/<latest>
```

> 💡 Swap `codi:slim` for `codi:complete` to run the same CLI workflows with the embedded LLM assist enabled by default.

#### Example: Analyze a Project via Container

```bash
# Mount your project directory and analyze
docker run --rm -v "$PWD:/work" codi:slim \
  codi all /work/demo/node --dry-run

# Results are written to /work/runs/<timestamp>/
ls -la runs/
```

## 🗺️ Roadmap

### 🎯 Epic A — CODI Core (Rules-Only)
- [x] CODI-MVP-001 — Initialise repo skeleton & Makefile
- [x] CODI-MVP-002 — Bootstrap CLI (Typer/Rich) with stubs
- [x] CODI-MVP-003 — Implement tolerant Dockerfile parser
- [x] CODI-MVP-004 — Implement stack detector (node/python/java)
- [x] CODI-MVP-005 — Seed `patterns/rules.yml` for 3 stacks
- [x] CODI-MVP-006 — Implement renderer (Jinja2 + policy guards)
- [x] CODI-MVP-007 — Build runner (BuildKit) + metrics capture
- [x] CODI-MVP-008 — Reporter (Markdown + HTML, diffs & rationale)
- [x] CODI-MVP-009 — Store module for runs/ artefacts
- [x] CODI-MVP-010 — Security & policy gates
- [x] CODI-MVP-011 — FastAPI service with 4 endpoints
- [x] CODI-MVP-012 — Slim container packaging
- [x] CODI-MVP-013 — Create minimal sample apps (3 stacks)
- [x] CODI-MVP-014 — End-to-end Slim smoke on 3 stacks
- [x] CODI-MVP-015 — Quickstart docs for Slim

### 🤖 Epic B — Local LLM Enhancement
- [x] CODI-MVP-016 — Integrate local LLM server (Ollama/llama.cpp)
- [x] CODI-MVP-017 — RAG store (SQLite/Chroma) + retrieval helper
- [x] CODI-MVP-018 — LLM-assist functions with strict boundaries
- [x] CODI-MVP-019 — Complete container packaging
- [x] CODI-MVP-020 — Airgap + model mount toggles

### 🔄 Epic C — Unified Complete Container
- [x] CODI-MVP-021 — Env wiring & configuration
- [x] CODI-MVP-022 — CPU-only perf sanity tests
- [x] CODI-MVP-023 — Security & air-gap verification
- [x] CODI-MVP-024 — Models README & runbook
- [x] CODI-MVP-025 — Example runs + dashboard how-to

## 🎓 Supported Stacks

| Stack | Builder Base | Runtime Base | Status |
|-------|--------------|--------------|--------|
| Node.js / Next.js | `node:20-slim` | `node:20-alpine` | ✅ Supported |
| Python / FastAPI | `python:3.12-slim` | `python:3.12-slim` | ✅ Supported |
| Java / Spring Boot | `maven:3.9-eclipse-temurin-21` | `eclipse-temurin:21-jre` | ✅ Supported |

## 📚 Documentation

**Full documentation suite → [`docs/deliverables/docs/INDEX.md`](docs/deliverables/docs/INDEX.md)**

The index covers installation, CLI usage, API reference, architecture, LLM module, rules guide, operations, security, CI/CD release, performance, and testing — organised by role.

**Quick links**

| Guide | Description |
|---|---|
| [Installation & Setup](docs/deliverables/docs/INSTALLATION.md) | Clone, venv, platform notes |
| [CLI Guide](docs/deliverables/docs/CLI_GUIDE.md) | All commands, env flags, workflows |
| [API Guide](docs/deliverables/docs/API_GUIDE.md) | FastAPI endpoints, schemas, examples |
| [Architecture](docs/deliverables/docs/ARCHITECTURE.md) | System diagram, module deep-dive |
| [Slim Container](docs/deliverables/docs/SLIM_CONTAINER.md) | Build and run `codi:slim` |
| [Complete Container](docs/deliverables/docs/COMPLETE_CONTAINER.md) | Embedded LLM runtime, adapter mounts |
| [LLM Module](docs/deliverables/docs/LLM_MODULE.md) | Data pipeline, training, evaluation |
| [Rules Guide](docs/deliverables/docs/RULES_GUIDE.md) | Template authoring, CMD rewrites |
| [Operations Runbook](docs/deliverables/docs/OPERATIONS.md) | Day-2 health checks, troubleshooting |
| [Security](docs/deliverables/docs/SECURITY.md) | Air-gap controls, container hardening |
| [CI/CD & Release](docs/deliverables/docs/CICD_RELEASE.md) | Signing, SBOMs, rollback |
| [Performance](docs/deliverables/docs/PERFORMANCE.md) | Budgets, `codi perf`, tips |
| [Reference](docs/deliverables/docs/REFERENCE.md) | Commands, schemas, glossary, roadmap |

**Product spec**
- [PRD](docs/codi_mvp_prd.md) — Full MVP specification
- [Task plan](docs/codi_mvp_tasks.md) — Engineering breakdown

## 🔐 Security & Privacy

- Air-gapped by default — no external calls in the rules-only pipeline
- Template-based rendering guarded by security policies and allowlists
- Reporter embeds policy notes and rationale for every candidate
- Build runner operates in dry-run mode until BuildKit integration lands
- Air-gap guard blocks outbound HTTP(S) when `AIRGAP=true`; optionally set `AIRGAP_ALLOWLIST` for vetted internal hosts

## 🏆 Success Metrics (MVP Goals)

| Metric | Target | Status |
|--------|--------|--------|
| Median size reduction | ≥40% | Pending BuildKit integration |
| Syntactically valid candidates | 100% | ✅ Enforced via parser + policy checks |
| Report generation | Every run | ✅ Automated |
| Offline operation | 0 outbound calls | ✅ Enforced by air-gap guard |
| Analysis performance | ≤3s (no build) | ✅ CPU dry-run suite via `codi perf` |
| Full run performance | ≤5m per stack | ✅ Dry-run pipeline <0.01s; real builds forthcoming |

## 🤝 Contributing

Contributions are welcome! Development follows the task plan in `docs/codi_mvp_tasks.md`.

1. Pick a task from the roadmap or open an issue
2. Create a feature branch
3. Implement with tests (`python3 -m pytest`)
4. Run `make lint` + `make test`
5. Submit a PR referencing the task ID

## 📝 License

MIT License — see `LICENSE` for details.

## 🙋 Support & Resources

- **PRD:** `docs/codi_mvp_prd.md`
- **Tasks:** `docs/codi_mvp_tasks.md`
- **Issues:** Track progress and report bugs via repository issues

---

**Project Status:** ✅ MVP Active — rules pipeline, CMD optimisation, local LLM assist, and release automation shipped  
**Next Milestone:** Public launch, real BuildKit build integration, CHANGELOG  
**Last Updated:** 2026-05-04
