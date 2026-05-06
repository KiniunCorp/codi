# CODI Models Guide

The Complete CODI container ships with llama.cpp for CPU-only inference and supports LoRA adapters for fine-tuned Dockerfile optimization. This guide explains model runtime wiring, adapter mounting, and operational toggles.

## Default Paths & Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_MOUNT_PATH` / `CODI_MODEL_PATH` | `/models` | Filesystem location where base model weights and adapters are mounted. |
| `CODE_MODEL` | `qwen2.5-coder-1.5b` | Base code model identifier. Fallback: `starcoder2-3b`. |
| `ADAPTER_PATH` | `/models/adapters/qwen15b-lora-v0.1` | Path to LoRA adapter directory (must contain `adapter_config.json` and weights). |
| `ADAPTER_VERSION` | `unknown` (auto-detected from `metadata.json`) | Adapter version for tracking and logging. |
| `LLM_ENABLED` | `true` (Complete image), `false` (Slim image) | Enables the local LLM assist layer. Set to `false` to disable summaries/recommendations. |
| `LLM_ENDPOINT` | Auto-generated (`http://127.0.0.1:8081`) | Override to target an external LLM endpoint instead of the embedded runtime. |
| `LLAMA_CPP_THREADS` | `4` | Number of CPU threads for llama.cpp inference. |
| `AIRGAP` | `true` | Prevents outbound HTTP(S) requests; leave enabled for offline compliance. |
| `AIRGAP_ALLOWLIST` | _empty_ | Optional comma-separated host allowlist for controlled outbound access (e.g. internal registries). |
| `CODI_RULESET_VERSION` | `2025.11-llm` | Propagates into rendered Dockerfiles (`LABEL codi.ruleset_version`) to link adapters with promotion metadata. |

## Directory Layout

Mount adapters and model weights under the configured path:

```
/models
├── adapters/
│   └── qwen15b-lora-v0.1/
│       ├── adapter_config.json       # Required: PEFT/LoRA configuration
│       ├── adapter_model.safetensors # Required: Adapter weights (or .bin)
│       ├── metadata.json             # Recommended: Version, checksums, training info
│       └── README.md                 # Optional: Adapter documentation
└── weights/                          # Optional: Base model weights (if not using Hugging Face)
    ├── qwen2.5-coder-1.5b-q4.gguf
    └── tokenizer.model
```

### Adapter Structure

Each adapter directory must contain:
- **`adapter_config.json`**: PEFT configuration (LoRA rank, target modules, etc.)
- **`adapter_model.safetensors`** or **`adapter_model.bin`**: Trained LoRA weights

Recommended files:
- **`metadata.json`**: Versioning, checksums, dataset info, training config
- **`README.md`**: Human-readable adapter documentation

The `core.security.ensure_model_mount_path(create=True)` helper will create the directory if requested.

## Adapter Version Matrix

| Adapter ID | Ruleset Version | Compatible Rules | Validation Run |
|------------|----------------|------------------|----------------|
| `qwen15b-lora-v0.1` | `2025.11-llm` | `node_nextjs_alpine_runtime`, `python_fastapi_wheels`, `java_springboot_jre21` | `eval/runs/20251125_0245` (win rate ≥0.61 across stacks) |

See [`docs/llm_adapter_notes.md`](../docs/llm_adapter_notes.md) for checksum references, mounting locations, and troubleshooting steps.

## Usage Scenarios

### Local CLI with Adapter

```bash
export MODEL_MOUNT_PATH="$HOME/.codi-models"
export ADAPTER_PATH="$MODEL_MOUNT_PATH/adapters/qwen15b-lora-v0.1"
export CODE_MODEL="qwen2.5-coder-1.5b"

# Ensure adapter directory exists
mkdir -p "$ADAPTER_PATH"

# Copy trained adapter (see training/qwen15b_lora/ for the QLoRA pipeline)
cp -r training/qwen15b_lora/output/* "$ADAPTER_PATH/"

# Validate adapter
python3 docker/scripts/verify_adapter.py "$ADAPTER_PATH"

# Run CODI locally (LLM assist enabled with adapter)
python3 -m cli.main run demo/python --out runs/local
```

### Complete Container with Mounted Adapter

```bash
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$HOME/.codi-models/adapters:/models/adapters" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -e CODE_MODEL=qwen2.5-coder-1.5b \
  -e ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1 \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

The runtime launcher (`docker/runtime_complete.py`) validates the adapter mount, reads metadata, logs adapter version, and starts llama.cpp with the configured adapter before booting FastAPI.

### Verifying Adapter Mounting

Run the adapter validation script:

```bash
# Inside container
/bin/bash /opt/codi/scripts/mount_adapter.sh /models/adapters/qwen15b-lora-v0.1

# Or directly
python3 docker/scripts/verify_adapter.py models/adapters/qwen15b-lora-v0.1
```

### Testing Runtime Without Adapters

To test the runtime with base model only:

```bash
docker run --rm -it \
  -v "$PWD:/work" \
  -e LLM_ENABLED=true \
  -e CODE_MODEL=qwen2.5-coder-1.5b \
  -e ADAPTER_PATH="" \
  codi:complete
```

### Verify `/llm/rank` offline

```bash
# Inside a running Complete container
python3 -m cli.main llm rank demo/node --out runs/llm-smoke
cat runs/llm-smoke/llm_metrics.json | jq '{adapter_version, ruleset_version}'
```

The response should include the adapter metadata, `ruleset_version` tag, and ranking payload. Use [`docs/llm_promotion_checklist.md`](../docs/llm_promotion_checklist.md) to audit results before promoting new rules.

## External Endpoints

To rely on a remote (but still internal) LLM endpoint:

```bash
export LLM_ENABLED=true
export LLM_ENDPOINT="http://llm.internal.example.com:8081"
python3 -m cli.main run demo/node
```

Air-gap enforcement still blocks other outbound requests; add the remote host to `AIRGAP_ALLOWLIST` if the endpoint is not on localhost.

## Operational Tips

- **Adapters are lightweight** (~10-400 MB) and safe to mount; base model weights can be larger (1-7 GB).
- **llama.cpp** runs CPU-only with Q4_K_M quantization for fast cold starts (typical: <3s inference).
- **Adapter checksums**: Verify integrity with `verify_adapter.py` before production use.
- **Fallback**: If adapter loading fails, CODI falls back to base model or mock LLM (deterministic responses).
- **Version tracking**: Adapter version is logged at startup and included in `runs/<id>/metadata/environment.json`.
- CODI never downloads weights; ensure adapters and models are pre-staged inside `/models` before launching the Complete container.
- Tests exercising adapter loading live in `tests/test_llm.py` and `tests/test_security.py`.

## Make Targets

The following make targets support runtime validation:

```bash
# Validate LLM runtime start/stop (no network)
make llm-runtime

# Run LLM runtime integration tests
make llm-runtime-test
```

## Troubleshooting

### Adapter Not Loading

**Symptoms**: Logs show `"Adapter Status: not_mounted"` or `"no_metadata"`

**Solutions**:
1. Verify adapter directory exists: `ls -la $ADAPTER_PATH`
2. Check required files: `adapter_config.json`, `adapter_model.safetensors` (or `.bin`)
3. Run validation: `python3 docker/scripts/verify_adapter.py $ADAPTER_PATH`
4. Check permissions: Ensure files are readable by `codi` user (UID 1000)

### Checksum Mismatch

**Symptoms**: `verify_adapter.py` reports checksum mismatch

**Solutions**:
1. Re-copy adapter files from source
2. Update checksums: Edit `metadata.json` with correct SHA256 values
3. If intentional (development), remove `checksums` section from `metadata.json`

### llama.cpp Binary Not Found

**Symptoms**: Runtime fails with `llama-server: command not found`

**Solutions**:
1. Rebuild Complete container: `make build-complete`
2. Verify binary in image: `docker run codi:complete which llama-server`
3. Check Dockerfile.complete llama.cpp build stage

For day-2 operations (log rotation, health checks, troubleshooting), see [`docs/runbook.md`](../docs/runbook.md).
