# 🧠 CODI (Container Dietician) — MVP PRD (Rules-First + Local LLM Container)
**Version:** 2.1 (MVP scope + LLM Enhancement)  
**Type:** Product Requirements Document (PRD)  
**Audience:** AI coding agents, infra/DevOps engineers, technical PM  
**Author:** Gus & ChatGPT 
**Date:** 2025-11-24

---

## 0) Scope Changes (MVP)
**In-scope (now):**
- Core value-chain end to end with **3 stacks**: **Node/Next.js**, **Python/FastAPI**, **Java/Spring Boot**.
- **Two deliverables**:
  1) **Slim container**: CODI core (CLI + API) using **rules.yml** only (no external LLM).  
  2) **Complete container**: Slim container **+ local LLM runtime** (offline) + lightweight RAG memory.
- **No external LLM calls**; **no n8n** and **no CI/CD** automations in this MVP (kept for later).

**Out-of-scope (later):**
- External LLM comparison, n8n workflows, GitHub Actions bots, security scanners, LoRA/SFT training jobs.

---

## 1) Executive Summary
**CODI (Container Dietician)** is a **rules-first, AI-assisted** tool that **analyzes**, **rewrites**, and **benchmarks** Dockerfiles.  
The MVP ships **two containers**:  
- a **Slim** container with deterministic **rules-based** optimization (CLI + API), and  
- a **Complete** container that bundles a **local, offline LLM** (7B class, quantized) to enhance **analysis, rationale, and candidate selection**, while final Dockerfiles are still **rendered from templates** in `patterns/rules.yml` for safety and reproducibility.

The CODI core delivers the full value chain: **Analyze → Rewrite (1–2 candidates) → Build & Measure → Report (MD/HTML)** across the **three MVP stacks**.

**MVP+ Extensions:** CMD/ENTRYPOINT analysis and optimization capabilities that detect runtime anti-patterns (shell-form usage, runtime package installations) and deterministically promote them to build stages while converting to exec-form for improved signal handling and security.

---

## 2) Product Goals & Success Metrics
| Goal | Description | KPI / Target |
|------|-------------|--------------|
| Automated optimization | Produce smaller, faster images without breaking behavior | ≥ 40% median size reduction across MVP stacks |
| Deterministic safety | Template-rendered Dockerfiles with policy checks | 100% syntactically valid candidates |
| Explainability | Human-friendly reports with rationale + diffs | Report generated on every run |
| Local-first privacy | All analysis runs **offline** in Complete container | 0 outbound calls by default |
| Learning loop | Use run history (RAG) to improve suggestions | Higher acceptance rate of candidates over time |
| CMD/ENTRYPOINT optimization (MVP+) | Detect and fix runtime anti-patterns in startup commands | 100% shell-form → exec-form conversion; runtime installs promoted to build |

---

## 3) System Overview (MVP)

    Dockerfile + Context
          |
          v
    +---------------------+
    |   CODI Core (Py)    |
    |  - analyze (parse)  |
    |  - rewrite (rules)  |
    |  - run (metrics)    |
    |  - report (MD/HTML) |
    +---------------------+
       ^             |
       | (Complete)  | artifacts (candidates, metrics, report)
       |             v
    +---------------------+
    |  Local LLM Server   |
    |  - code instruct    |
    |  - RAG over runs    |
    |  - rationale assist |
    +---------------------+

**Deliverable A — Slim container:** CODI Core only (rules-based).  
**Deliverable B — Complete container:** Slim + local LLM runtime (offline) + small vector store.

### LLM Integration (Complete container)

    Analyzer + Rules candidates
            |
            v
    +---------------------+
    | Local LLM Module    |
    | - model: Qwen2.5-   |
    |   Coder-1.5B (Q4)   |
    | - adapter: /models/ |
    |   adapters/qwen15b- |
    |   lora-v0.1         |
    | - runtime: llama.cpp|
    |   or Ollama (CPU)   |
    +---------------------+
            |
            v
    Ranking + rationale JSON
            |
            v
    Runner + Reporter (select best, build, emit HTML/MD)

**Constraints:**
- **Offline-first:** All inference and adapter loads run without network; adapters mounted from `/models/adapters/`.
- **Rules-first:** LLM outputs are **rankings + rationales** only; Dockerfiles remain template-rendered from `patterns/rules.yml`.
- **Deterministic validation:** A guardrail rejects any output that contains raw Dockerfile syntax outside allowed placeholders.
- **Adapter lineage:** Responses include `adapter_version` and `CODE_MODEL` for traceability in reports and logs.

**New artifacts:** `runs/<ts>/llm_metrics.json` (confidence + ranking), `runs/<ts>/report.*` updated with LLM sections.

---

## 4) Architecture & Components

### 4.1 Codebase layout

    /core
      parse.py      # tolerant Dockerfile parsing & features
      detect.py     # stack detection (node/python/java)
      rules.py      # load/validate rules.yml; select templates
      render.py     # Jinja2/template render; inline rationale comments
      build.py      # BuildKit builds; image inspect; timings
      report.py     # Markdown + HTML report generator
      store.py      # write runs/<ts>/{analysis.json, run.json, report.md/html}
    /cli
      main.py       # Typer/Rich-based CLI: codi analyze|rewrite|run|report|all
    /api
      server.py     # FastAPI: /analyze /rewrite /run /report
    /patterns
      rules.yml     # SoT templates for Node/Next, FastAPI, Spring Boot
    /models
      README.md     # how to mount/import local models
    /docker
      Dockerfile.slim     # Slim container (default: API CMD)
      Dockerfile.complete # Complete container (LLM + CODI; API CMD)
    /docs
      dashboard.md  # how to generate a simple dashboard from runs

### 4.2 Runtime modes
- **CLI (local)**: `codi all -f Dockerfile -C . --out runs/`  
- **API (local service)**: `codi serve --host 0.0.0.0 --port 8000`  
- **Container (Slim)**: `docker run -v $PWD:/work codi:slim codi all -f /work/Dockerfile -C /work`  
- **Container (Complete)**: same as Slim, with local LLM available at `http://localhost:11434` (or internal socket).

### 4.3 Data artifacts
- `runs/<timestamp>/analysis.json` — detector/summary features  
- `runs/<timestamp>/candidate1.Dockerfile` (and 2)  
- `runs/<timestamp>/run.json` — build metrics (size bytes, layers, duration)  
- `runs/<timestamp>/report.md` & `report.html`

### 4.4 CMD/ENTRYPOINT Analysis Flow (MVP+)

```
    Dockerfile Input
          |
          v
    core/parse.py
          |
          v
    core/cmd_parser.py ──────> Normalize shell-form vs exec-form
          |                    Extract CMD/ENTRYPOINT instructions
          |                    Capture script references
          v
    core/script_analyzer.py ─> Static analysis of referenced scripts
          |                    Detect runtime package installs
          |                    Flag migrations, daemons
          v
    core/detect.py ──────────> Stack-specific heuristics
          |                    (npm start, uvicorn, java -jar)
          v
    patterns/rules.yml ──────> cmd_rewrites section
          |                    Match analyzer flags
          |                    Select rewrite templates
          v
    core/render.py ──────────> Apply CMD/ENTRYPOINT optimizations
          |                    Promote runtime work to build stages
          |                    Convert shell-form to exec-form
          |                    Inject rationale comments
          v
    Optimized Dockerfile
    (with promoted installs + exec-form CMD)
```

**Key Features:**
- **Deterministic parsing:** Normalizes shell-form (`CMD npm start`) and exec-form (`CMD ["node", "server.js"]`) into structured metadata.
- **Script inspection:** Statically analyzes referenced shell scripts (e.g., `start.sh`, `entrypoint.sh`) to detect runtime package installations that should move to build stages.
- **Rules-first rewrites:** Uses `patterns/rules.yml` `cmd_rewrites` section to apply stack-specific optimizations (Node, Python, Java).
- **Safety:** Operates on static text only; respects air-gapped operation; no script execution.
- **Transparency:** Emits `cmd_analysis` metadata in reports and API responses with before/after comparisons.

---

## 5) Functional Requirements

### 5.1 Inputs
| Name | Type | Description |
|------|------|-------------|
| `dockerfile` | text/path | Dockerfile content or path |
| `context_dir` | path | Build context directory |
| `stack_hint` | string | Optional override: `node|python|java` |
| `dry_run` | bool | Skip real builds (planning mode) |

### 5.2 CLI Commands (must-have)
- `codi analyze -f <Dockerfile> -C <context>` → JSON to stdout + save to runs/  
- `codi rewrite -f <Dockerfile> -C <context> [--stack <hint>]` → 1–2 candidates + rationale comments  
- `codi run -f <Dockerfile> -C <context> [--candidates <paths>] [--real]` → build metrics  
- `codi report --in runs/<ts>` → report.md/html  
- `codi all -f <Dockerfile> -C <context> [--real]` → full pipeline

### 5.3 API Endpoints (FastAPI; same contracts as CLI sequence)
- `POST /analyze` → `{stack, summary, stages}`
- `POST /rewrite` → `{stack, candidates:[{name,rationale,dockerfile}]}`
- `POST /run` → `{run_id, results:[{kind, size_bytes, layers, build_seconds}]}`
- `POST /report` → `{markdown, html}`
- `POST /llm/rank` → `{ranking:[{candidate,score}], rationale, adapter_version, llm_metrics}`
- `POST /llm/explain` → `{rationale, summary, adapter_version}`

### 5.4 Rules engine (SoT)
- Source: `/patterns/rules.yml`  
- Selection: by detected stack + simple predicates (e.g., pkg manager present)  
- Rendering: Jinja2 with context variables (version pins, ports, paths)  
- Enforcement: final Dockerfiles must be template-rendered; LLM may propose **bounded substitutions** only

#### 5.4.1 CMD Rewrites Schema (MVP+)
The `patterns/rules.yml` file extends with a new `cmd_rewrites` section that enables deterministic CMD/ENTRYPOINT optimizations:

```yaml
cmd_rewrites:
  node:
    - match:
        form: shell
        installs_packages: true
      preferred_form: exec
      builder_promotions:
        - "RUN npm ci --only=production"
      runtime_cmd: '["node", "server.js"]'
      rationale_template: "Moved runtime npm install to builder stage; switched to exec-form for better signal handling"
  
  python:
    - match:
        form: shell
        command_contains: "pip install"
      preferred_form: exec
      builder_promotions:
        - "RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels"
      runtime_cmd: '["uvicorn", "app.main:app", "--host", "0.0.0.0"]'
      rationale_template: "Promoted pip install to build stage using wheel pattern"
  
  java:
    - match:
        form: shell
      preferred_form: exec
      runtime_cmd: '["java", "-jar", "app.jar"]'
      rationale_template: "Converted to exec-form for proper signal handling"
```

**Schema Fields:**
- `match`: Conditions that trigger this rewrite (form, flags, command patterns)
- `preferred_form`: Target form (`exec` or `shell`)
- `builder_promotions`: List of instructions to add to builder stage
- `post_copy_steps`: Instructions to run after COPY in runtime stage
- `runtime_cmd`: The optimized CMD/ENTRYPOINT instruction
- `rationale_template`: Human-readable explanation for reports

### 5.5 CMD/ENTRYPOINT Analysis & Optimization (MVP+)
- **Input:** Dockerfile with CMD and/or ENTRYPOINT instructions
- **Output:** Structured `cmd_analysis` object in `analysis.json` and enriched candidate Dockerfiles
- **Features:**
  - Normalizes shell-form vs exec-form syntax
  - Detects references to external scripts (`start.sh`, `entrypoint.sh`)
  - Flags runtime package installations that should move to build stages
  - Applies stack-specific rewrites from `cmd_rewrites` rules
  - Preserves environment variables and working directory context
- **Safety:** Static analysis only; no script execution; respects security gates

### 5.6 LLM Ranking & Explanation (Complete)
- **Purpose:** Let the local small model **rank rule-rendered candidates** and produce **rationales** without generating Dockerfiles.
- **Inputs:** Analyzer payload (`analysis.json`), candidate Dockerfiles, optional build metrics, RAG snippets from prior runs.
- **Outputs:**
  - `ranking`: ordered list of candidate IDs with confidence scores
  - `rationale`: text referencing rule IDs and CMD signals
  - `adapter_version`: e.g., `qwen15b-lora-v0.1`
  - `llm_metrics.json`: per-candidate accuracy/confidence emitted to `runs/<ts>/`
- **Endpoints/CLI:** `/llm/rank`, `/llm/explain`, `codi llm rank`, `codi llm explain`.
- **Safety:** Validation rejects outputs containing Dockerfile syntax outside placeholders; `LLM_ENABLED=false` bypasses calls.
- **Acceptance Criteria:**
  1. When 2+ candidates exist, ranking returns deterministic ordering across repeated runs (same seed).
  2. Rationales cite rule keys (from `patterns/rules.yml`) and CMD/ENTRYPOINT flags.
  3. Reports show adapter version + ranking table; disabling LLM removes the section without breaking runs.
  4. Inference runs CPU-only in <3s median for 512-token prompts (Complete container).

---

## 6) MVP Stacks & Rules (authoritative examples)

### 6.1 Node/Next.js
- **Builder**: `node:20-slim`; `npm ci` with cache; `npm run build` (standalone)  
- **Runtime**: `node:20-alpine`; copy `.next/standalone`, `.next/static`, `public`  
- **Env/Policy**: `NODE_ENV=production`; non-root user; `.dockerignore` guidance

### 6.2 Python/FastAPI
- **Builder**: `python:3.12-slim`; `apt-get` minimal; `pip wheel -r requirements.txt`  
- **Runtime**: `python:3.12-slim`; `pip install --no-cache-dir /wheels/*`; `uvicorn` entrypoint  
- **Env/Policy**: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`; non-root

### 6.3 Java/Spring Boot
- **Builder**: `maven:3.9-eclipse-temurin-21`; cache `.m2`; package with `-DskipTests`  
- **Runtime**: `eclipse-temurin:21-jre` (or `jlink` later); copy `*.jar`; `java -jar app.jar`  
- **Policy**: non-root; pinned base tags

---

## 7) Local LLM Integration (Complete container)

### 7.1 Purpose
- Improve **analysis explanations**, **candidate ranking**, and **rule discovery** while preserving rules-first determinism.
- Run fully **offline** on CPU inside the Complete container; no outbound calls.

### 7.2 Model runtime & adapters
- **Base model:** Qwen2.5-Coder-1.5B (quantized 4-bit) with fallback **StarCoder2-3B**.
- **Serving:** llama.cpp or Ollama launched inside Complete; endpoints exposed on localhost only.
- **Adapters:** LoRA artifacts under `/models/adapters/qwen15b-lora-v0.1` (metadata + checksums). Adapter version reported in logs, API, and reports.
- **Config env:** `CODE_MODEL`, `ADAPTER_PATH`, `LLM_ENABLED`, `LLM_ENDPOINT`, `AIRGAP`.

### 7.3 Data pipeline & training (QLoRA)
- **Collection:** `collect_github.py`, `extract_cmd_scripts.py`, `label_smells.py` write raw sets to `/data/raw/` with manifests.
- **Curation:** `standardize.py`, `synth_pairs_from_rules.py`, `split_dataset.py` emit pairs and splits under `/data/curated/`, `/data/pairs/`, `/data/splits/`.
- **Training:** `/training/qwen15b_lora/config.yaml` documents QLoRA hyperparameters (seq len 4k, 2–3 epochs, grad-accum 16, Q/K/V/O + MLP targets). Outputs adapters (<400 MB) and `metadata.json`.
- **Packaging:** Export GGUF + PEFT weights; checksum and tag adapters for compatibility with `rules.yml` version.

### 7.4 Inference flow (Complete)
```
Analyzer + rules candidates + metrics
          |
          v
   core/llm.py (prompts, validation)
          |
          v
  llama.cpp/Ollama (Qwen2.5-Coder-1.5B + LoRA)
          |
          v
 ranking + rationale + llm_metrics.json
          |
          v
 reporter/render (inject rationale comments, tables)
```
- Validator strips Dockerfile tokens and enforces placeholders only.
- Inference target: **<3s median** for 512-token prompts on CPU; batching disabled to keep latency predictable.

### 7.5 Contracts (Complete)
- `LLM_RANK(candidates, analysis, metrics)` → `{ranking:[{candidate,score}], rationale, adapter_version, llm_metrics}`.
- `LLM_EXPLAIN(analysis)` → `{rationale, summary, adapter_version}`.
- Responses are persisted to `runs/<ts>/llm_metrics.json` and surfaced in reports.

### 7.6 RAG memory (optional)
- Store compact per-run facts (features, rules chosen, metrics) in SQLite/Chroma under `/runs/`.
- Retrieval augment prompts but remains **read-only**; no external data pulls.

---

## 8) Non-Functional Requirements
| Category | Requirement |
|----------|-------------|
| Performance | Analysis ≤ 3s (no build); LLM inference <3s median on CPU; Full run ≤ 5m per stack |
| Portability | Linux/macOS for CLI; containers run CPU-only |
| Privacy | Default **air-gapped**; no external calls or model downloads at runtime |
| Security | BuildKit; non-root; block risky Dockerfile patterns; adapter checksums verified before load |
| Determinism | Candidates generated from templates; LLM only ranks/explains; reproducible outputs under fixed seed |
| Explainability | Report must include "rules applied", CMD analysis, and LLM rationale + adapter version |
| Observability | All runs saved under `runs/<timestamp>/`; `llm_metrics.json` persisted for audits |

---

## 9) Security & Policy Gates
- **Base image allowlist** (slim/alpine/temurin-jre), pinned tags.  
- Refuse **`ADD http(s)://`**, suspicious `--privileged`, or `sudo`.  
- Prefer **rootless** builds; if not, least privilege.  
- **Airgap** default; explicit env var to enable outbound model pulls.

---

## 10) Packaging & Delivery

### 10.1 Slim container
- Multi-stage build; includes Python runtime + CODI CLI/API + rules.yml.  
- Default CMD: start API; CLI available via `docker run … codi all …`.  
- No model runtime included.

### 10.2 Complete container
- Based on Slim + model server + small vector DB (SQLite/Chroma).  
- Model weights: allow **bind-mount** or **on-first-run pull** from an internal model registry.  
- Default CMD: start API (exposes `/analyze`, `/rewrite`, `/run`, `/report`), background LLM runtime.

### 10.3 Configuration (env)
- `RULES_PATH=/opt/codi/patterns/rules.yml`
- `AIRGAP=true|false` (default `true`)
- `LLM_ENABLED=true|false` (Slim sets `false`, Complete sets `true`)
- `LLM_ENDPOINT=http://localhost:11434/v1`
- `CODE_MODEL=qwen2.5-coder-1.5b` (default) | `starcoder2-3b` (fallback)
- `ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1`
- `EMBED_MODEL=<local-embed>` / `CODE_MODEL=<local-code>`

---

## 11) Data Schemas (abridged)

### 11.1 `/analyze` response

    {
      "stack": "node",
      "summary": {
        "stage_count": 2,
        "bases": ["node:20-slim","node:20-alpine"],
        "uses_pkg_manager": true,
        "runs_as_root": false,
        "has_cache_mount": true
      },
      "stages": [{"from":"node:20-slim","name":"builder"}, {"from":"node:20-alpine"}],
      "cmd_analysis": {
        "form": "shell",
        "original": "CMD npm start",
        "parsed": {
          "command": "npm start",
          "shell": "/bin/sh -c"
        },
        "flags": {
          "uses_shell_form": true,
          "installs_packages": false,
          "runs_migrations": false,
          "references_script": false
        },
        "recommendations": [
          "Convert to exec-form for better signal handling",
          "Consider using direct node invocation instead of npm start"
        ]
      }
    }

**MVP+ Extension:** The `cmd_analysis` object is added when CMD/ENTRYPOINT instructions are present:
- `form`: `"shell"` or `"exec"`
- `original`: The original instruction as written
- `parsed`: Normalized representation with command and arguments
- `flags`: Boolean indicators for detected patterns
- `script_ref`: If present, details about referenced external scripts
- `recommendations`: List of suggested optimizations

### 11.2 `/rewrite` response

    {
      "stack": "node",
      "candidates": [
        {"name":"multi_stage_slim","rationale":"...","dockerfile":"FROM node:20-slim AS builder ..."},
        {"name":"alpine_runtime_standalone","rationale":"...","dockerfile":"FROM node:20-alpine ..."}
      ]
    }

### 11.3 `/run` response

    {
      "run_id": "2025-10-29T12:34:56Z",
      "results": [
        {"kind":"original","size_bytes":540000000,"layers":12,"build_seconds":91},
        {"kind":"candidate_1","size_bytes":190000000,"layers":8,"build_seconds":55}
      ]
    }

### 11.4 `/report` response

    { "markdown":"...# CODI Report ...", "html":"<html>...</html>" }

### 11.5 `/llm/rank` response (Complete)

    {
      "ranking": [{"candidate":"candidate_1","score":0.64},{"candidate":"candidate_2","score":0.36}],
      "rationale": "Candidate_1 promotes runtime installs and uses exec-form CMD.",
      "adapter_version": "qwen15b-lora-v0.1",
      "llm_metrics": {"win_rate":0.72,"mean_confidence":0.58}
    }

### 11.6 `/llm/explain` response (Complete)

    {
      "summary": "Promoted apt-get install to builder and switched CMD to exec-form.",
      "rationale": "Analyzer flagged runtime installs; builder promotions added for faster startup.",
      "adapter_version": "qwen15b-lora-v0.1"
    }

---

## 12) Epics & Milestones

### Epic A — **CODI Core (rules-only)**  *(Slim container foundation)*
- A1: Repo skeleton & Makefile; CLI commands `analyze|rewrite|run|report|all`  
- A2: Parser + detector for 3 stacks (node/python/java)  
- A3: `patterns/rules.yml` seed for 3 stacks (see §6); Jinja2 rendering  
- A4: Build runner (BuildKit), metrics capture, safety checks  
- A5: Reporter (MD/HTML) with rationale + diffs + metrics  
- A6: Slim container packaging (API as default CMD)

**Exit criteria:** Full pipeline works locally with **3 sample apps**; artifacts saved under `runs/`.

### Epic B — **Local LLM enhancement**  *(Complete container extras)*
- B1: Embed a local LLM server (Ollama or llama.cpp) + embed model  
- B2: RAG store on runs/ (SQLite/Chroma); retrieval helper  
- B3: LLM-assist functions (summary, tie-breaker, rationale polish) with **strict boundaries**  
- B4: Complete container packaging; offline, airgap by default

**Exit criteria:** LLM-assisted rationales improve clarity; still deterministic templates for final Dockerfiles.

### Epic C — **Unified Complete Container**
- C1: Integrate Slim + LLM layers; env-driven toggles (`LLM_ENABLED`, `AIRGAP`)  
- C2: Smoke tests on all 3 stacks; performance sanity on CPU-only  
- C3: Docs (`models/README.md`, runbook) and example runs

**Exit criteria:** One image runs both API & CLI; local-only by default; documented install & usage.

---

## 13) Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM latency on CPU | Slower responses | Keep prompts short; cache embeddings; most time spent on Docker builds anyway |
| Unsafe suggestions | Broken images | Templates as SoT; validation gate; rules-only final render |
| Build variability | Flaky demos | Provide stable sample apps; `--dry_run` mode for quick checks |
| Model size | Large image | Prefer bind-mounted models; publish a “slim + model mount” pattern |
| Time constraints | Incomplete polish | Focus on 3 stacks; ship Slim first, then Complete |

---

## 14) Acceptance Tests (MVP)
1. **Rules-only run (Slim)** on each stack → report shows ≥30% size reduction and fewer layers.
2. **Complete run (LLM-enabled)** → same metrics + clearer rationale section (LLM summary present).
3. **Airgap check** → Complete container functions with `AIRGAP=true`, no outbound HTTP.
4. **Determinism** → re-running on same inputs produces identical candidate Dockerfiles.
5. **Security gates** → refuse Dockerfiles with disallowed instructions.
6. **LLM endpoints** → `/llm/rank` and `/llm/explain` return ranking + rationale with `adapter_version` when `LLM_ENABLED=true`; they return bypass notice when disabled.
7. **Offline inference** → Complete container loads adapters from `/models/adapters/` and serves rankings with no network egress; inference <3s median for sample prompts.
8. **Report integration** → `report.md/html` include "LLM Rationale & Ranking" with candidate ordering, adapter version, and llm_metrics table.
9. **Rules promotion** → When evaluator marks a candidate as best, updated `patterns/rules.yml` `llm_assist` entries pass validation and appear in subsequent runs.
10. **Adapter integrity** → Corrupted adapter file (bad checksum) is rejected and logged; fallback model selected only when explicitly configured.

### 14.1 CMD/ENTRYPOINT Acceptance Tests (MVP+)
11. **Shell-form detection** → Given `CMD npm start`, analyzer correctly identifies `form: "shell"` and emits `uses_shell_form: true`.
12. **Exec-form detection** → Given `CMD ["node", "server.js"]`, analyzer identifies `form: "exec"` and preserves exact arguments.
13. **Runtime install detection** → Given a Dockerfile where CMD references `start.sh` that contains `apt-get install`, analyzer flags `installs_packages: true` and emits warning.
14. **Script promotion** → When runtime installs are detected, rendered candidates move package installations to builder stage with rationale comment.
15. **Exec-form conversion** → Shell-form CMD/ENTRYPOINT in original is converted to exec-form in candidates with signal handling rationale.
16. **Missing script handling** → If CMD references a script not present in context, analyzer adds `missing_script` warning but continues without failure.
17. **Stack-specific rewrites** → Node/Python/Java demos each trigger appropriate `cmd_rewrites` rules based on detected stack and flags.
18. **Report transparency** → Reports include "CMD/ENTRYPOINT Analysis" section with before/after comparison, applied rules, and estimated impact.

---

## 15) Handover Notes (for agents/engineers)
- Prioritize **Slim** deliverable first; it's the foundation for **Complete**.  
- Keep `rules.yml` small and crisp; we'll expand post-MVP.  
- Write clean interfaces so future n8n/CI integrate without refactor.  
- Document how to mount models internally (bind volume) vs staging pulls.

### 15.1 CMD/ENTRYPOINT Implementation Notes (MVP+)
- **Modularity:** CMD parser (`core/cmd_parser.py`) and script analyzer (`core/script_analyzer.py`) are separate modules that integrate with existing `parse.py` and `detect.py` without breaking changes.
- **Static analysis only:** Never execute referenced scripts; analyze as plain text with regex/heuristics.
- **Rules-first:** All CMD rewrites come from `patterns/rules.yml`; no free-form generation.
- **Backward compatibility:** Ensure all existing tests pass; CMD analysis is additive (returns empty/null if no CMD/ENTRYPOINT present).
- **Test fixtures:** Create `tests/fixtures/cmd_scripts/` with sample shell scripts for unit testing script analysis.
- **Incremental rollout:** CMD features are opt-in via analyzer detection; won't affect Dockerfiles without CMD/ENTRYPOINT.

---

## 16) Quickstart (after build)
- **Slim container (rules-only):**  
  `docker run -v $PWD:/work codi:slim codi all -f /work/Dockerfile -C /work --out /work/runs`  
- **Complete container (with local LLM):**  
  `docker run -v $PWD:/work -v /models:/models -e LLM_ENABLED=true -e AIRGAP=true codi:complete codi all -f /work/Dockerfile -C /work --out /work/runs`

---

## 17) Roadmap (post-MVP hints)
- External LLM comparison mode; CI/GitHub Action integration; n8n workflow.  
- Policy packs (org rules), security scanners (Trivy), golden-set gates.  
- Optional LoRA refresh using approved diffs; PR bot for `rules.yml` updates.
