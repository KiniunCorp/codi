# CODI Quick Reference

Use this cheat sheet for daily operations. All commands assume the repository root unless noted.

## CLI Commands

| Command | Description |
| --- | --- |
| `codi analyze <path>` | Parse Dockerfile and output analysis summary. |
| `codi rewrite <path>` | Generate candidate Dockerfiles using templates. |
| `codi run <path>` | Full pipeline (analyze → rewrite → build metrics → store artefacts). |
| `codi report <run_dir>` | Produce Markdown + HTML reports for an existing run. |
| `codi all <path>` | Convenience wrapper for `run` followed by `report`. |
| `codi serve` | Start FastAPI server (defaults: `127.0.0.1:8000`). |
| `codi dashboard --runs <root> --export-json <file>` | Build dashboard dataset. |
| `codi perf --out <dir>` | Run CPU performance sanity suite. |
| `codi llm rank <path>` | Execute ranking pipeline (Complete deployments). |
| `codi llm explain <path>` | Request LLM explanations for rendered candidates. |

## Frequent Command Patterns

```bash
# Run optimisation and open latest HTML report
codi all demo/node
open $(ls -dt runs/* | head -n 1)/reports/report.html

# Generate report for specific run
codi report runs/20251126T174725Z-python-python

# Launch API for integrations
env AIRGAP_ALLOWLIST="testserver" codi serve --host 0.0.0.0 --port 8000

# Aggregate demo runs into dashboard dataset
codi dashboard --runs docs/examples/dashboard --export-json docs/dashboard/data/sample_runs.json --relative-to docs/dashboard
```

## Environment Variables

| Variable | Default | Effect |
| --- | --- | --- |
| `CODI_OUTPUT_ROOT` | `runs/` | Base directory for run artefacts. |
| `RULES_PATH` | `patterns/rules.yml` | Override rules catalog. |
| `AIRGAP` | `true` | Enable outbound network blocking. |
| `AIRGAP_ALLOWLIST` | _(empty)_ | Comma-separated hostnames allowed when air-gapped. |
| `LLM_ENABLED` | `false` (Slim) / `true` (Complete) | Toggle LLM assist calls. |
| `LLM_ENDPOINT` | `http://127.0.0.1:8081` | Target local or remote LLM service. |
| `CODE_MODEL` | `qwen2.5-coder-1.5b` | Base model identifier for telemetry. |
| `ADAPTER_PATH` | `/models/adapters/qwen15b-lora-v0.1` | Adapter directory path. |
| `MODEL_MOUNT_PATH` | `/models` | Base path for weights/adapters (Complete container). |
| `LLAMA_CPP_THREADS` | `4` | CPU threads for llama.cpp runtime. |

## Make Targets

| Target | Description |
| --- | --- |
| `make setup` | Create `.venv`, install dependencies. |
| `make lint` | Run Ruff + Black (check mode). |
| `make format` | Apply Ruff import fixes + Black formatting. |
| `make test` | Execute entire pytest suite. |
| `make build-slim` | Build Slim container image. |
| `make build-complete` | Build Complete container image. |
| `make run-slim` | Run Slim API container (`docker run ...`). |
| `make run-slim-cli` | Start interactive shell inside Slim container. |
| `make test-slim` | Smoke test Slim container using demo project. |
| `make clean` | Remove venv, caches, and `runs/`. |
| `make data-collect` | Collect Dockerfiles via GitHub API. |
| `make data-extract` | Extract CMD scripts. |
| `make data-label` | Label smells using analyzer. |
| `make data-prepare` | Standardize → pair generation → split (incremental). |
| `make data-prepare-full` | Full reprocessing of data pipeline. |
| `make data-split` | Re-run dataset splitting. |
| `make llm-runtime` | Validate llama.cpp runtime start/stop. |
| `make llm-runtime-test` | Run LLM integration tests. |
| `make release-images` | Build Slim/Complete images tagged for release (no push). |
| `make publish-images` | Build + push release images (requires `RELEASE_VERSION`). |

## Container Cheat Sheet

```bash
# Slim API
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim

# Slim CLI workflow
docker run --rm -v "$PWD:/work" codi:slim codi all /work/demo/python --dry-run

# Complete container with adapters mounted
MODEL_ROOT="$HOME/.codi-models"
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$MODEL_ROOT/adapters:/models/adapters" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

## Health Checks

| Target | Command |
| --- | --- |
| FastAPI | `curl http://localhost:8000/healthz` → `{ "status": "ok" }` |
| LLM server (Complete) | `curl http://localhost:8081/healthz` |
| Adapter mount | `python docker/scripts/verify_adapter.py /models/adapters/<id>` |
| Container state | `docker inspect --format '{{ .State.Health.Status }}' <container>` |

## Troubleshooting Quick Table

| Problem | Steps |
| --- | --- |
| CLI fails with air-gap error | Add host to `AIRGAP_ALLOWLIST` or set `AIRGAP=false` temporarily. |
| `codi` missing after setup | Activate `.venv/bin/activate` or reinstall via `make setup`. |
| `Permission denied` writing to `runs/` | Change `CODI_OUTPUT_ROOT` to a writable location. |
| Adapter not detected | Confirm mount path, run verification script, check file permissions. |
| API request blocked | Ensure FastAPI service is running (`codi serve`) and host/port align with client. |
| Dashboard JSON has broken links | Pass `--relative-to docs/dashboard` when exporting dataset for static hosting. |

## File Locations

| Artefact | Path |
| --- | --- |
| Runs root | `runs/<timestamp>-<stack>-<label>/` |
| Reports | `runs/<...>/reports/report.{md,html}` |
| Metrics | `runs/<...>/metadata/metrics.json` |
| LLM telemetry | `runs/<...>/metadata/llm_metrics.json` |
| RAG metadata | `runs/<...>/metadata/rag.json` |
| Dashboard viewer | `docs/dashboard/index.html` |

## Quick Links

- Architecture details: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Tech stack: [TECH_STACK.md](./TECH_STACK.md)
- Container docs: `SLIM_CONTAINER.md`, `COMPLETE_CONTAINER.md`
- API reference: `API_GUIDE.md`
- LLM pipeline: `LLM_MODULE.md`

## Related Documentation

- [INSTALLATION.md](./INSTALLATION.md) for full setup instructions.
- [CLI_GUIDE.md](./CLI_GUIDE.md) for detailed command usage.
- [OPERATIONS.md](./OPERATIONS.md) for runtime troubleshooting guidance.
