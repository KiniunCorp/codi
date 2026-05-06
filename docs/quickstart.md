# CODI Slim Quickstart

Welcome to the **CODI Slim** experience. This guide walks you through running the
rules-first optimisation pipeline locally and inside the `codi:slim` container.
All commands are copy‑paste ready and assume you are in the repository root.

---

## Prerequisites

- Python **3.12** (for direct CLI usage)
- Docker **24+** with BuildKit enabled (for the Slim image)
- `make` (optional but recommended)

Verify your environment:

```bash
python3 --version
docker version
```

---

## 1. Local CLI Workflow (rules-only)

### Install dependencies

```bash
make setup       # creates a virtualenv and installs python deps
source .venv/bin/activate
```

### Run the optimiser end-to-end

```bash
# Analyse, render candidates, estimate metrics, and persist artefacts
codi run demo/node

# Generate human-readable artefacts (Markdown + HTML)
codi report runs/*/  # point at the latest run directory

# Or execute everything in one go
codi all demo/node
```

Outputs land under `runs/<timestamp>-<stack>-<label>/` with inputs, candidates,
metrics, and reports in dedicated subdirectories.

### Inspect RAG insights

```bash
LATEST=$(ls -dt runs/* | head -n 1)
cat "$LATEST/metadata/rag.json" | jq
```

The `rag.json` file surfaces similar historical runs retrieved from the new
SQLite-backed lightweight memory (`runs/_rag/index.sqlite3`).

---

## 2. Smoke validation

```bash
# Executes deterministic smoke checks across Node, Python, and Java demos
python3 -m pytest tests/test_smoke.py
```

> ℹ️ If `pytest` is not yet installed, run `pip install pytest` inside your
> virtual environment or `make test` to install + execute the suite.

---

## 3. Containerised Quickstart (`codi:slim`)

Build the Slim image (multi-stage Dockerfile included):

```bash
make build-slim
# or
docker build -f docker/Dockerfile.slim -t codi:slim .
```

### Serve the FastAPI endpoints

```bash
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim

# Health-check
curl http://localhost:8000/healthz
```

### Run CLI commands via the container

```bash
docker run --rm -v "$PWD:/work" codi:slim \
  codi all /work/demo/python --dry-run

# Inspect results generated on the host
ls runs/
```

### Capture quickstart docs artefacts

Every container invocation writes to `/work/runs/`. Mount your own project
directory instead of `$PWD` to optimise real workloads.

---

## 4. Next steps

- Review generated artefacts under `runs/<timestamp>/metadata/`
- Explore retrieved matches in `rag.json` to understand prior optimisations
- Share reports (`reports/report.md` / `report.html`) with your team

For deeper architecture details and roadmap context, see the
[`docs/codi_mvp_prd.md`](codi_mvp_prd.md) and
[`docs/codi_mvp_tasks.md`](codi_mvp_tasks.md).

Happy slimming! 🐳
