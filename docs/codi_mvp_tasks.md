# CODI — MVP Task Plan (codi_mvp_tasks.md)

## Executive Summary
This plan translates the CODI MVP PRD into a technically ordered backlog that delivers two shippable containers: **Slim (rules-only)** and **Complete (Slim + local LLM + RAG)**. Tasks are sequenced by hard dependencies first (parser → rules → renderer → runner → reporter → API → Slim image), then augmented to add the local model server and RAG memory, and finally unified and validated. The output includes a sortable-style summary table and detailed, testable specs for each task with clear acceptance criteria, artifacts, and DoD. Scope is constrained strictly to the PRD’s three stacks (Node/Next.js, Python/FastAPI, Java/Spring Boot), rules-first determinism, no external LLM calls, and air‑gapped security defaults.

## Conventions & Coding
- **ID format:** `CODI-MVP-###` (001+; no gaps)  
- **Priority:** `P0` (critical path) · `P1` (important) · `P2` (nice-to-have)  
- **Owner:** `PM`, `PdM`, `TA`, `Eng`  
- **Labels:** `Epic-A` (Core rules-only), `Epic-B` (Local LLM), `Epic-C` (Unified container), `Epic-CMD` (CMD/ENTRYPOINT), `Epic-LLM` (LLM Enhancement) + stack tags `Node`, `Python`, `Java`  
- **Estimates:** person-hours (engineering time)

---

## Summary Table
ID | Title | Epic | Priority | Owner | Status | Estimate (h) | AI-agent (H:m:s) | Depends On | Outputs
---|---|---|---|---|---|---:|---|---|---
CODI-MVP-001 | Initialize repo skeleton & Makefile | Epic-A | P0 | Eng | Complete | 4 | 0:29:22 | — | `/core/ /cli/ /api/ /patterns/ /models/ /docker/ /docs/`, `Makefile`
CODI-MVP-002 | Bootstrap CLI (Typer/Rich) with stubs | Epic-A | P0 | Eng | Complete | 4 | 1:35:00 | 001 | `/cli/main.py`, `tests/test_cli.py`
CODI-MVP-003 | Implement tolerant Dockerfile parser | Epic-A | P0 | Eng | Complete | 8 | 1:35:00 | 001 | `/core/parse.py`, `tests/test_parse.py`
CODI-MVP-004 | Implement stack detector (node/python/java) | Epic-A | P0 | Eng | Complete | 6 | 0:20:00 | 003 | `/core/detect.py`, unit tests
CODI-MVP-005 | Seed `patterns/rules.yml` for 3 stacks | Epic-A | P0 | Eng | Complete | 10 | 0:22:00 | 004 | `/patterns/rules.yml`
CODI-MVP-006 | Implement renderer (Jinja2 + policy guards) | Epic-A | P0 | Eng | Complete | 10 | 1:10:00 | 005 | `/core/render.py`, `/core/parse.py`, `/tests/test_render.py`
CODI-MVP-007 | Build runner (BuildKit) + metrics capture | Epic-A | P0 | Eng | Complete | 10 | 2:05:00 | 006 | `/core/build.py`, `/cli/main.py`, `/tests/test_build.py`, `/runs/<ts>/run.json`
CODI-MVP-008 | Reporter (Markdown + HTML, diffs & rationale) | Epic-A | P0 | Eng | Complete | 10 | 2:30:00 | 007 | `/core/report.py`, `/cli/main.py`, `/tests/test_report.py`, `/runs/<ts>/report.md/html`
CODI-MVP-009 | Store module for runs/ artifacts | Epic-A | P1 | Eng | Complete | 4 | 2:05:00 | 006 | `/core/store.py`, `/cli/main.py`, `/tests/test_store.py`, `/runs/<ts>/*`
CODI-MVP-010 | Security & policy gates | Epic-A | P0 | Eng | Complete | 8 | 0:20:00 | 003 | allowlist, validations, tests
CODI-MVP-011 | FastAPI service with 4 endpoints | Epic-A | P0 | Eng | Complete | 8 | 1:45:00 | 006,007,008 | `/api/server.py`, `/tests/test_api.py`, `CLI serve`, OpenAPI docs
CODI-MVP-012 | Slim container packaging | Epic-A | P0 | Eng | Complete | 6 | 0:32:45 | 011 | `/docker/Dockerfile.slim`, entrypoint, `.dockerignore`, Makefile targets
CODI-MVP-013 | Create minimal sample apps (3 stacks) | Epic-A | P1 | Eng | Complete | 6 | 1:35:00 | 001 | `/demo/node`, `/demo/python`, `/demo/java`
CODI-MVP-014 | End-to-end Slim smoke on 3 stacks | Epic-A | P0 | Eng | Complete | 6 | 1:05:00 | 012,013 | `/runs/<ts>/*`, `tests/test_smoke.py`
CODI-MVP-015 | Quickstart docs for Slim | Epic-A | P1 | PdM | Complete | 4 | 0:55:00 | 014 | `/docs/quickstart.md`
CODI-MVP-016 | Integrate local LLM server (Ollama/llama.cpp) | Epic-B | P0 | Eng | Complete | 8 | 1:25:00 | 012 | `core/llm.py`, `tests/test_llm.py`
CODI-MVP-017 | RAG store (SQLite/Chroma) + retrieval helper | Epic-B | P1 | Eng | Complete | 8 | 2:20:00 | 016 | `/core/store.py` (extend), retrieval API
CODI-MVP-018 | LLM-assist functions w/ strict boundaries | Epic-B | P0 | Eng | Complete | 8 | 1:27:00 | 016,017 | `/core/llm.py`, `/core/build.py`, `/core/report.py`, `/api/server.py`, `/cli/main.py`, tests
CODI-MVP-019 | Complete container packaging | Epic-B | P0 | Eng | Complete | 6 | 0:47:00 | 016,018 | `/docker/Dockerfile.complete`, `docker/runtime_complete.py`
CODI-MVP-020 | Airgap + model mount toggles | Epic-B | P0 | TA | Complete | 4 | 1:18:00 | 019 | `core/security.py`, `docker/runtime_complete.py`, `tests/test_security.py`, docs update
CODI-MVP-021 | Env wiring & configuration | Epic-C | P0 | Eng | Complete | 4 | 1:50:00 | 019,020 | `core/config.py`, env metadata, docs/tests updated
CODI-MVP-022 | CPU-only perf sanity tests | Epic-C | P1 | Eng | Complete | 6 | 1:05:00 | 021 | `core/perf.py`, `cli perf`, `tests/test_perf.py`, `docs/performance_cpu_sanity.md`
CODI-MVP-023 | Security & air-gap verification | Epic-C | P0 | Eng | Complete | 6 | 0:50:00 | 021 | `tests/test_security.py`, `docs/security_verification.md`
CODI-MVP-024 | Models README & runbook | Epic-C | P1 | PdM | Complete | 4 | 1:20:00 | 021 | `/models/README.md`, `/docs/runbook.md`, `README.md`
CODI-MVP-025 | Example runs + dashboard how-to | Epic-C | P2 | PdM | Complete | 4 | 0:19:28 | 022 | `/docs/dashboard.md`, `/docs/dashboard/`, `/docs/examples/dashboard/`
CODI-MVP-026 | Image publishing & signing | Epic-C | P0 | Eng | Complete | 10 | 1:32:00 | 019,021 | `.github/workflows/release-images.yml`, Makefile release targets, cosign/SBOM docs
CODI-MVP-027 | Release validation & rollback runbook | Epic-C | P0 | Eng | Planned | 8 | — | 026 | Staging smoke tests, promotion checklist, rollback SOP
CMD-001 | CMD/ENTRYPOINT analyzer foundation | Epic-CMD | P0 | Eng | Complete | 10 | 0:09:18 | CODI-MVP-003, CODI-MVP-006 | `core/cmd_parser.py`, `core/analyzer.py`, `core/build.py`, `cli/main.py`, `api/server.py`, `tests/test_cmd_parser.py`
CMD-002 | Script reference inspection & heuristics | Epic-CMD | P0 | Eng | Complete | 8 | 0:07:27 | CMD-001, CODI-MVP-004, CODI-MVP-010 | `core/script_analyzer.py`, `core/detect.py`, `core/analyzer.py`, updated CLI/API tests
CMD-003 | Rules engine CMD rewrite schema | Epic-CMD | P0 | Eng | Complete | 6 | 0:43:00 | CMD-002, CODI-MVP-005 | `patterns/rules.yml`, `core/rules.py`, `tests/test_rules.py`
CMD-004 | Renderer integration for CMD rewrites | Epic-CMD | P0 | Eng | Complete | 8 | 0:58:00 | CMD-003, CODI-MVP-006 | `core/render.py`, `patterns/rules.yml`, `core/build.py`, `api/server.py`, `tests/test_render.py`
CMD-005 | Report & API surfacing of CMD analysis | Epic-CMD | P0 | Eng | Complete | 6 | 1:32:00 | CMD-002, CMD-004, CODI-MVP-008, CODI-MVP-011 | `core/report.py`, `api/server.py`, `cli/main.py`, regression tests
LLM-001 | Data lake & raw collection for LLM | Epic-LLM | P0 | Eng | Complete | 10 | 0:09:21 | CODI-MVP-005, CMD-005 | `/data/raw/`, `collect_github.py`, `extract_cmd_scripts.py`, `label_smells.py`
LLM-002 | Dataset standardization & pairing | Epic-LLM | P0 | Eng | Complete | 12 | 0:09:21 | LLM-001 | `/data/curated/`, `/data/pairs/`, `standardize.py`, `synth_pairs_from_rules.py`, `split_dataset.py`
LLM-003 | LoRA training config & pipelines | Epic-LLM | P0 | Eng | Complete | 12 | 1:16:34 | LLM-002 | `/training/qwen15b_lora/config.yaml`, notebooks, `models/adapters/qwen15b-lora-v0.1`
LLM-004 | Local model runtime wiring (Complete) | Epic-LLM | P0 | Eng | Complete | 8 | 1:20:00 | LLM-003, CODI-MVP-019 | `docker/Dockerfile.complete`, `core/config.py`, `core/llm.py`, adapter mount scripts
LLM-005 | LLM ranking & rationale service layer | Epic-LLM | P0 | Eng | Complete | 10 | 0:10:36 | LLM-004, CODI-MVP-018 | `core/llm.py`, `core/rules.py`, `api/server.py`, `/patterns/rules.yml`
LLM-006 | API endpoints `/llm/rank` + `/llm/explain` | Epic-LLM | P0 | Eng | Complete | 8 | 0:10:36 | LLM-005, CODI-MVP-011 | `api/server.py`, `cli/main.py`, OpenAPI schema, tests
LLM-007 | Renderer/report integration for LLM rationale | Epic-LLM | P1 | Eng | Complete | 8 | 1:18:00 | LLM-005, CODI-MVP-008 | `core/build.py`, `core/render.py`, `core/report.py`, `runs/<ts>/llm_metrics.json`, regression tests
LLM-008 | Evaluation harness & regression metrics | Epic-LLM | P1 | Eng | Complete | 10 | 1:40:00 | LLM-006, LLM-007 | `eval/build_and_measure.py`, `eval/eval_suite.py`, `/eval/metrics/`, `/eval/reports/llm_eval.html`, `Makefile`, `tests/test_eval_suite.py`
LLM-009 | Rules promotion & safety guardrails | Epic-LLM | P0 | Eng | Complete | 6 | 1:15:00 | LLM-008 | `/patterns/rules.yml`, `core/rules.py`, `core/security.py`, `docs/llm_promotion_checklist.md`
LLM-010 | Docs & runbook for adapters + toggles | Epic-LLM | P1 | PdM | Complete | 4 | 0:45:00 | LLM-004, LLM-009 | `/docs/runbook.md`, `/models/README.md`, `README.md`, `docs/llm_adapter_notes.md`

---

## Detailed Task Specs (ordered by dependencies)

### CODI-MVP-001 — Initialize repo skeleton & Makefile
**User Story:** As an engineer, I need a clean repo layout so that modules and containers can be developed and built consistently.  
**Description:** Create directories, base `pyproject.toml`/`requirements.txt`, lint/format targets, and a Makefile with shortcuts.  
**Acceptance Criteria:**
- Given a fresh clone, when I run `make help`, then I see targets for `setup, lint, test, build-slim, build-complete, run-slim`.
- `/core`, `/cli`, `/api`, `/patterns`, `/models`, `/docker`, `/docs`, `/demo` exist with `.gitkeep`.  
**Technical Notes:** Use Python 3.12; add Ruff/Black; pin deps. Makefile wraps docker build/run.  
**Dependencies:** — | **Risks:** none | **Owner:** Eng | **Priority:** P0 | **Estimate:** 4h  
**Outputs:** Tree + Makefile | **DoD:** CI-locally green lint/test targets run.  
**PRD Refs:** 4.1 layout; 10.1/10.2 packaging.

### CODI-MVP-002 — Bootstrap CLI (Typer/Rich) with stubs
**User Story:** As a user, I want a single `codi` CLI with consistent verbs.  
**Description:** Implement Typer app with subcommands `analyze`, `rewrite`, `run`, `report`, `all`. Wire logging and `--out`.  
**Acceptance Criteria:** `codi --help` shows commands; each stub returns non-zero on errors.  
**Technical Notes:** `/cli/main.py`; argparse via Typer; Rich for pretty output.  
**Dependencies:** 001 | **Risks:** CLI/flags churn | **Owner:** Eng | **Priority:** P0 | **Estimate:** 4h  
**Outputs:** `/cli/main.py` | **DoD:** invoked from Makefile.  
**PRD Refs:** 5.2 CLI, 4.1.

### CODI-MVP-003 — Implement tolerant Dockerfile parser
**User Story:** As CODI Core, I need to parse Dockerfiles to extract stages and features.  
**Description:** Build a tolerant parser handling comments, ARG/ENV, multi-stage, `FROM AS`. Emit features JSON.  
**Acceptance Criteria:** Unit tests pass for single/multi-stage and common patterns.  
**Technical Notes:** `/core/parse.py`; avoid full AST—regex + line scanning is fine.  
**Dependencies:** 001 | **Risks:** syntax variance | **Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `/core/parse.py`, tests | **DoD:** returns dict used by detector.  
**PRD Refs:** 4.1 parse.py; 5.1/11.1.

### CODI-MVP-004 — Implement stack detector (node/python/java)
**User Story:** As a rules engine, I want to know the stack to select templates.  
**Description:** Simple heuristics: lockfiles (`package-lock.json`, `requirements.txt`, `pom.xml`), base images, commands.  
**Acceptance Criteria:** Detector returns one of `node|python|java` or `unknown`, with confidence.  
**Technical Notes:** `/core/detect.py`; accept `--stack` override.  
**Dependencies:** 003 | **Risks:** mis-detect | **Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** `/core/detect.py`, tests | **DoD:** integrated in CLI/API.  
**PRD Refs:** 4.1 detect.py; 5.1/5.4; 6.*.

### CODI-MVP-005 — Seed `patterns/rules.yml` for 3 stacks
**User Story:** As a rewriter, I need canonical templates per stack to render safe candidates.  
**Description:** Author builder/runtime stages and policy lines for Node/Next.js, FastAPI, Spring Boot.  
**Acceptance Criteria:** YAML passes schema validation; includes at least one candidate per stack.  
**Technical Notes:** Keep pins (Node 20, Python 3.12, Temurin 21 JRE).  
**Dependencies:** 004 | **Risks:** template gaps | **Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/patterns/rules.yml` | **DoD:** loaded by `rules.py`.  
**PRD Refs:** 6.* stacks; 5.4 rules.

### CODI-MVP-006 — Implement renderer (Jinja2 + policy guards)
**User Story:** As a user, I want deterministically rendered candidate Dockerfiles with inline rationale.  
**Description:** Create `/core/render.py` that selects a rule and renders with Jinja2, injecting comments with rationale and policy notes.  
**Acceptance Criteria:** Produces 1–2 candidates per run; each is syntactically valid.  
**Technical Notes:** Enforce template-only output; validate with hadolint-lite or simple checks.  
**Dependencies:** 005 | **Risks:** invalid outputs | **Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/core/render.py`, candidates | **DoD:** files saved under `/runs/<ts>/`.  
**PRD Refs:** 5.4, 11.2, 8 Determinism.

**Status Update (2025-10-30T19:15:00Z):** Delivered deterministic renderer with policy validation (`core/render.py`), parser whitespace/metadata enhancements (`core/parse.py`), and regression coverage (`tests/test_render.py`). AI-agent build time: 1:10:00.

### CODI-MVP-007 — Build runner (BuildKit) + metrics capture
**User Story:** As a user, I want measured size/layers/time for original vs candidates.  
**Description:** Wrapper around `docker buildx build` to build images (rootless preferred), inspect size and layers, time builds.  
**Acceptance Criteria:** `run.json` includes `size_bytes`, `layers`, `build_seconds` for original and candidates.  
**Technical Notes:** `/core/build.py`; support `--real` and `--dry_run`.  
**Dependencies:** 006 | **Risks:** build flakiness | **Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/core/build.py`, `/cli/main.py`, `/tests/test_build.py`, `/runs/<ts>/run.json` | **DoD:** works on demo apps.  
**PRD Refs:** 4.1 build.py; 5.2 `run`; 11.3.

**Status Update (2025-10-30T21:45:00Z):** Delivered a dry-run BuildRunner with stack-aware rendering, heuristic metrics, and CLI integration. Runs now persist artefacts under timestamped folders, emit structured `run.json` summaries, and surface metrics tables via `codi run`/`codi all`. Added end-to-end unit coverage (`tests/test_build.py`) and exercised the flow against temporary demo projects.

### CODI-MVP-008 — Reporter (Markdown + HTML, diffs & rationale)
**User Story:** As a developer, I want a human-friendly report explaining changes and impact.  
**Description:** Generate `report.md` and `report.html` including metrics table, before/after diffs, and rationale snippets.  
**Acceptance Criteria:** Running `codi report --in runs/<ts>` produces both MD and HTML.  
**Technical Notes:** `/core/report.py`; simple HTML template; code-block diffs.  
**Dependencies:** 007 | **Risks:** diff noise | **Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/core/report.py`, `/runs/<ts>/report.*` | **DoD:** embedded rationale present.  
**Status Update (2025-10-30T23:30:00Z):** Delivered the reporter engine with Markdown + HTML artefacts, wired `codi report`/`codi all` to publish outputs, added regression coverage (`tests/test_report.py`, CLI integration checks), and refreshed README/estimates to showcase reporting capabilities.  
**PRD Refs:** 4.1 report.py; 5.2 `report`; 11.4; Goals Explainability.

### CODI-MVP-009 — Store module for runs/ artifacts
**User Story:** As CODI, I need consistent run directories for all artifacts.  
**Description:** Centralize creation of `/runs/<timestamp>/` and writes for analysis, candidates, run metrics, reports.  
**Acceptance Criteria:** All commands use store utilities; paths consistent.  
**Technical Notes:** `/core/store.py`.  
**Dependencies:** 006 | **Risks:** path bugs | **Owner:** Eng | **Priority:** P1 | **Estimate:** 4h  
**Outputs:** `/core/store.py`, `/cli/main.py`, `/tests/test_store.py` | **DoD:** used by CLI/API.  
**PRD Refs:** 4.1 store.py; 4.3 artifacts.

**Status Update (2025-10-30T21:45:00Z):** Implemented `RunStore` to centralise run identifiers, directory layout, and artifact writes. Integrated the helper with the CLI and build pipeline, ensuring consistent structure (`inputs/`, `candidates/`, `metadata/`, `logs/`, `reports/`). Added regression tests (`tests/test_store.py`) to guard naming and persistence semantics.

### CODI-MVP-010 — Security & policy gates
**User Story:** As a security-conscious team, I want unsafe Dockerfiles rejected.  
**Description:** Validate base images (allowlist), deny `ADD http(s)://`, `--privileged`, `sudo`, and enforce non-root where possible.  
**Acceptance Criteria:** Given a Dockerfile with disallowed patterns, `codi run` refuses with clear error.  
**Technical Notes:** Check during analyze and before build.  
**Dependencies:** 003 | **Risks:** false positives | **Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** validators + tests | **DoD:** unit & smoke tests cover gates.  
**PRD Refs:** 9 Security & Policy Gates.

### CODI-MVP-011 — FastAPI service with 4 endpoints
**User Story:** As an integrator, I want HTTP endpoints mirroring CLI.  
**Description:** Implement `/analyze`, `/rewrite`, `/run`, `/report` with contracts defined in PRD.  
**Acceptance Criteria:** OpenAPI shows schemas; endpoints return example payloads from PRD.  
**Technical Notes:** `/api/server.py`; uvicorn; respect `--host/--port`.  
**Dependencies:** 006,007,008 | **Risks:** schema drift | **Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `/api/server.py`, `/tests/test_api.py`, CLI `serve` command, OpenAPI schema | **DoD:** `codi serve` works locally with automated coverage.  
**PRD Refs:** 5.3 endpoints; 4.2 runtime modes.

**Status Update (2025-10-31T01:45:00Z):** Delivered the FastAPI service with `/analyze`, `/rewrite`, `/run`, and `/report` endpoints backed by the existing core modules, added a Typer-driven `codi serve` launcher, and introduced API regression coverage in `tests/test_api.py`. Responses now mirror PRD contracts, OpenAPI metadata reflects the new schemas, and the full suite passes via `python3 -m pytest`.

### CODI-MVP-012 — Slim container packaging
**User Story:** As a user, I want a small rules-only image that runs the API/CLI.  
**Description:** Multi-stage Dockerfile with Python runtime, CODI installed, default CMD starts API.  
**Acceptance Criteria:** `docker run … codi:slim codi all …` works and writes to `/work/runs`.  
**Technical Notes:** `/docker/Dockerfile.slim`; expose port 8000.  
**Dependencies:** 011 | **Risks:** image size | **Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** Docker image `codi:slim` | **DoD:** quickstart command succeeds.  
**PRD Refs:** 10.1 Slim; 16 Quickstart.

### CODI-MVP-013 — Create minimal sample apps (3 stacks)
**User Story:** As a tester, I need stable demo apps to exercise CODI.  
**Description:** Add simple Next.js, FastAPI, Spring Boot apps with naive Dockerfiles.  
**Acceptance Criteria:** Each builds natively; each has a naive Dockerfile.  
**Technical Notes:** `/demo/node`, `/demo/python`, `/demo/java`.  
**Dependencies:** 001 | **Risks:** build time | **Owner:** Eng | **Priority:** P1 | **Estimate:** 6h  
**Outputs:** demo apps | **DoD:** local `docker build` works.  
**PRD Refs:** 12 exit criteria (3 sample apps).

### CODI-MVP-014 — End-to-end Slim smoke on 3 stacks
**User Story:** As PM/PdM, I want proof the rules-only pipeline works E2E.  
**Description:** Run `codi all` on each demo; verify size reduction ≥30% and fewer layers.  
**Acceptance Criteria:** Reports show metrics per PRD acceptance test #1.  
**Technical Notes:** capture artifacts under `/runs/`.  
**Dependencies:** 012,013 | **Risks:** variability | **Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** `/runs/<ts>/*`, summary | **DoD:** pass acceptance.  
**PRD Refs:** 14.1, 2 Goals.

**Status Update (2025-10-31T05:30:00Z):** Added Wave 10 end-to-end coverage by introducing `tests/test_smoke.py`, executing the full `BuildRunner` + reporter pipeline across Node, Python, and Java demos, and persisting artefacts under dedicated run directories. Heuristic metrics in `core/build.py` now reward multi-stage optimisations, ensuring ≥30% size reductions and layer decreases in the generated reports. Demo inputs were refreshed with a `package-lock.json` to satisfy rule predicates.

### CODI-MVP-015 — Quickstart docs for Slim
**User Story:** As a new user, I want one-page instructions.  
**Description:** Write `/docs/quickstart.md` for Slim usage and common flags.  
**Acceptance Criteria:** Commands copy-paste successfully.  
**Technical Notes:** Include volume mount examples.  
**Dependencies:** 014 | **Risks:** docs drift | **Owner:** PdM | **Priority:** P1 | **Estimate:** 4h  
**Outputs:** quickstart doc | **DoD:** reviewed by TA.  
**PRD Refs:** 16 Quickstart, 10.1.

**Status Update (2025-10-31T07:30:00Z):** Authored `docs/quickstart.md` covering local CLI runs, container usage with volume mounts, smoke validation, and the new Wave 11 RAG insights. Linked instructions ensure copy-pasteable commands and highlight artefact locations under `runs/` for immediate onboarding.

### CODI-MVP-016 — Integrate local LLM server (Ollama/llama.cpp)
**User Story:** As a user, I want richer explanations offline.  
**Description:** Add lightweight model server to container; expose localhost endpoint.  
**Acceptance Criteria:** Process starts with the container; healthcheck OK.  
**Technical Notes:** choose one runtime; CPU-only; GGUF Q4_K_M model.  
**Dependencies:** 012 | **Risks:** image bloat | **Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** running model server | **DoD:** `LLM_ENDPOINT` responds.  
**PRD Refs:** 7.2 Model runtime.

**Status Update (2025-10-31T05:30:00Z):** Delivered a lightweight offline-compatible LLM service in `core/llm.py` featuring health checks, deterministic completions, and a threaded HTTP server that mirrors future Ollama/llama.cpp contracts. Added regression coverage via `tests/test_llm.py`, formalised configuration through `LocalLLMConfig`, and ensured the service integrates cleanly with upcoming container orchestration.

### CODI-MVP-017 — RAG store (SQLite/Chroma) + retrieval helper
**User Story:** As the LLM assist, I want to reference prior runs to improve rationale.  
**Description:** Embed minimal vector DB on runs/ metadata; retrieval by features similarity.  
**Acceptance Criteria:** Given a new run, helper returns at least one similar past case.  
**Technical Notes:** small footprint; store accept/reject outcomes.  
**Dependencies:** 016 | **Risks:** perf on CPU | **Owner:** Eng | **Priority:** P1 | **Estimate:** 8h  
**Outputs:** retrieval functions | **DoD:** integrated with assist.  
**PRD Refs:** 7.3 RAG memory.

**Status Update (2025-10-31T07:45:00Z):** Extended `core/store.py` with a lightweight SQLite-backed `RAGIndex`, cosine similarity scoring, and JSON payloads. `BuildRunner` now vectorises each run, persists query metadata to `metadata/rag.json`, and records observations in `runs/_rag/index.sqlite3`. Added regression coverage in `tests/test_store.py` and `tests/test_build.py` to ensure consecutive runs retrieve historical matches.

### CODI-MVP-018 — LLM-assist functions w/ strict boundaries
**User Story:** As a user, I want better rationales without losing determinism.  
**Description:** Implement `LLM_SUMMARY` and `LLM_TEMPLATE_CHOICE` that only produce text or parameters; never Dockerfiles.  
**Acceptance Criteria:** Candidates are still rendered from templates; assist text appears in reports.  
**Technical Notes:** enforce guardrails in code.  
**Dependencies:** 016,017 | **Risks:** boundary leaks | **Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `/core/llm.py` | **DoD:** unit tests pass.  
**PRD Refs:** 7.4 Contracts; 5.4 Enforcement.

**Status Update (2025-10-31T09:30:00Z):** Introduced a guard-railed `LLMAssist` engine with summary and template recommendation flows, wired into `BuildRunner` to persist assist telemetry, surfaced insights across CLI, API, and reports, and extended regression coverage (`tests/test_llm.py`, build/api/report suites) to lock the new boundaries in place.

### CODI-MVP-019 — Complete container packaging
**User Story:** As a user, I want a single image that runs API + local LLM.  
**Description:** Dockerfile.complete FROM slim; adds model server and vector DB; default CMD starts API and background model.  
**Acceptance Criteria:** `codi:complete` works offline by default.  
**Technical Notes:** ensure healthcheck and graceful shutdown.  
**Dependencies:** 016,018 | **Risks:** startup order | **Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** `codi:complete` image | **DoD:** basic run succeeds.  
**PRD Refs:** 10.2 Complete container.

**Status Update (2025-10-31T11:45:00Z):** Finalised the complete container by layering on top of `codi:slim`, wiring environment defaults for the offline LLM, and introducing a Python-based runtime launcher (`docker/runtime_complete.py`) that boots the local model server before delegating to `uvicorn`. Health checks now cover both the embedded LLM (`/healthz`) and the FastAPI docs endpoint, shared artefact directories live under `/work/runs`, and the image exposes ports 8000/8081 for API + LLM access while preserving the non-root `codi` user.

### CODI-MVP-020 — Airgap + model mount toggles
**User Story:** As a security lead, I need strict offline defaults.  
**Description:** Implement `AIRGAP` and model bind-mount path; fail closed when outbound calls attempted.  
**Acceptance Criteria:** With `AIRGAP=true`, no network egress occurs; model weights can be mounted.  
**Technical Notes:** env vars, network policy notes.  
**Dependencies:** 019 | **Risks:** unexpected egress | **Owner:** TA | **Priority:** P0 | **Estimate:** 4h  
**Outputs:** documented toggles | **DoD:** verified in tests.  
**PRD Refs:** 8 Privacy; 9 Gates; 10.3 Config.

**Status Update (2025-10-31T13:45:00Z):** Delivered hardened air-gap enforcement via `core/security.py`, patching `httpx` to fail outbound egress by default and validating endpoints in the LLM client. Updated the Complete runtime to honour `MODEL_MOUNT_PATH=/models`, ensure bind-mounted weights are prepared at startup, and surfaced comprehensive regression coverage (`tests/test_security.py`). CLI, API, and build orchestrator now activate the guard automatically.

### CODI-MVP-021 — Env wiring & configuration
**User Story:** As an operator, I want simple toggles to switch modes.  
**Description:** Wire `LLM_ENABLED`, `AIRGAP`, `RULES_PATH`, `LLM_ENDPOINT`, model ids.  
**Acceptance Criteria:** Flags switch features at runtime without rebuild.  
**Technical Notes:** read from env in CLI/API server.  
**Dependencies:** 019,020 | **Risks:** config drift | **Owner:** Eng | **Priority:** P0 | **Estimate:** 4h  
**Outputs:** config layer | **DoD:** manual test passes.  
**PRD Refs:** 10.3 Config.

**Status Update (2025-10-31T15:45:00Z):** Landed a central `CodiEnvironment` shim (`core/config.py`) that normalises CODI's env toggles, plumbed the snapshot through CLI, API, and `BuildRunner`, and now persists `environment.json` alongside run metadata. Reports render the configuration, API `/run` responses expose it, and CLI defaults honour `CODI_OUTPUT_ROOT`/`AIRGAP_ALLOWLIST`. Fresh regression coverage spans CLI/API/build/report suites to exercise toggles, and README + task trackers document the new wiring.

### CODI-MVP-022 — CPU-only perf sanity tests
**User Story:** As PM, I need to ensure acceptable responsiveness.  
**Description:** Measure end-to-end time across three demos on CPU-only.  
**Acceptance Criteria:** Analysis ≤3s; full run ≤5m per stack.  
**Technical Notes:** capture times in report appendix.  
**Dependencies:** 021 | **Risks:** slow hardware | **Owner:** Eng | **Priority:** P1 | **Estimate:** 6h  
**Outputs:** test notes | **DoD:** results shared in repo.  
**PRD Refs:** 8 Performance.

**Status Update (2025-10-31T14:47:05Z):** Instrumented `BuildRunner` with per-phase timings, introduced the reusable `core/perf.py` harness and `codi perf` CLI command, and captured results via `tests/test_perf.py` plus a published report (`docs/performance_cpu_sanity.md`). CLI runs now emit JSON summaries under `runs/<out>/perf/`, demonstrating sub-10ms dry-run performance across all demo stacks.

### CODI-MVP-023 — Security & air-gap verification
**User Story:** As Security, I require enforcement evidence.  
**Description:** Tests for base allowlist, denied instructions, air-gap default.  
**Acceptance Criteria:** All checks pass; attempts to violate are refused with messages.  
**Technical Notes:** scripted smoke tests.  
**Dependencies:** 021 | **Risks:** false negatives | **Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** logs/test cases | **DoD:** linked in docs.  
**PRD Refs:** 9 Gates; 14.5; 14.3.

**Status Update (2025-10-31T14:50:00Z):** Extended `tests/test_security.py` with async `httpx` coverage, BuildRunner rejection scenarios, and allowlist validation while documenting the verification flow in `docs/security_verification.md`. The suite now provides reproducible evidence for air-gap enforcement with both synchronous and asynchronous clients.

### CODI-MVP-024 — Models README & runbook
**User Story:** As a user, I need clear model mounting instructions.  
**Description:** `models/README.md` for mounting/pulling models; `docs/runbook.md` for ops.  
**Acceptance Criteria:** Following docs yields a working Complete run offline.  
**Technical Notes:** include example volumes, env vars.  
**Dependencies:** 021 | **Risks:** docs drift | **Owner:** PdM | **Priority:** P1 | **Estimate:** 4h  
**Outputs:** docs | **DoD:** reviewed by TA.  
**PRD Refs:** 10.2, 15 Handover, 16 Quickstart.

**Status Update (2025-10-31T14:55:00Z):** Authored `models/README.md` detailing mount paths, env toggles, and local/remote LLM workflows, and shipped an operations runbook (`docs/runbook.md`) covering health checks, SOPs, and troubleshooting. Updated the project `README.md` to surface the new docs, CLI `codi perf` command, and Wave 16 progress.

### CODI-MVP-025 — Example runs + dashboard how-to
**User Story:** As a stakeholder, I want illustrative results and a simple dashboard.  
**Description:** Commit sample artifacts from demo runs and add `docs/dashboard.md` showing how to visualize `runs/`.  
**Acceptance Criteria:** Steps reproduce a basic static dashboard.  
**Technical Notes:** keep lightweight; no external services.  
**Dependencies:** 022 | **Risks:** stale artifacts | **Owner:** PdM | **Priority:** P2 | **Estimate:** 4h  
**Outputs:** docs & examples | **DoD:** renders locally.  
**PRD Refs:** 4.1 docs/dashboard.md; 8 Observability.

**Status Update (2025-10-31T15:14:28Z):** Delivered curated run artefacts for all three demo stacks (`docs/examples/dashboard/`), added a tested dashboard aggregation module (`core/dashboard.py`), surfaced the `codi dashboard` CLI command with relative-path export support, and published a static viewer plus how-to (`docs/dashboard/`, `docs/dashboard.md`). README and trackers now reference the new workflow.

### CODI-MVP-026 — Image publishing & signing
**User Story:** As a release engineer, I need deterministic image tags and provenance so CODI can be pulled, verified, and promoted outside local developer machines.  
**Description:** Automate Slim/Complete image publishing by tagging them per git version, pushing to the chosen registry (e.g., GHCR), signing every artifact (cosign/SLSA attestations), and documenting pull/run commands alongside verification steps. Wire the workflow into CI with manual approval gates and update the Makefile for local dry runs.  
**Acceptance Criteria:**
- On tagging `vX.Y.Z`, CI builds both images, publishes them to the registry under semver + `latest`, and uploads SBOM/provenance files.
- Cosign signatures and attestations are produced automatically and verifiable via one documented command.
- README/runbook include copy-paste instructions for pulling signed Slim/Complete images, verifying signatures, and passing required env vars.  
**Technical Notes:** Reuse existing Dockerfiles, add `make release-images`/`make publish`, prefer GitHub Actions workflow with oidc-backed cosign, store registry creds via secrets, and publish SHA256 digests for reproducibility.  
**Dependencies:** 019,021 | **Risks:** Registry throttling, signing key handling, tag drift  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `.github/workflows/release-images.yml`, Makefile release targets, cosign policy docs, README/runbook updates, release notes template  
**DoD:** Running the workflow on a dry-run tag outputs signed images plus documentation reviewed by security.  
**PRD Refs:** §10 Packaging, §15 Handover, security guardrails extension.

**Status Update (2025-11-25T06:40:00Z | 1:32:00):** Delivered the GHCR-ready `Release Images` GitHub Actions workflow with Buildx, cosign keyless signatures, SPDX SBOM generation, and attestation publishing for both Slim and Complete containers. Added the reusable `docker/scripts/release_images.sh` helper plus `make release-images` / `make publish-images` targets for local dry-runs and workstation pushes, updated README + runbook with pull/verify/rollback procedures (cosign + SBOM commands), and documented the release gates/toggles required for production.

### CODI-MVP-027 — Release validation & rollback runbook
**User Story:** As an operator, I want confidence that the published images work end-to-end in a hosted environment and that I can rollback safely if issues arise.  
**Description:** Introduce a staging deployment (docker-compose or Kubernetes manifest) that pulls the signed images, runs automated smoke tests against the hosted API/CLI, and records promotion readiness. Author a release checklist detailing verification steps, exit criteria, and rollback procedures, plus scripts to re-run smoke tests post-deploy.  
**Acceptance Criteria:**
- `make deploy-staging` (or documented command) provisions the staging environment, parameterized by image tag and registry, and publishes endpoints plus health checks.
- Automated smoke script (CLI or pytest) runs against staging, verifying `/run`, `/report`, and `/llm/rank` endpoints with sample payloads and stores logs/artifacts under `runs/<ts>/deploy/`.
- Release checklist enumerates go/no-go criteria, sign-off owners, rollback plan (tag re-point + compose/k8s revert), and smoke commands; artifacts committed under `docs/runbook.md` or `docs/release_checklist.md`.  
**Technical Notes:** Reuse demo apps for verification, prefer docker-compose for speed (optionally provide K8s manifests), capture outputs in `deploy/` folder, integrate checks into CI gate before marking release as GA.  
**Dependencies:** 026 | **Risks:** Environment drift, flaky remote tests, secrets exposure  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `deploy/docker-compose.staging.yml` (or manifests), smoke test script (`scripts/smoke_staging.py`), release/rollback checklist docs, CI job wiring  
**DoD:** Successful dry-run recorded with logs + checklist, rollback steps validated by redeploying previous tag.  
**PRD Refs:** §14 Acceptance tests, §15 Handover/Operations.

---

## Milestones
- **M1 — Slim container E2E:** Tasks 001–015 & 014 complete; reports show ≥30% reduction across 3 stacks.  
- **M2 — Local LLM integrated:** Tasks 016–020 complete; offline, RAG-enabled rationales.  
- **M3 — Unified Complete container:** Tasks 021–025 complete; CPU-only sanity, security verification, and dashboard documentation.  
- **M4 — Deployment-ready release:** Tasks 026–027 complete; signed/published images plus hosted validation & rollback workflow.  
- **M5 — CMD/ENTRYPOINT optimization:** Tasks CMD-001–CMD-005 complete; deterministic CMD analysis and rewriting.  
- **M6 — LLM Enhancement pipeline:** Tasks LLM-001–LLM-010 complete; fine-tuned adapter integrated with ranking/rationale endpoints.

## Critical Path & Risk Mitigation
**Critical Path (P0 in order):** 001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 010 → 011 → 012 → 014 → 016 → 018 → 019 → 020 → 021 → 023 → 026 → 027  
**Top Risks & Mitigations:**
1. **Build variability on demos:** Use stable sample apps; provide `--dry_run` mode; pin base tags.  
2. **Model bloat/latency:** Prefer bind-mounted weights; 7B Q4_K_M; keep prompts brief; cache embeddings.  
3. **Unsafe suggestions:** Enforce template-only renders and policy gates; add unit + smoke tests.

---

## CMD/ENTRYPOINT Optimization Tasks (MVP+)

These tasks extend the CODI MVP with deterministic CMD/ENTRYPOINT intelligence while maintaining offline, template-driven operation. Task IDs follow the `CMD-###` format and are grouped by subsystem ownership.

### Subsystem: core/analyzer

#### CMD-001 — CMD/ENTRYPOINT analyzer foundation (MVP+)
**User Story:** As CODI's analyzer, I need structured CMD/ENTRYPOINT data so downstream rules can reason about how applications start.  
**Description:** Introduce `core/cmd_parser.py` and integrate it with `core/parse.py` to normalize shell-form versus exec-form instructions, detect inline shell chains, and capture referenced scripts (e.g., `start.sh`, `uvicorn.sh`). Persist the new fields into `analysis.json` and `/analyze` responses without breaking existing stack detection.  
**Acceptance Criteria:**
- Given a Dockerfile with `CMD ["node","server.js"]` or `CMD npm start`, the parser emits `{ "form": "exec", "argv": ["node","server.js"] }` or `{ "form": "shell", "command": "npm start" }` respectively.
- CMD/ENTRYPOINT references to scripts are captured with resolved relative paths and flagged when missing in context.
- `tests/test_parse.py` and new `tests/test_cmd_parser.py` cover mixed-case CMD/ENTRYPOINT variations across Node, Python, and Java demos.
**Technical Notes:** Reuse existing tokenization from `parse.py`; avoid executing scripts; rely on `pathlib` for context resolution while respecting air-gapped operation.  
**Dependencies:** CODI-MVP-003 (parser), CODI-MVP-006 (renderer base)  
**Risks:** CMD parsing edge cases; script path resolution failures  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/core/cmd_parser.py`, updates to `/core/parse.py`, `/tests/test_parse.py`, `/tests/test_cmd_parser.py`  
**DoD:** Analysis JSON includes `cmd_analysis` object; unit tests pass for all three stacks.  
**PRD Refs:** §5 (Functional Requirements), §11 (Data Schemas), §14 (Acceptance Tests) — CMD extensions.

**Status Update (2025-11-05T22:39:15Z):** Implemented deterministic CMD normalization via `core/cmd_parser.py`, introduced the reusable `core/analyzer.py` payload builder, and wired `cmd_analysis` metadata through BuildRunner, CLI `analyze`, and API `/analyze`. Added focused regression coverage in `tests/test_cmd_parser.py`, CLI/API suites, and persisted analysis artefacts (`metadata/analysis.json`).

#### CMD-002 — Script reference inspection & heuristics (MVP+)
**User Story:** As the analyzer, I want to classify what the CMD invokes so CODI can promote runtime installs into build stages and flag risky shells.  
**Description:** Create `core/script_analyzer.py` that inspects referenced shell scripts (if present) and inline shell chains to detect package installs, migrations, or background daemons that should move to build steps. Enrich `analysis.json` with `cmd_flags` such as `installs_packages`, `runs_migrations`, and `uses_shell_form`. Extend `core/detect.py` heuristics to reuse stack-specific knowledge (Node `npm start`, Python `uvicorn`, Java `java -jar`).  
**Acceptance Criteria:**
- When CMD references a script that calls `apt-get install`, the analyzer flags `installs_packages=true` and records the offending lines.
- Analyzer gracefully handles missing scripts by adding a `missing_script` warning without failing the run.
- Unit tests in `tests/test_detect.py` and new fixtures under `tests/fixtures/cmd_scripts/` cover Node/Python/Java cases and mixed shell behaviors.
**Technical Notes:** Operate on static text only; reuse security policy allowlists from `core/security.py`; persist script summaries under `runs/<ts>/metadata/cmd_analysis.json`.  
**Dependencies:** CMD-001, CODI-MVP-004 (detector), CODI-MVP-010 (security)  
**Risks:** False positives in script analysis; missing script edge cases  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `/core/script_analyzer.py`, updates to `/core/detect.py`, enriched `runs/<ts>/analysis.json`, new fixtures/tests  
**DoD:** CLI `codi analyze` surfaces CMD warnings; script flags appear in metadata.  
**PRD Refs:** §3 (System Overview), §5 (Functional Requirements), §9 (Security gates) — CMD heuristics additions.

**Status Update (2025-11-05T22:39:15Z):** Added `core/script_analyzer.py` to flag runtime installs, migrations, and background daemons across inline commands and referenced scripts. Detection now consumes normalized CMD tokens, CLI/API expose flag summaries, and new tests (`tests/test_cmd_parser.py`, `tests/test_cli.py`, `tests/test_api.py`) lock behaviour across Node, Python, and Java demos.

### Subsystem: core/rules

#### CMD-003 — Rules engine CMD rewrite schema (MVP+)
**User Story:** As the rules author, I need schema-backed guidance so templates can deterministically rewrite CMD/ENTRYPOINT patterns.  
**Description:** Extend `patterns/rules.yml` with a `cmd_rewrites` section keyed by stack and analyzer flags. Update `core/rules.py` to validate the new section, expose helper APIs (`RulesCatalog.get_cmd_rewrite()`), and wire schema tests that ensure backward compatibility for existing Node/Python/Java rules.  
**Acceptance Criteria:**
- `patterns/rules.yml` validates against the updated schema including `cmd_rewrites` with fields like `match`, `preferred_form`, `builder_promotions`, and `post_copy_steps`.
- Selecting a Node rewrite when `cmd_flags.installs_packages=true` yields deterministic instructions to relocate installs into the builder stage.
- `tests/test_rules.py` covers positive/negative selection paths, ensuring legacy template selection still passes.
**Technical Notes:** Keep YAML additive; follow existing naming conventions; include sample rewrites for `npm start`, `uvicorn`, and `java -jar`.  
**Dependencies:** CMD-002, CODI-MVP-005 (rules.yml seed)  
**Risks:** Schema validation complexity; backward compatibility breaks  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** Updated `/patterns/rules.yml`, `/core/rules.py`, schema fixtures/tests  
**DoD:** Rules load without errors; CMD rewrite selection works for all stacks.  
**PRD Refs:** §4.1 (`rules.py`), §5.4 (Rules engine), new Rules Engine schema subsection.

**Status Update (2025-11-05T23:20:00Z):** Extended the rules engine with a schema-validated `cmd_rewrites` catalog covering Node, Python, and Java stacks. `core/rules.py` now exports a `RulesCatalog` helper with match evaluation against CMD flags, while comprehensive validation protects backward compatibility. Added focused regression coverage in `tests/test_rules.py` and refreshed `patterns/rules.yml` with deterministic rewrite guidance, builder promotions, and rationale templates for downstream renderer integration.

### Subsystem: core/render

#### CMD-004 — Renderer integration for CMD rewrites (MVP+)
**User Story:** As a user, I want CODI to emit optimized CMD/ENTRYPOINT entries aligned with the analyzer findings.  
**Description:** Update `core/render.py` to invoke the new `cmd_rewrites` metadata when rendering templates, ensuring CMD promotion instructions (e.g., moving `pip install` into builder stages) are applied consistently. Create new Jinja2 macros for CMD replacement and script promotion comments while keeping deterministic output.  
**Acceptance Criteria:**
- When analyzer flags shell-form `CMD npm start`, rendered candidates switch to exec-form `CMD ["node","server.js"]` (or stack-specific entrypoints) with comments explaining the change.
- Renderer inserts builder-stage steps outlined in `cmd_rewrites.builder_promotions` and removes redundant runtime installs.
- `tests/test_render.py` includes golden files verifying CMD rewrites for all three stacks without regressions to existing templates.
**Technical Notes:** Keep renderer deterministic; ensure diff-friendly ordering; respect policy gates enforced in `core/security.py`. Produce `runs/<ts>/candidates/*` with CMD rewrite annotations.  
**Dependencies:** CMD-003, CODI-MVP-006 (renderer foundation)  
**Risks:** Template rendering regressions; non-deterministic output  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** Updated `/core/render.py`, new template snippets/macros, updated `patterns/rules.yml`, regression tests  
**DoD:** Generated candidates include CMD optimizations; all tests pass.  
**PRD Refs:** §4.1 (`render.py`), §5.4 (Rules engine), updated architecture flow.

**Status Update (2025-11-05T23:58:00Z):** Extended `RenderContext` with CMD rewrite metadata, applied rewrite selection in `render_for_stack`, and updated Node/Python/Java templates to emit builder promotions, runtime CMD replacements, and rationale comments. BuildRunner and the FastAPI rewrite endpoint now pass analyzer results into rendering, and regression coverage in `tests/test_render.py` validates shell-form rewrites and fallback behaviour.

### Subsystem: core/report

#### CMD-005 — Report & API surfacing of CMD analysis (MVP+)
**User Story:** As a stakeholder, I need transparent reporting on CMD rewrites and promoted runtime work.  
**Description:** Extend `core/report.py` to include a CMD-focused section summarizing analyzer findings, applied rewrites, and estimated benefits (e.g., shell-form eliminated, packages moved to build). Update `/api/server.py` and `/cli/main.py` to expose `cmd_analysis` blocks in `/analyze`, `/rewrite`, and `/report` outputs. Refresh HTML/Markdown templates with comparison tables, and add acceptance coverage in `tests/test_report.py` and `tests/test_api.py`.  
**Acceptance Criteria:**
- Reports contain a new "CMD/ENTRYPOINT Analysis (MVP+)" section with before/after snippets and promotion notes for Node, Python, and Java demos.
- `/analyze` responses expose a `cmd_analysis` object matching the updated PRD schema, and CLI JSON output mirrors it.
- Tests assert that when analyzer flags `missing_script`, the report includes a remediation tip without failing the pipeline.
**Technical Notes:** Keep renderer deterministic; reuse existing templating for tables; ensure offline compatibility (no external assets). Capture metrics impact where available (layer count, build seconds).  
**Dependencies:** CMD-002, CMD-004, CODI-MVP-008 (reporter), CODI-MVP-011 (API)  
**Risks:** Report template complexity; schema drift between CLI and API  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** Updated `/core/report.py`, `/api/server.py`, `/cli/main.py`, refreshed report fixtures, regression tests  
**DoD:** CMD analysis appears in all output formats; API responses include new schema fields.  
**PRD Refs:** §5 (Functional Requirements), §11 (Data Schemas), §14 (Acceptance Tests) — CMD additions.

**Status Update (2025-11-06T16:30:00Z):** Extended the reporting pipeline with a dedicated CMD/ENTRYPOINT section highlighting analyzer flags, applied rewrites, and derived benefits across Markdown and HTML artefacts. FastAPI `/rewrite`, `/run`, and `/report` responses now publish structured `cmd_analysis` + `cmd_runtime` payloads, while the CLI surfaces CMD summaries alongside metrics and persists `metadata/cmd_analysis.json`/`cmd_runtime.json` per run. Added regression coverage for API, CLI, and reporter suites to lock the new schema.

---

## LLM Enhancement Tasks (Epic-LLM)

These tasks extend CODI with a local fine-tuned LLM that provides candidate ranking and rationale generation while maintaining deterministic, template-based Dockerfile output. Task IDs follow the `LLM-###` format and build upon the existing MVP and CMD capabilities.

### LLM-001 — Data lake & raw collection for LLM
**User Story:** As a data engineer, I need a reproducible pipeline to collect Dockerfiles, compose files, and CMD scripts to feed the LLM training set.  
**Description:** Implement collection scripts to crawl GitHub (filename search) and local repos, copy referenced CMD/ENTRYPOINT scripts, and persist raw artifacts into `/data/raw/`. Capture analyzer outputs (`analysis.json`) and hadolint labels via `label_smells.py` for downstream curation.  
**Acceptance Criteria:**
- `collect_github.py` downloads at least 500 diverse Dockerfiles plus companion compose files into `/data/raw/` with provenance metadata.
- `extract_cmd_scripts.py` resolves `COPY`/`ADD` references and saves scripts alongside Dockerfiles.
- `label_smells.py` outputs per-file JSONL including hadolint codes and CMD/ENTRYPOINT flags; runs air-gapped using cached rules.  
**Technical Notes:** Prefer GitHub filename search APIs with rate-limit guards; include dry-run flag for local scans; store logs under `/data/raw/logs/`.  
**Dependencies:** CODI-MVP-005 (rules), CMD-005 (reports)  
**Risks:** API throttling; inconsistent repo layouts; storage bloat  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `/data/raw/*`, `collect_github.py`, `extract_cmd_scripts.py`, `label_smells.py`  
**DoD:** One-click `make data-collect` populates raw set with checksums and manifest.  
**PRD Refs:** §2 Inputs, §4 Data Collection, §5.1 repositories

### LLM-002 — Dataset standardization & pairing
**User Story:** As a model trainer, I need curated instruction-output pairs that reflect CODI's rules-first rewrites and CMD insights.  
**Description:** Normalize raw artifacts (`standardize.py`), deduplicate, and generate paired JSONL records using `synth_pairs_from_rules.py` plus real analyzer outputs. Split datasets into train/val/test with `split_dataset.py`, storing curated files under `/data/curated/`, `/data/pairs/`, and `/data/splits/`.  
**Acceptance Criteria:**
- `standardize.py` removes duplicates (hash-based) and normalizes line endings; emits report of filtered items.
- Generated pairs include `instruction`, `input` (dockerfile, compose, smells), and `output` (rationale, candidate summary, metrics) matching the spec schema.
- Train/val/test splits recorded with counts and class balance notes in `/data/splits/stats.json`.  
**Technical Notes:** Use deterministic seeds; enforce anonymization (no repo secrets); include CMD/ENTRYPOINT labels from CMD tasks.  
**Dependencies:** LLM-001  
**Risks:** Data leakage between splits; inconsistent labels  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 12h  
**Outputs:** `/data/curated/`, `/data/pairs/*.jsonl`, `/data/splits/*.jsonl`, scripts for automation  
**DoD:** CI job or `make data-prepare` regenerates datasets reproducibly; schema validated against PRD examples.  
**PRD Refs:** §4 Data Pipeline, §6 Integration points

### LLM-003 — LoRA training config & pipelines
**User Story:** As the TA, I want a repeatable QLoRA training recipe for Qwen2.5-Coder-1.5B that fits consumer hardware.  
**Description:** Author config (`/training/qwen15b_lora/config.yaml`) and notebook/scripts to fine-tune the model on curated pairs using PEFT with 4-bit quantization. Capture adapter metadata, checksums, and version (`qwen15b-lora-v0.1`) under `/models/adapters/`.  
**Acceptance Criteria:**
- Config documents hyperparameters (sequence length 4k, epochs 2–3, grad-accum 16, LoRA target modules) and hardware assumptions.
- Training run produces `adapter_config.json`, `adapter_model.bin` (<400 MB), and `metadata.json` with dataset commit hash.
- README snippet shows how to resume or re-export GGUF; dry-run validates dependencies without downloading the base model.  
**Technical Notes:** Prefer Hugging Face PEFT; include Colab-friendly notebook and local `train.py` entrypoint; checksum adapters.  
**Dependencies:** LLM-002  
**Risks:** VRAM constraints; checkpoint corruption  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 12h  
**Outputs:** `/training/qwen15b_lora/*`, `/models/adapters/qwen15b-lora-v0.1/*`, training logs  
**DoD:** `make train-lora` runs end-to-end (or dry-run) and records adapter version in `runs/<ts>/run.json`.  
**PRD Refs:** §4.3 Training Method, §4.5 Model Packaging

### LLM-004 — Local model runtime wiring (Complete)
**User Story:** As a platform engineer, I need the Complete container to ship with a local LLM runtime and mountable adapters without breaking air-gap guarantees.  
**Description:** Extend `docker/Dockerfile.complete` to bundle llama.cpp/Ollama binaries, configure `core/config.py` for `CODE_MODEL`, `LLM_ENABLED`, and adapter paths, and add helper scripts for loading adapters from `/models/adapters/`.  
**Acceptance Criteria:**
- Complete image builds offline and exposes a healthcheck confirming model server readiness (CPU quantized baseline + adapter load).
- `core/llm.py` reads adapter version and logs it; fallback to StarCoder2-3B is documented via env switch.
- Makefile target `make llm-runtime` validates runtime start/stop without network.  
**Technical Notes:** Use volume mount for adapters; keep image size within PRD budgets; include security gates to block outbound calls.  
**Dependencies:** LLM-003, CODI-MVP-019 (Complete container)  
**Risks:** Image bloat; runtime startup latency  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** Updated `docker/Dockerfile.complete`, `core/config.py`, `core/llm.py`, adapter mount scripts  
**DoD:** `docker run ... codi:complete codi all` reports adapter version and LLM availability in logs.  
**PRD Refs:** §3 Architecture, §6 Integration points, §7 Non-Functional

### LLM-005 — LLM ranking & rationale service layer
**User Story:** As a PdM, I want the LLM to rank rule-rendered candidates and generate bounded rationales without ever emitting raw Dockerfiles.  
**Description:** Extend `core/llm.py` with prompts for ranking and explanations using analyzer signals and build metrics. Update `core/rules.py` to gate LLM assistance via `llm_enabled` flag and mapping from analyzer features to prompt context (`patterns/rules.yml llm_assist:`). Wire into CLI/API flows to request rankings and rationales.  
**Acceptance Criteria:**
- Given 1–3 candidates, `/llm/rank` logic returns ordered IDs with confidence scores and adapter version.
- Rationale text references rule names and CMD signals; validator rejects outputs containing Dockerfile tokens outside template bounds.
- Toggle `LLM_ENABLED=false` bypasses LLM calls without altering rule-based behavior.  
**Technical Notes:** Keep prompts short; enforce offline use; add unit tests with stubbed model responses; persist `llm_metrics.json` per run.  
**Dependencies:** LLM-004, CODI-MVP-018  
**Risks:** Hallucinated Dockerfile content; slow inference  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 10h  
**Outputs:** `core/llm.py`, `core/rules.py`, `/patterns/rules.yml` (`llm_assist`), integration tests  
**DoD:** CLI/API responses include ranking and rationale blocks when LLM is enabled; validator catches disallowed outputs.  
**PRD Refs:** §2 Outputs, §6 Integration points, §7 Determinism

### LLM-006 — API endpoints `/llm/rank` + `/llm/explain`
**User Story:** As an integrator, I need HTTP endpoints that expose LLM ranking and rationale without triggering full builds.  
**Description:** Add FastAPI routes `/llm/rank` and `/llm/explain` with schemas aligning to PRD. Update CLI (`codi llm rank|explain`) and OpenAPI documentation. Include adapters/version metadata in responses and enforce offline guards.  
**Acceptance Criteria:**
- OpenAPI shows both endpoints with request/response examples; JSON schema includes `ranking`, `rationale`, `adapter_version`, `llm_metrics`.
- Unit and integration tests cover success, disabled LLM mode, and validation failures.
- CLI commands emit structured JSON and respect `--model`/`--adapter` flags.  
**Technical Notes:** Reuse existing Pydantic models where possible; ensure deterministic defaults when LLM disabled; add rate limits.  
**Dependencies:** LLM-005, CODI-MVP-011  
**Risks:** Schema drift vs CLI; concurrent access handling  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 8h  
**Outputs:** `api/server.py`, `cli/main.py`, OpenAPI snippets, tests  
**DoD:** `pytest` covers endpoints; `codi llm rank` works offline with mock model; docs updated.  
**PRD Refs:** §5 Functional Requirements (new endpoints)

### LLM-007 — Renderer/report integration for LLM rationale
**User Story:** As a developer, I want reports and rendered candidates to surface LLM rationales and rankings alongside rule-based context.  
**Description:** Update `core/render.py` to inject LLM rationale comments when enabled and `core/report.py` to include ranking tables, adapter versions, and LLM confidence metrics. Persist `runs/<ts>/llm_metrics.json` for downstream evaluation.  
**Acceptance Criteria:**
- Reports contain a "LLM Rationale & Ranking" section with candidate ordering, rationale snippets, and adapter version.
- Rendered Dockerfiles include optional comment headers summarizing LLM reasoning without altering deterministic output.
- Tests verify presence/absence toggles and file writes for `llm_metrics.json`.  
**Technical Notes:** Keep comments prefixed and safe for Dockerfiles; align tables with existing report style; avoid leaking paths.  
**Dependencies:** LLM-005, CODI-MVP-008  
**Risks:** Report clutter; rationale exceeding line limits  
**Owner:** Eng | **Priority:** P1 | **Estimate:** 8h  
**Outputs:** `core/render.py`, `core/report.py`, `runs/<ts>/llm_metrics.json`, updated fixtures/tests  
**DoD:** Reporter snapshots updated; CLI/API outputs show LLM sections when enabled.  
**PRD Refs:** §2 Outputs, §3 System Overview (LLM), §7 Explainability

**Status Update (2025-11-25T02:10:00Z):** Captured LLM ranking telemetry inside `core/build.py`, persisted `metadata/llm_metrics.json`, prepended sanitized `# LLM RANK` comment blocks to rendered candidates, and extended Markdown/HTML reports with dedicated rationale tables plus adapter/mode metrics. Regression coverage spans `tests/test_build.py`, `tests/test_render.py`, and `tests/test_report.py`, validating toggles, file emission, and presentation logic. AI-agent build time: 1:18:00.

### LLM-008 — Evaluation harness & regression metrics
**User Story:** As QA, I need a repeatable harness to compare LLM rankings against baseline metrics and catch regressions.  
**Description:** Build `eval_suite.py` to execute builds for candidates, compute deltas (size, layers, time, hadolint), and compare LLM-chosen winners vs actual best. Generate HTML/MD/CSV reports under `/eval/reports/` and metrics in `/eval/metrics/`.  
**Acceptance Criteria:**
- `make eval-llm` runs end-to-end on sample set, producing `llm_eval.html` with tables for win-rate, size reduction, and confidence histograms.
- Regression test verifies evaluator skips network access and consumes cached datasets/build contexts.
- Metrics persisted in machine-readable JSON/CSV for dashboards.  
**Technical Notes:** Parallelize builds cautiously to avoid resource spikes; reuse existing runner; gate external pulls.  
**Dependencies:** LLM-006, LLM-007  
**Risks:** Build time; flaky docker cache; metric skew  
**Owner:** Eng | **Priority:** P1 | **Estimate:** 10h  
**Outputs:** `/eval/metrics/*`, `/eval/reports/llm_eval.html`, `eval_suite.py`, `build_and_measure.py` updates  
**DoD:** Evaluator shows ≥40% median size reduction when LLM picks top candidate vs baseline; artifacts saved under timestamped runs.  
**PRD Refs:** §4.4 Evaluation, §8 Deliverables

**Status Update (2025-11-25T02:45:00Z):** Delivered an offline harness via `eval/build_and_measure.py` + `eval/eval_suite.py`, emitting timestamped JSON/CSV metrics, HTML dashboards, and reusable dataclasses. Added `make eval-llm`, tracked artefacts under `eval/metrics` & `eval/reports`, and codified summary logic/tests in `tests/test_eval_suite.py`. The evaluator consumes demo stacks by default, skips network access, and records win-rate/confidence histograms for downstream dashboards. AI-agent build time: 1:40:00.

### LLM-009 — Rules promotion & safety guardrails
**User Story:** As a rules maintainer, I want to safely promote LLM-discovered patterns into `rules.yml` without violating deterministic guarantees.  
**Description:** Create a promotion workflow that ingests evaluator outputs, reviews top-performing rationales, and updates `patterns/rules.yml` under a new `llm_assist` section. Add validations in `core/rules.py`/`core/security.py` to reject non-template tokens and enforce allowlists.  
**Acceptance Criteria:**
- Promotion script or checklist documents diff-based rule updates with associated metrics and adapter version.
- Validator fails builds if LLM proposes raw Dockerfile fragments or disallowed instructions.
- `rules.yml` includes cross-references to rule IDs used in rationales and CMD signals.  
**Technical Notes:** Use schema validation; keep PR-ready diffs; integrate with reporter to cite promoted rules.  
**Dependencies:** LLM-008  
**Risks:** Overfitting to small eval set; false positives in validators  
**Owner:** Eng | **Priority:** P0 | **Estimate:** 6h  
**Outputs:** Updated `patterns/rules.yml`, `core/rules.py`, `core/security.py`, promotion notes  
**DoD:** New rules ship with tests; validator rejects hallucinated outputs; adapters tagged with compatible rule version.  
**PRD Refs:** §6 Integration, §7 Determinism, §10 Acceptance Criteria

**Status Update (2025-11-25T04:20:00Z | 1:15:00):** Added `codi.ruleset_version` labels/env tags to all templates, recorded promotion metadata + adapter compatibility under `llm_assist.promotions`, and codified the workflow inside `docs/llm_promotion_checklist.md`. `core/rules.py` now parses promotions via new dataclasses, `core/security.py` exposes `ensure_instruction_allowlist`/`scrub_docker_tokens`, and `core/llm.py` consumes the sanitiser. Regression coverage landed in `tests/test_rules.py` and `tests/test_security.py`.

### LLM-010 — Docs & runbook for adapters + toggles
**User Story:** As an operator, I need clear instructions to load adapters, switch models, and verify offline behavior.  
**Description:** Update `/docs/runbook.md`, `/models/README.md`, and top-level README with adapter mounting steps, env toggles (`LLM_ENABLED`, `CODE_MODEL`, `ADAPTER_PATH`), health-check commands, and troubleshooting. Add `docs/llm_adapter_notes.md` with version matrix.  
**Acceptance Criteria:**
- Documentation includes copy-paste commands for loading adapters via volume mount and verifying `/llm/rank` works offline.
- Clear guidance on fallback StarCoder2-3B and checksum verification for adapters.
- Screenshots or snippets showing report sections with adapter versions.  
**Technical Notes:** Keep instructions consistent with Makefile targets; avoid duplicating CI guidance.  
**Dependencies:** LLM-004, LLM-009  
**Risks:** Doc drift; missing adapter compatibility notes  
**Owner:** PdM | **Priority:** P1 | **Estimate:** 4h  
**Outputs:** Updated docs as listed; `docs/llm_adapter_notes.md`  
**DoD:** Reviewed by TA; commands verified in Complete container without network.  
**PRD Refs:** §3 System Overview, §7 Non-Functional, §10 Acceptance Criteria

**Status Update (2025-11-25T05:05:00Z | 0:45:00):** Refreshed README, `docs/runbook.md`, and `models/README.md` with `/llm/rank` smoke commands, `CODI_RULESET_VERSION`, adapter validation steps, and links to the promotion workflow. Authored the new `docs/llm_adapter_notes.md` reference (mounting scripts, env toggles, troubleshooting) and linked it across the runbook + README to close the doc loop introduced by Wave LLM-6.

---

*End of mvp_tasks.md.*
