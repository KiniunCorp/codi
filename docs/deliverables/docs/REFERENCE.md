# CODI Reference Manual

Use this document as the canonical reference for commands, APIs, file formats, and key terminology.

## 1. Command Reference

### CLI Commands

| Command | Synopsis |
| --- | --- |
| `codi analyze <path>` | Inspect Dockerfile, output analysis summary. |
| `codi rewrite <path>` | Generate candidate Dockerfiles. |
| `codi run <path>` | Full pipeline; writes artefacts to `CODI_OUTPUT_ROOT`. |
| `codi report <run_dir>` | Generate Markdown + HTML reports. |
| `codi all <path>` | `run` + `report`. |
| `codi serve [--host] [--port]` | Start FastAPI server. |
| `codi dashboard --runs <root> --export-json <file>` | Build dashboard dataset. |
| `codi perf --out <dir>` | Run CPU performance suite. |
| `codi llm rank <path>` | Request LLM ranking (Complete deployments). |
| `codi llm explain <path>` | Request LLM explanations. |

### Make Targets

See [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for full table. Highlights:
- `make setup`, `make lint`, `make test`, `make build-slim`, `make build-complete`, `make release-images`, `make publish-images`, `make data-*`, `make llm-runtime*`.

## 2. API Reference (Summary)

| Endpoint | Method | Description |
| --- | --- | --- |
| `/healthz` | GET | Service health. |
| `/analyze` | POST | Run analyzer only. |
| `/rewrite` | POST | Render candidates. |
| `/run` | POST | Full pipeline. |
| `/report` | POST | Generate report for existing run. |
| `/llm/rank` | POST | LLM ranking (Complete). |
| `/llm/explain` | POST | LLM explanations (Complete). |

Detailed schemas available in [API_GUIDE.md](./API_GUIDE.md) and FastAPI docs.

## 3. File Format Specifications

### 3.1 `metadata/run.json`

```json
{
  "project_path": "demo/node",
  "stack": "node",
  "detected_components": ["nextjs"],
  "smells": ["latest_tag", "shell_form_cmd"],
  "cmd_summary": {
    "uses_shell_form": true,
    "installs_packages": false
  },
  "timestamp": "2025-11-26T17:47:25Z"
}
```

### 3.2 `metadata/metrics.json`

```json
{
  "estimated_original_size_mb": 320,
  "estimated_candidate_size_mb": 205,
  "estimated_size_reduction_pct": 35.9,
  "estimated_layers": {"original": 18, "candidate": 12},
  "analysis_time_ms": 230,
  "render_time_ms": 320,
  "total_time_ms": 650
}
```

### 3.3 `metadata/llm_metrics.json`

```json
{
  "adapter_version": "qwen15b-lora-v0.1",
  "code_model": "qwen2.5-coder-1.5b",
  "ranking": [
    {"candidate_id": "candidate_1", "score": 0.72},
    {"candidate_id": "candidate_2", "score": 0.41}
  ],
  "selected_candidate": "candidate_1",
  "rationale": "Prioritises multi-stage build with wheel caching.",
  "environment": {"llm_endpoint": "http://127.0.0.1:8081"}
}
```

### 3.4 `metadata/environment.json`

```json
{
  "rules_path": "patterns/rules.yml",
  "airgap": true,
  "llm_enabled": true,
  "output_root": "runs/",
  "codl_ruleset_version": "2025.11-llm",
  "timestamp": "2025-11-26T17:47:25Z"
}
```

### 3.5 `metadata/rag.json`

```json
{
  "query_run": "20251126T174725Z-python-python",
  "similar_runs": [
    {
      "run_id": "20251031T224547Z-python-python",
      "stack": "python",
      "score": 0.86,
      "path": "runs/20251031T224547Z-python-python"
    }
  ]
}
```

### 3.6 Dashboard Dataset (`codi dashboard`)

```json
{
  "generated_at": "2025-11-26T18:00:00Z",
  "runs": [
    {
      "id": "20251126T174725Z-python-python",
      "stack": "python",
      "rule_id": "python_fastapi_wheels",
      "metrics": {
        "size_reduction_pct": 35.9,
        "layer_reduction": 6
      },
      "environment": {
        "airgap": true,
        "llm": true
      },
      "reports": {
        "markdown": "reports/report.md",
        "html": "reports/report.html"
      }
    }
  ]
}
```

### 3.7 Rules Catalog (`patterns/rules.yml`)
- See [RULES_GUIDE.md](./RULES_GUIDE.md) for semantics.

## 4. Environment Variables

Refer to [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for the complete table. Key variables include `CODI_OUTPUT_ROOT`, `RULES_PATH`, `AIRGAP`, `AIRGAP_ALLOWLIST`, `LLM_ENABLED`, `LLM_ENDPOINT`, `CODE_MODEL`, `ADAPTER_PATH`, `MODEL_MOUNT_PATH`, `LLAMA_CPP_THREADS`.

## 5. Glossary

| Term | Definition |
| --- | --- |
| Adapter | LoRA weights that fine-tune the base model for LLM assist. |
| Builder stage | Dockerfile stage that installs dependencies and builds artefacts. |
| Candidate | Optimised Dockerfile generated from templates. |
| CMD rewrite | Conversion of CMD/ENTRYPOINT instructions to exec form and promotion of runtime installs. |
| Complete container | CODI image with embedded LLM runtime. |
| Slim container | Rules-only CODI image. |
| RAG index | SQLite database storing embeddings of past runs for similarity search. |
| Rules catalog | YAML file describing templates, metadata, and CMD rewrites. |
| Run directory | Timestamped folder containing inputs, candidates, metadata, and reports. |

## 6. Version History

| Version | Highlights |
| --- | --- |
| v0.1.0 | Initial public release including CLI, API, Slim & Complete containers, dashboard tooling, LLM adapter integration, and release automation. |

Future entries should document notable additions (new stacks, BuildKit integration, remote adapters). Avoid referencing internal roadmap code names.

## 7. Known Limitations

- Build runner operates in dry-run mode; real Docker builds require manual execution.
- Only three stacks are supported out of the box (Node.js, Python, Java).
- LLM runtime is CPU-only; GPU acceleration would require custom builds.
- Adapter validation expects predefined directory structure; no automatic download.
- Authentication for API endpoints is not built-in; rely on surrounding infrastructure.

## 8. Roadmap Themes

- BuildKit integration for actual Docker builds and size measurements.
- Additional stacks (Go, .NET, Rust) and templates.
- Multi-architecture container images.
- Enhanced dashboard visualisations and REST endpoints for aggregated data.
- Optional authentication layer for FastAPI service.
- GPU-enabled LLM runtime for higher throughput.

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) for system diagrams referenced here.
- [CLI_GUIDE.md](./CLI_GUIDE.md) and [API_GUIDE.md](./API_GUIDE.md) for interfaces consuming these schemas.
- [RULES_GUIDE.md](./RULES_GUIDE.md) for catalog fields mirrored in the reference tables.
- [LLM_MODULE.md](./LLM_MODULE.md) for telemetry structures tied to adapters.
