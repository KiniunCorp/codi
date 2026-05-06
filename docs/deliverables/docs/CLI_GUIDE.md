# CODI CLI Guide

The `codi` CLI provides complete parity with the FastAPI service. This document covers every command, flags, environment variables, and workflows.

## 1. Command Overview

Run `codi --help` for the full list. Core commands:

- `codi analyze`
- `codi rewrite`
- `codi run`
- `codi report`
- `codi all`
- `codi serve`
- `codi dashboard`
- `codi perf`
- `codi llm rank`
- `codi llm explain`

Each subcommand accepts `--help` for options.

## 2. Shared Options

| Flag | Description |
| --- | --- |
| `--out PATH` | Override output directory for run artefacts. Default inherits `CODI_OUTPUT_ROOT` (or `runs/`). |
| `--rules-path PATH` | Use alternate rules file (same as `RULES_PATH`). |
| `--stack STACK` | Force stack detection (`node`, `python`, `java`). Useful when heuristics are ambiguous. |
| `--dry-run` | For commands that would write to disk, simulate actions without persisting artefacts (where supported). |

## 3. Analyze

```bash
codi analyze demo/node
```

Outputs stack detection summary, smell list, CMD insights, and policy notes. Useful for quick diagnostics without generating candidates.

### Key Flags
- `--format json` – emit machine-readable JSON.
- `--write-metadata` – persist `metadata/run.json` even during analysis-only workflows.

## 4. Rewrite

```bash
codi rewrite demo/python --stack python
```

Generates candidate Dockerfiles under `runs/<id>/candidates/` without running metrics estimation. Typically followed by manual review or `codi report`.

### Flags
- `--rules-path` – use alternate templates.
- `--candidate-limit N` – limit to N templates (default 2).

## 5. Run

```bash
codi run demo/java --out runs/java-runs
```

Executes end-to-end pipeline: parse, detect, analyze, render, estimate metrics, write artefacts, update RAG index. When `LLM_ENABLED=true`, run also triggers ranking and rationale generation.

### Flags
- `--skip-llm` – bypass LLM even if enabled globally.
- `--candidate-limit` – limit templates.
- `--disable-rag` – skip similarity lookup if not desired.

## 6. Report

```bash
LATEST=$(ls -dt runs/* | head -n 1)
codi report "$LATEST"
```

Regenerates Markdown/HTML from stored metadata and candidates. Safe to run multiple times after editing templates.

### Flags
- `--format` – `md`, `html`, or `all` (default).
- `--open` – attempt to open HTML report using system default browser.

## 7. All

```bash
codi all demo/node --out runs/demo-node
```

Shortcut for `run` followed by `report`. Accepts the same flags as `run` plus `--format` for report output.

## 8. Serve (FastAPI)

```bash
codi serve --host 0.0.0.0 --port 8000
```

Starts FastAPI server replicating CLI functionality. Environment variables propagate into the server’s `CodiEnvironment` snapshot.

### Flags
- `--reload` – enable auto-reload (development only).
- `--workers` – number of Uvicorn workers.

## 9. Dashboard

```bash
codi dashboard --runs runs/ --export-json docs/dashboard/data/sample_runs.json --relative-to docs/dashboard
```

Aggregates run directories into a JSON dataset consumed by the static dashboard viewer.

### Options
- `--runs PATH` – root containing run folders (required).
- `--export-json FILE` – output path.
- `--relative-to PATH` – rewrite report links relative to static hosting root.

## 10. Performance Suite

```bash
codi perf --out runs/perf --analysis-budget 5 --total-budget 180
```

Runs CPU-only analysis/render loops with timing budgets, writing `cpu_perf_report.json` for audits.

## 11. LLM Commands (Complete deployments)

### 11.1 `codi llm rank`

```bash
codi llm rank demo/python --out runs/llm-eval
```

- Sends analyser + renderer output to the local LLM server.
- Stores `llm_metrics.json` with ranking and confidence scores.

### 11.2 `codi llm explain`

```bash
codi llm explain demo/node --out runs/llm-explain
```

- Requests textual rationales for each candidate.
- Results stored alongside other metadata.

Both commands honour `LLM_ENABLED`, `LLM_ENDPOINT`, and adapter environment variables.

## 12. Environment Variable Reference

See [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for the full table. CLI picks up variables from the shell, `.env`, or command flags.

## 13. Example Workflows

### 13.1 Local Optimisation Loop

1. `codi run demo/node`
2. Inspect `runs/<id>/candidates/*.Dockerfile`
3. `codi report runs/<id>`
4. Share `report.html`

### 13.2 CI Integration (Slim Container)

```bash
# Dockerfile step
docker run --rm -v "$PWD:/work" -w /work codi:slim \
  codi all /work/demo/python --out /work/runs/ci-python
```

Archive `/work/runs/ci-python` as a build artifact.

### 13.3 LLM Evaluation Session

```bash
export MODEL_MOUNT_PATH="$HOME/.codi-models"
export ADAPTER_PATH="$MODEL_MOUNT_PATH/adapters/qwen15b-lora-v0.1"
export LLM_ENABLED=true
codi llm rank demo/python --out runs/llm-session
```

### 13.4 Dashboard Publishing

```bash
codi dashboard --runs runs/ --export-json docs/dashboard/data/team_runs.json --relative-to docs/dashboard
python -m http.server --directory docs/dashboard 8001
```

## 14. Exit Codes

| Command | Exit Condition |
| --- | --- |
| `0` | Successful execution. |
| `1` | Validation failure, parse error, or policy violation. |
| `2` | CLI misuse (missing args). |

## 15. Logging

- CLI outputs Rich tables/logs to stdout.
- Additional debug logs available by setting `CODI_LOG_LEVEL=DEBUG`.
- Errors include run directory references for quick inspection.

## Related Documentation

- [INSTALLATION.md](./INSTALLATION.md) for environment setup.
- [SLIM_CONTAINER.md](./SLIM_CONTAINER.md) and [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) for container workflows.
- [API_GUIDE.md](./API_GUIDE.md) for HTTP equivalents of CLI commands.
- [RULES_GUIDE.md](./RULES_GUIDE.md) for template behaviour referenced by CLI output.
