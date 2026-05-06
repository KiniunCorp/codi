# CODI API Guide

The FastAPI service mirrors all CLI functionality and exposes schema-validated endpoints for integrations. This guide describes available endpoints, request/response structures, and usage examples.

## 1. Getting Started

Run the server via CLI or container:

```bash
# Local CLI
codi serve --host 0.0.0.0 --port 8000

# Slim container
docker run --rm -it -v "$PWD:/work" -p 8000:8000 codi:slim
```

Interactive docs available at `http://<host>:<port>/docs`. Health check: `GET /healthz`.

## 2. Authentication

Current release exposes endpoints without authentication. Deployments behind ingress or API gateways should enforce authentication/authorization externally. Future versions may support tokens.

## 3. Environment Snapshot

Each response includes a `environment` block derived from `core.config.CodiEnvironment`, showing resolved toggles (`LLM_ENABLED`, `AIRGAP`, `RULES_PATH`, etc.).

## 4. Endpoints

### 4.1 `POST /analyze`
- **Purpose**: Parse Dockerfile, detect stack, run analyzer, return metadata.
- **Body**:
  ```json
  {
    "project_path": "demo/node",
    "stack_hint": "node",
    "rules_path": "patterns/rules.yml"
  }
  ```
- **Response**: Analysis payload with smells, CMD summary, policy notes, environment snapshot.
- **Error Codes**: 400 (validation), 404 (path not found), 422 (parse errors).

### 4.2 `POST /rewrite`
- **Purpose**: Generate deterministic candidates without running full pipeline.
- **Body**:
  ```json
  {
    "project_path": "demo/python",
    "candidate_limit": 2
  }
  ```
- **Response**: Candidate metadata including file paths, applied rules, CMD rewrites, and rationale comments.

### 4.3 `POST /run`
- **Purpose**: Full pipeline (analyse → rewrite → metrics → store artefacts).
- **Body**:
  ```json
  {
    "project_path": "demo/java",
    "out_dir": "runs/api-demo",
    "candidate_limit": 2,
    "skip_llm": false
  }
  ```
- **Response**: Paths to generated run, metrics summary, candidate info, LLM ranking (if enabled), and environment snapshot.
- **Behaviour**: Writes artefacts under `out_dir` (defaults to configured `CODI_OUTPUT_ROOT`).

### 4.4 `POST /report`
- **Purpose**: Generate Markdown/HTML report for existing run directory.
- **Body**:
  ```json
  {
    "run_path": "runs/20251126T174725Z-python-python",
    "format": "all"
  }
  ```
- **Response**: Absolute paths to generated report files; includes metadata snapshot for convenience.

### 4.5 `POST /llm/rank` (Complete deployments)
- **Purpose**: Invoke local LLM ranking pipeline on-demand.
- **Body**:
  ```json
  {
    "project_path": "demo/node",
    "out_dir": "runs/llm-rank"
  }
  ```
- **Response**: Ranking order, confidence scores, adapter metadata, environment snapshot.
- **Notes**: Requires `LLM_ENABLED=true` and reachable `LLM_ENDPOINT`.

### 4.6 `POST /llm/explain`
- **Purpose**: Request textual rationales for generated candidates.
- **Body**: Same shape as `/llm/rank`.
- **Response**: Explanation strings keyed by candidate identifier.

### 4.7 `GET /healthz`
- Returns `{ "status": "ok" }` if service is healthy.

## 5. Request Fields

| Field | Type | Description |
| --- | --- | --- |
| `project_path` | string | Absolute or relative path accessible to the server. |
| `stack_hint` | string | Optional manual stack override (`node`, `python`, `java`). |
| `rules_path` | string | Alternate rules file. |
| `out_dir` | string | Where to place run artefacts. Defaults to `CODI_OUTPUT_ROOT`. |
| `candidate_limit` | int | Number of templates to render (1-3). |
| `skip_llm` | bool | Skip LLM even if enabled globally. |
| `format` | string | `md`, `html`, or `all` for reports. |

## 6. Response Structure (example excerpt)

```json
{
  "run_path": "runs/20251126T174725Z-python-python",
  "candidates": [
    {
      "id": "candidate_1",
      "rule_id": "python_fastapi_wheels",
      "summary": "Switches to wheel-based install with multi-stage caching",
      "cmd_rewrite": {
        "converted_to_exec_form": true,
        "promoted_runtime_installs": ["pip install --user"]
      }
    }
  ],
  "metrics": {
    "estimated_size_reduction_pct": 34.8,
    "estimated_layer_reduction": 4,
    "analysis_time_ms": 215
  },
  "environment": {
    "rules_path": "patterns/rules.yml",
    "airgap": true,
    "llm_enabled": false
  }
}
```

## 7. Error Handling

| Status | Meaning |
| --- | --- |
| 400 | Missing or invalid parameters. |
| 404 | Provided path does not exist. |
| 409 | Policy violation (e.g., adapter missing, air-gap breach attempt). |
| 422 | Parsing or rendering errors, includes detailed message. |
| 500 | Unexpected server error (check logs). |

Responses include `detail` field with actionable information. For parsing issues, `detail.context` lists offending lines.

## 8. cURL Examples

```bash
# Analyze project
curl -X POST http://localhost:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"project_path": "demo/node"}' | jq

# Trigger full run
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"project_path": "demo/python", "out_dir": "runs/api-python"}' | jq '.metrics'

# Generate report
curl -X POST http://localhost:8000/report \
  -H 'Content-Type: application/json' \
  -d '{"run_path": "runs/api-python"}'
```

## 9. Python Client Snippet

```python
import requests

BASE_URL = "http://localhost:8000"
payload = {"project_path": "demo/java", "out_dir": "runs/api-java"}
resp = requests.post(f"{BASE_URL}/run", json=payload, timeout=600)
resp.raise_for_status()
print(resp.json()["metrics"])
```

## 10. JavaScript (fetch) Example

```javascript
const payload = { project_path: "demo/node" };
fetch("http://localhost:8000/analyze", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
})
  .then((res) => res.json())
  .then((data) => console.log(data.stack));
```

## 11. Deployment Considerations

- **Air-gap allowlists**: If the API is accessed via a hostname, add it to `AIRGAP_ALLOWLIST` as needed (`AIRGAP_ALLOWLIST="internal.api.local"`).
- **Reverse proxies**: When running behind Nginx/Traefik, forward required headers; FastAPI docs remain accessible.
- **Scaling**: Uvicorn supports multiple workers via `codi serve --workers 4`; horizontal scaling is straightforward because runs are written to shared storage.
- **Storage**: Ensure server has write access to `CODI_OUTPUT_ROOT`. Use a dedicated volume when running inside containers.

## 12. Logging & Monitoring

- FastAPI logs requests/responses via Uvicorn.
- Set `LOG_LEVEL=debug` or `CODI_LOG_LEVEL=DEBUG` for deeper traces.
- Export metrics to external systems by tailing logs or wrapping server with middleware.

## Related Documentation

- [CLI_GUIDE.md](./CLI_GUIDE.md) for local command equivalents.
- [SLIM_CONTAINER.md](./SLIM_CONTAINER.md) and [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) for deployment contexts.
- [LLM_MODULE.md](./LLM_MODULE.md) for model-specific API endpoints.
- [REFERENCE.md](./REFERENCE.md) for schema definitions.
