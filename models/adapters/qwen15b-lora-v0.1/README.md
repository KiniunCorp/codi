# CODI LoRA Adapter - Qwen2.5-Coder-1.5B v0.1

## Overview

This is a **development stub** adapter for the CODI local model runtime.

**Status**: Placeholder for testing infrastructure  
**Version**: v0.1.0-dev  
**Base Model**: Qwen/Qwen2.5-Coder-1.5B  
**Adapter Type**: LoRA (Low-Rank Adaptation)

## Purpose

This stub adapter enables testing of:
- Adapter mount scripts (`mount_adapter.sh`, `verify_adapter.py`)
- Configuration wiring (`core/config.py`, `core/llm.py`)
- Runtime logging and version tracking
- Complete container build and startup

## Files

- `metadata.json` - Adapter metadata and checksums
- `adapter_config.json` - PEFT/LoRA configuration
- `README.md` - This file

**Missing**: `adapter_model.safetensors` or `adapter_model.bin` (actual trained weights)

## Usage

### For Testing (Without Weights)

The current stub is sufficient for:
```bash
# Test adapter metadata reading
python3 docker/scripts/verify_adapter.py models/adapters/qwen15b-lora-v0.1

# Test LLM runtime with adapter configuration
make llm-runtime

# Build Complete container
make build-complete
```

### For Production (With Weights)

To use a trained adapter:

1. **Train the adapter** using the QLoRA pipeline in `training/qwen15b_lora/`:
   ```bash
   make train-lora
   ```

2. **Copy trained weights** to this directory:
   ```bash
   cp training/qwen15b_lora/output/adapter_model.safetensors models/adapters/qwen15b-lora-v0.1/
   ```

3. **Update checksums** in `metadata.json`:
   ```bash
   python3 docker/scripts/verify_adapter.py models/adapters/qwen15b-lora-v0.1 --update-checksums
   ```

4. **Mount in Complete container**:
   ```bash
   docker run -v $(pwd)/models:/models -e ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1 codi:complete
   ```

## Configuration

The adapter is loaded via environment variables:

- `CODE_MODEL=qwen2.5-coder-1.5b` - Base model identifier
- `ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1` - Path to adapter directory
- `ADAPTER_VERSION=v0.1.0-dev` - Adapter version for tracking

## Fallback

If adapter loading fails, CODI falls back to:
- Base model without adapter (if `CODE_MODEL` supports it)
- Mock LLM server (`core/llm.py` `LocalLLMServer`)
- StarCoder2-3B (if configured via `CODE_MODEL=starcoder2-3b`)

## Training Details

**Dataset**: `codi-dockerfile-pairs-v1` (1000 examples)  
**LoRA Config**:
- Rank: 16
- Alpha: 32
- Dropout: 0.05
- Target modules: q_proj, k_proj, v_proj, o_proj

**Training**:
- Epochs: 3
- Batch size: 4
- Learning rate: 2e-4

## References

- PRD: §7 Local LLM Integration, §10.2 Complete Container
- Tasks: LLM-003 (Training), LLM-004 (Runtime)
- Docs: `/docs/runbook.md`, `/models/README.md`

