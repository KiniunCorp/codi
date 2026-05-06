# CODI Installation & Setup Guide

This guide covers prerequisites, installation paths, environment configuration, and troubleshooting tips for running CODI locally or in CI.

## 1. Prerequisites

| Component | Requirement | Notes |
| --- | --- | --- |
| Python | 3.12.x | System Python or pyenv virtualenv. |
| pip / venv | Latest | `python3 -m venv` used by `make setup`. |
| Docker | 24+ with BuildKit | Required for container workflows. |
| Make | Optional | Simplifies scripted tasks. |
| Git | Latest stable | Needed to clone repositories and manage adapters. |

### Platform Notes
- **macOS**: Install Python 3.12 via `brew install python@3.12`. Docker Desktop 4.24+ includes BuildKit.
- **Ubuntu**: Use `apt-get install python3.12 python3.12-venv make docker.io` (enable BuildKit in `/etc/docker/daemon.json`).
- **Windows**: Use WSL2 with Ubuntu 22.04; install Docker Desktop with WSL integration; run CLI inside WSL.

## 2. Clone Repository

```bash
git clone <repository-url>
cd codi
```

## 3. Local CLI Setup

### 3.1 Create Virtual Environment

```bash
make setup
source .venv/bin/activate
```

`make setup` creates `.venv/`, upgrades `pip`, installs CODI in editable mode with dev dependencies, and prepares CLI entrypoint `codi`.

### 3.2 Verify Installation

```bash
codi --version
python -m pytest -q
```

### 3.3 Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `CODI_OUTPUT_ROOT` | Run artefact root | `runs/` |
| `RULES_PATH` | Alternate rules file | `patterns/rules.yml` |
| `AIRGAP` | Block outbound HTTP | `true` |
| `AIRGAP_ALLOWLIST` | Comma-separated hosts | _(empty)_ |
| `LLM_ENABLED` | Enable assist calls | `false` (Slim) |
| `LLM_ENDPOINT` | Remote LLM URL | `http://127.0.0.1:8081` |
| `CODE_MODEL` | Base model id | `qwen2.5-coder-1.5b` |
| `ADAPTER_PATH` | Adapter directory | `/models/adapters/qwen15b-lora-v0.1` |

Set them in your shell profile or prefix CLI commands:

```bash
export CODI_OUTPUT_ROOT="$HOME/codi-runs"
export AIRGAP_ALLOWLIST="internal.registry.local"
```

## 4. Running the CLI

### 4.1 End-to-End Optimisation

```bash
codi run demo/node
LATEST=$(ls -dt runs/* | head -n 1)
codi report "$LATEST"
```

### 4.2 Single Command (`codi all`)

```bash
codi all demo/python
```

### 4.3 Smoke Tests

```bash
python -m pytest tests/test_smoke.py
```

## 5. Container Workflows

### 5.1 Build Images

```bash
make build-slim
make build-complete
```

### 5.2 Run Slim Container (API)

```bash
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim
```

### 5.3 Run CLI Inside Slim Container

```bash
docker run --rm -v "$PWD:/work" codi:slim \
  codi all /work/demo/java --dry-run
```

### 5.4 Run Complete Container (LLM enabled)

```bash
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$HOME/.codi-models/adapters:/models/adapters" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

Mount `/models` with adapters and weights before enabling LLM services. Use `docker/scripts/verify_adapter.py` to validate adapters.

## 6. IDE Integration

- **VS Code**: Configure Python interpreter as `.venv/bin/python`; enable `python.testing.pytestEnabled=true` and set `python.testing.pytestArgs=["tests"]`.
- **PyCharm**: Point to `.venv/bin/python`; mark `core`, `cli`, and `api` as source roots.
- **EditorConfig**: Ensure Black formatting (line length 100) and Ruff linting run on save.

## 7. Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `ModuleNotFoundError: core` | Activate `.venv` or run `make setup` to install editable package. |
| `codi: command not found` | Ensure `.venv/bin` is on PATH or run `python -m cli.main`. |
| Docker build fails due to permissions | Use `sudo usermod -aG docker $USER` (Linux) and re-login. |
| Adapter validation fails | Check that `adapter_config.json` and `adapter_model.safetensors` exist and match metadata checksums. |
| `AIRGAP` blocking API tests | Set `AIRGAP_ALLOWLIST="testserver"` when running FastAPI test client. |
| CLI cannot write to `runs/` | Set `CODI_OUTPUT_ROOT` to a directory where the user has write permissions. |

## 8. Maintenance Commands

```bash
make clean           # Remove venv, caches, runs/
make lint            # Ruff + Black (check mode)
make format          # Ruff imports + Black formatter
make test            # Full pytest suite
make data-prepare    # Run data pipeline (incremental)
```

## 9. Next Steps

- For container-specific options, see `SLIM_CONTAINER.md` and `COMPLETE_CONTAINER.md`.
- For API integrations, read `API_GUIDE.md`.
- To explore the LLM pipeline, see `LLM_MODULE.md`.

## Related Documentation

- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for command and environment cheatsheets.
- [SLIM_CONTAINER.md](./SLIM_CONTAINER.md) and [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) for container usage.
- [OPERATIONS.md](./OPERATIONS.md) for day-2 procedures after installation.
