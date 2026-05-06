# CODI LLM Module

CODI augments deterministic rules with an optional local LLM that ranks candidates, generates rationales, and provides operator-friendly insights. This document walks through every stage of the LLM lifecycle: data collection, training, adapter packaging, runtime integration, and evaluation.

## 1. Design Principles

- **Offline by default**: All inference occurs locally via llama.cpp; no external API calls are required.
- **Rules-first**: LLM output is limited to ranking and explanations—Dockerfile content always comes from templates.
- **Adapter-based**: Fine-tuned behaviour ships as LoRA adapters (~100–400 MB) mounted at runtime.
- **Auditable**: Each run records adapter version, base model, confidence scores, and rationale text.

## 2. Component Overview

| Layer | Module | Description |
| --- | --- | --- |
| Data collection | `data/collect_github.py`, `data/label_smells.py`, `data/standardize.py`, `data/synth_pairs_from_rules.py`, `data/split_dataset.py` | Builds curated datasets of Dockerfiles and instruction pairs. |
| Training | `training/qwen15b_lora/` | QLoRA configuration, scripts, and Colab notebook. |
| Runtime | `core/llm.py`, `docker/runtime_complete.py`, `docker/scripts/verify_adapter.py` | Embeds llama.cpp server and wires CLI/API to local endpoints. |
| Evaluation | `eval/` package, `llm_metrics.json`, dashboard summaries | Measures adapter quality and logs telemetry. |

## 3. Data Pipeline

### 3.1 Collection (`data/collect_github.py`)
- Uses GitHub REST API to download Dockerfiles and metadata.
- Supports stack filters, dry-run mode, and rate-limit handling.
- Outputs raw files, `.meta.json` descriptors, and manifest statistics.

### 3.2 CMD Script Extraction (`data/extract_cmd_scripts.py`)
- Traverses COPY/ADD relationships to fetch referenced shell scripts.
- Helpful for training CMD rewrite rationales.

### 3.3 Labeling (`data/label_smells.py`)
- Runs CODI’s analyzer on raw Dockerfiles to label smells, stack info, and CMD flags.
- Optional Hadolint integration adds lint codes.

### 3.4 Standardisation (`data/standardize.py`)
- Deduplicates files using semantic hashes.
- Normalises Dockerfiles, filters low-quality samples, and records reports.

### 3.5 Pair Generation (`data/synth_pairs_from_rules.py`)
- Generates instruction/input/output JSONL pairs for rewriting, ranking, and explaining.
- Incorporates rule metadata to create structured prompts.

### 3.6 Splitting (`data/split_dataset.py`)
- Stratifies by stack into train/val/test splits.
- Writes `data/splits/{train,val,test}.jsonl` plus statistics.

### 3.7 R2 Sync Utilities
- `data/sync_to_r2.py`, `data/download_from_r2.py`, `data/r2_utils.py` manage Cloudflare R2 mirrors.
- Useful for distributing large datasets to training environments.

### 3.8 Make Targets

```bash
make data-collect
make data-extract
make data-label
make data-prepare       # standardize -> pairs -> splits
make data-prepare-full  # full reprocess (no incremental caching)
make data-clean
```

## 4. Training Pipeline

### 4.1 Configuration
- Located in `training/qwen15b_lora/config.yaml`.
- Key hyperparameters: LoRA rank 16, alpha 32, dropout 0.05, learning rate 2e-4, 3 epochs.
- Target modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`.

### 4.2 Hardware Requirements
- Minimum: 8 GB VRAM (e.g., T4) with gradient accumulation.
- Recommended: 16 GB VRAM (e.g., RTX 4080) for faster epochs.
- CPU-only training works but is significantly slower.

### 4.3 Training Script

```bash
python training/qwen15b_lora/train.py \
  --config training/qwen15b_lora/config.yaml \
  --dataset data/splits/train.jsonl \
  --validation data/splits/val.jsonl
```

Features:
- Loads base model (`Qwen/Qwen2.5-Coder-1.5B-Instruct`).
- Applies QLoRA via bitsandbytes.
- Supports `--resume-from` checkpoints.
- Logs to TensorBoard (`training/qwen15b_lora/logs`).

### 4.4 Colab Workflow
- Notebook: `training/qwen15b_lora/train_colab.ipynb`.
- Helper scripts `create_colab_zip.py` / `.sh` package data and configs.
- `COLAB_UPLOAD_GUIDE.md` describes zipped asset handling.

### 4.5 Outputs
- `adapter_model.safetensors`
- `adapter_config.json`
- `metadata.json` (version, dataset split, checksum)
- Optional README summarising training run.

## 5. Adapter Packaging

1. Copy training outputs into repo under `models/adapters/<adapter-id>/`.
2. Populate `metadata.json` with fields:
   ```json
   {
     "adapter_version": "qwen15b-lora-v0.1",
     "created_at": "2025-11-25T04:12:00Z",
     "base_model": "qwen2.5-coder-1.5b",
     "dataset": "data/splits/train.jsonl",
     "checksums": {
       "adapter_model.safetensors": "sha256:..."
     }
   }
   ```
3. Run `python docker/scripts/verify_adapter.py models/adapters/qwen15b-lora-v0.1` to ensure structure and checksums are valid.
4. Document compatibility in `patterns/rules.yml` `llm_assist` section.

## 6. Runtime Integration

### 6.1 Module `core/llm.py`
- `LocalLLMServer`: context manager used by tests for stubbed inference.
- `LLMRankingService`: orchestrates requests to actual llama.cpp server, handles timeouts, and enforces output schema.
- `AssistCandidate` / `AssistContext`: dataclasses describing renderer output.

### 6.2 Complete Container
- `docker/runtime_complete.py` launches llama.cpp and FastAPI.
- Adapter metadata logged at startup; fallback to deterministic stub if adapters missing.

### 6.3 CLI/API Hooks
- `codi run` triggers ranking automatically when `LLM_ENABLED=true`.
- API endpoints `/llm/rank` and `/llm/explain` provide manual control.
- Responses stored in `metadata/llm_metrics.json` (see `REFERENCE.md`).

### 6.4 Environment Variables

| Variable | Description |
| --- | --- |
| `LLM_ENABLED` | Enables or disables LLM features. |
| `LLM_ENDPOINT` | URL of llama.cpp server (default `http://127.0.0.1:8081`). |
| `CODE_MODEL` | Base model ID recorded in telemetry. |
| `ADAPTER_PATH` | Filesystem path to adapter directory. |
| `MODEL_MOUNT_PATH` | Base mount for weights/adapters. |
| `LLAMA_CPP_THREADS` | Number of CPU threads for inference. |
| `LLM_TIMEOUT_SECONDS` | Optional override for HTTP timeouts. |

### 6.5 Health Monitoring
- LLM server exposes `/healthz` returning `{ "status": "ok", "model_id": "..." }`.
- The runtime orchestrator polls this endpoint before starting FastAPI.
- Drifts or failures cause container exit to avoid serving stale adapters.

## 7. Evaluation & Promotion

### 7.1 Evaluation Suite (`eval/`)
- `eval_suite.py` executes ranking/explanation tasks on held-out datasets.
- `build_and_measure.py` compares candidate performance metrics.
- Results stored under `eval/runs/` with HTML reports referencing `eval/reports/llm_eval.html`.

### 7.2 Promotion Criteria
- Adapter must outperform baseline on majority of evaluation stacks.
- Promotion logged in `patterns/rules.yml` under `llm_assist` with fields: `id`, `rule_id`, `adapter_version`, `promoted_at`, `metrics`.
- Example:
  ```yaml
  llm_assist:
    promotions:
      - id: LLM-PROMO-20251125-NODE
        rule_id: node_nextjs_alpine_runtime
        adapter_version: qwen15b-lora-v0.1
        promoted_at: "2025-11-25T04:12:00Z"
        metrics:
          eval_run: eval/runs/20251125_0245
          eval_report: eval/reports/llm_eval.html#20251125_0245
          win_rate: 0.61
  ```

### 7.3 Telemetry
- `llm_metrics.json` contains ranking order, confidence, selected candidate ID, adapter version, base model, and environment snapshot.
- Reports display LLM section summarising recommended candidate and rationale excerpts.

## 8. Troubleshooting

| Issue | Resolution |
| --- | --- |
| Adapter missing or unreadable | Verify mount path, permissions, and `metadata.json`. |
| LLM requests timing out | Increase `LLM_TIMEOUT_SECONDS`, ensure llama.cpp process has enough CPU threads. |
| Air-gap violation logs | Add internal hosts to `AIRGAP_ALLOWLIST` or disable temporarily for testing. |
| Ranking outputs unexpected text | Validate `LLMRankingService` response schema; adapters must not emit raw Dockerfile content. |
| Need deterministic stub | Set `LLM_ENABLED=false` or run CLI with `--skip-llm`. |

## 9. Extending the LLM Module

1. **Collect more data** using `make data-collect` and friends.
2. **Augment rules** to generate synthetic training pairs reflecting new optimisations.
3. **Train new adapter** with updated dataset and config.
4. **Package** adapter into `models/adapters/<id>/` with metadata + checksums.
5. **Validate** using `verify_adapter.py` and run evaluation suite.
6. **Promote** by updating `patterns/rules.yml` and referencing evaluation results.

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) for system context.
- [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) for runtime orchestration.
- [RULES_GUIDE.md](./RULES_GUIDE.md) for deterministic template ties.
- [CICD_RELEASE.md](./CICD_RELEASE.md) for publishing adapters inside images.
- [REFERENCE.md](./REFERENCE.md) for schema details referenced by telemetry files.
