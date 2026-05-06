# CODI Operations Guide

This runbook covers day-2 activities for operating CODI in development, staging, and production environments.

## 1. Artefact Locations

| Artefact | Path |
| --- | --- |
| Runs root | `CODI_OUTPUT_ROOT` (default `runs/`) |
| Reports | `runs/<id>/reports/report.{md,html}` |
| Metrics | `runs/<id>/metadata/metrics.json` |
| Environment snapshot | `runs/<id>/metadata/environment.json` |
| LLM telemetry | `runs/<id>/metadata/llm_metrics.json` |
| RAG index | `runs/_rag/index.sqlite3` |
| Dashboard datasets | `docs/dashboard/data/*.json` |

## 2. Health Checks

| Component | Command | Expected |
| --- | --- | --- |
| FastAPI | `curl http://localhost:8000/healthz` | `{ "status": "ok" }` |
| LLM server | `curl http://localhost:8081/healthz` | `{ "status": "ok", "model_id": "..." }` |
| Adapter mount | `python docker/scripts/verify_adapter.py /models/adapters/<id>` | Exit 0 |
| Container | `docker inspect --format '{{ .State.Health.Status }}' <container>` | `healthy` |
| Dashboard dataset | `jq . docs/dashboard/data/sample_runs.json` | Valid JSON |

## 3. Start/Stop Procedures

### Local CLI

```bash
source .venv/bin/activate
codi run demo/node --out runs/local-node
```

### Slim Container API

```bash
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim
```

### Complete Container

```bash
MODEL_ROOT="$HOME/.codi-models"

docker run --rm -it \
  -v "$PWD:/work" \
  -v "$MODEL_ROOT:/models" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

### Graceful Shutdown
- API: `Ctrl+C` (SIGINT) or `docker stop`.
- Complete container: `docker stop <id>` terminates llama.cpp and FastAPI.

## 4. Configuration Management

Maintain a central `.env` or environment file for production deployments. Example:

```
CODI_OUTPUT_ROOT=/data/codi-runs
RULES_PATH=/opt/codi/patterns/rules.yml
AIRGAP=true
AIRGAP_ALLOWLIST=testserver,internal.api.local
LLM_ENABLED=true
LLM_ENDPOINT=http://127.0.0.1:8081
MODEL_MOUNT_PATH=/models
ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1
LLAMA_CPP_THREADS=8
```

Reload services after changes to ensure snapshots reflect new values.

## 5. Troubleshooting Checklist

| Symptom | Action |
| --- | --- |
| CLI/APIs can’t access project path | Verify mount points or run path permissions. |
| Adapter validation failure | Confirm files exist, run verification script, check checksums. |
| Air-gap guard blocking legitimate host | Add host to `AIRGAP_ALLOWLIST`. |
| Reports missing metrics | Rerun `codi run`; ensure `metrics.json` exists. |
| Dashboard links broken | Use `--relative-to` when generating dataset. |
| RAG lookups slow | Vacuum SQLite database in `runs/_rag` or rebuild via `codi run --disable-rag` when not needed. |
| llama.cpp CPU contention | Adjust `LLAMA_CPP_THREADS` to leave room for FastAPI. |

## 6. Log Collection

- **CLI runs**: Logs printed to stdout/stderr. Redirect to file if needed.
- **FastAPI**: `uvicorn` logs accessible via terminal or `docker logs`.
- **Complete container**: `docker logs` shows adapter validation, llama.cpp output, and API logs.
- **LLM telemetry**: `llm_metrics.json` captures ranking results.

Consider centralised logging via container runtime (e.g., Fluent Bit) if running CODI in production clusters.

## 7. Backup & Retention

- Rotate runs using `ls -dt runs/* | tail -n +31 | xargs -r rm -rf` to keep last 30 runs.
- Archive important runs to object storage (tar + upload).
- Backup RAG index if similarity search history is required.

## 8. Scaling Guidance

| Scenario | Recommendation |
| --- | --- |
| Many concurrent API requests | Increase Uvicorn workers (`codi serve --workers 4`) and front with load balancer. |
| Heavy LLM usage | Deploy multiple Complete containers with round-robin LLM endpoints; share adapter mount via network storage. |
| CI workloads | Run multiple Slim containers in parallel; output directories should be unique per job. |
| Storage constraints | Periodically clean `runs/` or point `CODI_OUTPUT_ROOT` to high-capacity volume. |

## 9. Run Verification Steps

1. Confirm `metrics.json` includes expected reductions.
2. Review `report.html` for rationale and security notes.
3. Inspect `metadata/environment.json` for correct toggles.
4. If LLM enabled, check `llm_metrics.json` for adapter version and ranking confidence.

## 10. Incident Response

1. **Isolate** problematic run directory for debugging.
2. **Collect logs** from CLI or container.
3. **Reproduce** with `codi run --dry-run` if build environment differs.
4. **Escalate** by attaching artefacts (report, metrics, environment snapshot) to ticketing system.

## 11. Maintenance Tasks

| Cadence | Task |
| --- | --- |
| Weekly | `make test`, `codi perf`, verify adapters, review dashboard trends. |
| Monthly | Update dependencies, rebuild containers, rotate adapters if new versions exist. |
| Quarterly | Re-run data pipeline and training to capture new Dockerfile patterns. |

## Related Documentation

- [SECURITY.md](./SECURITY.md) for detailed policy controls.
- [CICD_RELEASE.md](./CICD_RELEASE.md) for publishing and rollback procedures.
- [PERFORMANCE.md](./PERFORMANCE.md) for tuning guidance referenced in maintenance tasks.
- [LLM_MODULE.md](./LLM_MODULE.md) for adapter operations often handled by operators.
