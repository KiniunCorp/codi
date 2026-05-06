# CODI Complete Container Guide

The Complete container extends the Slim image with an embedded llama.cpp runtime and adapter management tooling. It is designed for air-gapped environments that still require LLM ranking and rationale generation.

## 1. Image Overview

- **Dockerfile**: `docker/Dockerfile.complete`
- **Base**: `codi:slim`
- **Additions**:
  - Installs build-essential, git, curl, and `libcurl4-openssl-dev`.
  - Clones and compiles `llama.cpp` with CPU optimisations.
  - Adds adapter validation script (`docker/scripts/verify_adapter.py`) and mount helper (`docker/scripts/mount_adapter.sh`).
  - Provides orchestration script `docker/runtime_complete.py` to start llama.cpp then FastAPI.
- **Ports**: 8000 (FastAPI), 8081 (LLM server).
- **Volumes**: `/work` for project data, `/models` for weights/adapters.

## 2. Build Instructions

```bash
make build-complete
# or
docker build -f docker/Dockerfile.complete -t codi:complete .
```

## 3. Runtime Orchestration

`docker/runtime_complete.py` performs the following steps when the container starts:

1. Validate `MODEL_MOUNT_PATH` and `ADAPTER_PATH`.
2. Run `docker/scripts/verify_adapter.py` if adapter path exists.
3. Launch `llama.cpp` server with configured threads and model paths.
4. Wait for LLM health check (`/healthz`).
5. Export `LLM_ENDPOINT` pointing to the embedded server (default `http://127.0.0.1:8081`).
6. Start FastAPI (`uvicorn api.server:app`).

Logs include adapter version, checksum validation results, and health status for both services.

## 4. Running the Container

```bash
MODEL_ROOT="$HOME/.codi-models"
mkdir -p "$MODEL_ROOT/adapters/qwen15b-lora-v0.1"

# copy adapters into MODEL_ROOT before running

docker run --rm -it \
  -v "$PWD:/work" \
  -v "$MODEL_ROOT:/models" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -e CODE_MODEL=qwen2.5-coder-1.5b \
  -e ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1 \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

- FastAPI docs: `http://localhost:8000/docs`
- LLM health: `http://localhost:8081/healthz`

## 5. Adapter Layout

Adapters must follow this structure under `/models/adapters/<adapter-id>/`:

```
adapter_config.json
adapter_model.safetensors (or .bin)
metadata.json
README.md (optional)
```

`metadata.json` should include version, training info, and checksum. CODI logs adapter version at startup.

## 6. Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODEL_MOUNT_PATH` | `/models` | Root directory mounted from host. |
| `ADAPTER_PATH` | `/models/adapters/qwen15b-lora-v0.1` | Adapter directory consumed by llama.cpp runtime. |
| `CODE_MODEL` | `qwen2.5-coder-1.5b` | Base model identifier recorded in telemetry. |
| `LLM_ENABLED` | `true` | Enables ranking/explanation flows. |
| `LLM_ENDPOINT` | Auto-set to embedded server | Override to target remote LLM. |
| `LLAMA_CPP_THREADS` | `4` | CPU threads for inference. |
| `AIRGAP` | `true` | Outbound HTTP guard for both API and runtime. |
| `AIRGAP_ALLOWLIST` | _(empty)_ | Hosts allowed when air-gapped. |
|

## 7. Health Checks

- **FastAPI**: `curl http://localhost:8000/healthz`
- **LLM server**: `curl http://localhost:8081/healthz`
- **Adapter validation**: `docker exec <container> python docker/scripts/verify_adapter.py /models/adapters/qwen15b-lora-v0.1`

The orchestrator exits if llama.cpp fails to start or adapter validation errors occur.

## 8. Example: Local Optimisation With Embedded LLM

```bash
# Run container
MODEL_ROOT="$HOME/.codi-models"
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$MODEL_ROOT:/models" \
  -p 8000:8000 -p 8081:8081 \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  codi:complete &
CONTAINER_PID=$!

# Inside another terminal
docker exec -it $(docker ps --filter ancestor=codi:complete -q | head -n 1) \
  codi run /work/demo/node --out /work/runs/complete-node

wait $CONTAINER_PID
```

## 9. Using Remote LLM Endpoints

If another internal llama.cpp deployment should be used instead of the embedded one:

```bash
-e LLM_ENDPOINT=http://llm.internal.example.com:8081 \
-e LLM_ENABLED=true \
-e AIRGAP_ALLOWLIST="llm.internal.example.com"
```

In this mode you can omit adapter mounts, although `MODEL_MOUNT_PATH` remains available for logging local metadata.

## 10. Adapter Maintenance

- **Verification**: `python docker/scripts/verify_adapter.py models/adapters/qwen15b-lora-v0.1`
- **Mount helper**: `/opt/codi/scripts/mount_adapter.sh /models/adapters/qwen15b-lora-v0.1`
- **Promotion**: Document compatibility in `patterns/rules.yml` (`llm_assist` section) and record evaluation metadata.

## 11. Logs & Telemetry

- Runtime writes combined logs to stdout (visible via `docker logs`).
- `runs/<id>/metadata/llm_metrics.json` records ranking/explanation output.
- `environment.json` captures adapter version, ruleset version, and runtime defaults.

## 12. Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `Adapter Status: not_mounted` | Ensure host directory is mounted at `/models/adapters/<id>` and readable by UID 1000. |
| `checksum mismatch` | Re-copy adapter files or update `metadata.json`. |
| `llama-server: command not found` | Rebuild image (`make build-complete`); ensure llama.cpp built successfully. |
| `LLM_ENDPOINT` not reachable | Confirm port mappings, container network settings, or remote host allowlist. |
| Slow inference | Increase `LLAMA_CPP_THREADS` (limited by host CPU) or reduce token limits in `docker/runtime_complete.py`. |

## 13. When to Choose Complete vs Slim

| Scenario | Recommended Image |
| --- | --- |
| Need deterministic rewrites only | Slim |
| Require offline ranking/rationales | Complete |
| CI pipelines without adapters | Slim |
| Air-gapped data centre with adapter catalog | Complete |

## Related Documentation

- [LLM_MODULE.md](./LLM_MODULE.md) for adapter lifecycle and data pipeline details.
- [CLI_GUIDE.md](./CLI_GUIDE.md) for commands executed inside the container.
- [CICD_RELEASE.md](./CICD_RELEASE.md) for publishing procedures.
- [SECURITY.md](./SECURITY.md) for air-gap and container hardening guidance.
