# CODI Technology Stack

This document enumerates the technologies, libraries, and tooling that power CODI across CLI, API, containers, data pipeline, training, and release automation. Version ranges match `pyproject.toml` and container specifications unless stated otherwise.

## Programming Languages

| Layer | Language | Notes |
| --- | --- | --- |
| Core engine | Python 3.12 | Required for CLI/API modules. Official support targets 3.12. |
| Container scripting | Bash | Used for helper scripts (`docker/scripts/*.sh`). |
| Dashboard | JavaScript (ES6) + HTML/CSS | Static viewer at `docs/dashboard/`. |
| Templates | Jinja2 | Rules catalog templates in `patterns/rules.yml`. |
|
## Python Dependencies

### Runtime Dependencies (excerpt from `pyproject.toml`)

| Package | Purpose |
| --- | --- |
| `typer[all]>=0.12.3` | CLI framework with Rich integration. |
| `rich>=13.7.1` | Terminal rendering for CLI panels and progress bars. |
| `fastapi>=0.115.0` | REST API server with OpenAPI schemas. |
| `uvicorn[standard]>=0.30.0` | ASGI server for FastAPI deployments. |
| `pydantic>=2.9.0` | Data validation for API schemas and internal models. |
| `jinja2>=3.1.4` | Template engine used by the renderer. |
| `pyyaml>=6.0.2` | Parsing `patterns/rules.yml` and configuration files. |
| `docker>=7.1.0` | Future BuildKit integration and Docker client helpers. |
| `httpx>=0.27.0` | HTTP client with air-gap enforcement. |
| `python-dotenv>=1.0.1` | Optional `.env` file support for CLI/API. |

### Optional Extras

- **`dev` extra**: `black`, `ruff`, `pytest`, `pytest-cov`, `mypy`, `types-PyYAML`, `types-requests`.
- **`data` extra**: `boto3` for R2 sync utilities.
- **`training` extra**: `transformers`, `peft`, `bitsandbytes`, `datasets`, `accelerate`, `trl`, `tensorboard`.

## Tooling

| Category | Tool | Usage |
| --- | --- | --- |
| Linting | Ruff | `make lint` executes Ruff (checks + import sorting). |
| Formatting | Black | `make format` runs Black across the repo. |
| Type checking | mypy | Configured in `pyproject.toml`. |
| Testing | pytest | `make test` or `python -m pytest`. |
| Coverage | pytest-cov | Optional coverage reports via `--cov`. |
| Documentation | Markdown | All docs stored under `docs/` and `docs/deliverables/docs/`. |

## Containers

| Image | Base | Highlights |
| --- | --- | --- |
| `docker/Dockerfile.slim` | `python:3.12-slim` | Multi-stage (builder + runtime), installs CODI with `pip install .`, runs as non-root `codi` user, exposes port 8000. |
| `docker/Dockerfile.complete` | Slim image + llama.cpp build | Adds build-essential, git, curl, `libcurl4-openssl-dev`, compiles llama.cpp with CPU optimisations, includes adapter validation scripts, exposes ports 8000/8081. |

Both images honour environment variables documented in `SLIM_CONTAINER.md` and `COMPLETE_CONTAINER.md`. Build commands are available through the Makefile:

```bash
make build-slim
make build-complete
```

## Local LLM Runtime

| Component | Technology |
| --- | --- |
| Base model | Qwen2.5-Coder-1.5B (primary), StarCoder2-3B (fallback) |
| Adapter format | LoRA/PEFT (`adapter_model.safetensors`) |
| Runtime | llama.cpp (CPU, compiled during Complete build) |
| Client protocol | HTTP JSON via `LocalLLMServer`/`LocalLLMClient` |
| Adapter metadata | Stored under `/models/adapters/<id>/metadata.json` |

See `LLM_MODULE.md` for the full pipeline.

## Data Pipeline Stack

| Stage | Technology |
| --- | --- |
| Collection | Python scripts hitting GitHub REST API; optional Hadolint integration. |
| Storage | Local filesystem under `data/` + optional Cloudflare R2 via `boto3`. |
| Processing | Python scripts for standardisation, pair generation, and splitting. |
| Format | JSON / JSONL with reproducible manifests. |

Key scripts live under `data/` (e.g., `collect_github.py`, `label_smells.py`, `synth_pairs_from_rules.py`).

## Training Stack

- **Framework**: Hugging Face Transformers + PEFT + TRL.
- **Quantisation**: QLoRA (4-bit) via bitsandbytes.
- **Accelerator**: `accelerate` handles device placement; training works on single GPUs (>=8 GB VRAM) or CPU (slow).
- **Monitoring**: TensorBoard logging stored under `training/qwen15b_lora/logs`.
- **Notebooks**: `training/qwen15b_lora/train_colab.ipynb` for Colab workflows.
- **Packaging**: `create_colab_zip.py` bundles datasets and configs for remote execution.

## Runtime Services

| Service | Description |
| --- | --- |
| FastAPI (`api/server.py`) | Hosts `/analyze`, `/rewrite`, `/run`, `/report`, `/llm/*`, `/healthz`. |
| Local LLM server | HTTP server started by `docker/runtime_complete.py`, exposes `/healthz`, `/complete`, `/rank`. |
| Dashboard viewer | Static site served via any HTTP server (`python -m http.server --directory docs/dashboard 8001`). |

## Storage & Artefacts

- Runs stored on disk under `runs/` (configurable via `CODI_OUTPUT_ROOT`).
- Metadata stored as JSON (see `REFERENCE.md` for schemas).
- RAG embeddings stored in SQLite database `runs/_rag/index.sqlite3` using cosine similarity.
- Dashboard datasets stored as JSON (usually `docs/dashboard/data/*.json`).

## CI/CD & Release

| Component | Technology |
| --- | --- |
| Workflow engine | GitHub Actions (`.github/workflows/release-images.yml`). |
| Build tooling | Docker Buildx + QEMU for multi-arch builds. |
| Signing | cosign (keyless, OIDC). |
| SBOM generation | Anchore SBOM action (SPDX JSON). |
| Artifact storage | GitHub Actions artifacts for SBOMs + attestation files. |

Makefile targets `release-images` and `publish-images` wrap `docker/scripts/release_images.sh` to produce identical builds locally.

## Observability & Instrumentation

- CLI uses Rich tables for immediate feedback.
- FastAPI integrates with standard logging; `uvicorn` emits structured logs by default.
- Complete container logs adapter status, llama.cpp output, and health probes.
- `codi perf` writes JSON metrics for longitudinal tracking.

## Security Stack

- Outbound HTTP guard is implemented via `httpx` wrappers.
- Containers run non-root with `AIRGAP=true` by default.
- Policy enforcement lives in `core/security.py` and `patterns/rules.yml` allowlists.
- Adapter validation script computes checksums and verifies metadata before enabling LLM assist.

## Supported Platforms

- macOS 13+
- Ubuntu 22.04+
- Windows via WSL2 (for CLI; containers require Docker Desktop with WSL backend)
- Docker Engine 24+ with BuildKit enabled

## Versioning & Compatibility

- Python pinned to `>=3.12,<3.13`.
- Container base images updated periodically; refer to `docker/Dockerfile.*` for exact digests if necessary.
- Adapters specify compatibility via `patterns/rules.yml` `llm_assist` entries.
- Release versions follow semantic versioning (`vX.Y.Z`).

This stack description should be used in tandem with `ARCHITECTURE.md` for conceptual understanding and `CICD_RELEASE.md` for deployment practices.

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) for system diagrams and module relationships.
- [INSTALLATION.md](./INSTALLATION.md) and [CLI_GUIDE.md](./CLI_GUIDE.md) for hands-on setup.
- [CICD_RELEASE.md](./CICD_RELEASE.md) for build/publish automation details.
