# CODI QLoRA Training

This directory contains configuration and scripts for training a LoRA adapter for Qwen2.5-Coder-1.5B to rank and explain Dockerfile optimizations.

## Overview

- **Base Model:** Qwen/Qwen2.5-Coder-1.5B-Instruct (quantized 4-bit)
- **Method:** QLoRA (4-bit quantization + LoRA adapters)
- **Target:** Dockerfile optimization candidate ranking and rationale generation
- **Output:** `qwen15b-lora-v0.1` adapter (<400 MB)

## Quick Start

### Prerequisites

```bash
# Install training dependencies
pip install transformers>=4.36.0 peft>=0.7.0 bitsandbytes>=0.41.0 \
            datasets>=2.16.0 accelerate>=0.25.0 trl>=0.7.0 tensorboard
```

**Hardware Requirements:**
- **Minimum:** 8 GB VRAM (e.g., RTX 3070, T4)
- **Recommended:** 16 GB VRAM (e.g., RTX 4080, A100)
- **CPU Training:** Supported but extremely slow

**Platform Notes:**
- `bitsandbytes` requires Linux or WSL (not macOS)
- BFloat16 requires Ampere+ GPUs (RTX 30xx/40xx, A100, etc.)

### 1. Prepare Training Data

```bash
# From repo root
make data-prepare
```

This will:
1. Standardize raw Dockerfiles
2. Generate training pairs from rules
3. Split into train/val/test sets

Output: `data/splits/train.jsonl`, `data/splits/val.jsonl`, `data/splits/test.jsonl`

### 2. Validate Environment (Dry-Run)

```bash
python training/qwen15b_lora/train.py --dry-run
```

This checks:
- Dependencies installed
- Dataset files present
- GPU/CUDA availability
- Estimated VRAM usage

### 3. Start Training

```bash
# Local training
python training/qwen15b_lora/train.py

# Or via Makefile
make train-lora
```

**Expected Duration:**
- T4 GPU: ~2-3 hours (3 epochs)
- RTX 3090: ~1-1.5 hours
- A100 GPU: ~30-45 minutes

**Monitoring:**
```bash
# TensorBoard
tensorboard --logdir training/qwen15b_lora/logs
```

### 4. Resume from Checkpoint (Optional)

```bash
python training/qwen15b_lora/train.py \
  --resume-from training/qwen15b_lora/checkpoints/checkpoint-500
```

## Configuration

All hyperparameters are defined in [`config.yaml`](./config.yaml):

### Key Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| **LoRA rank (r)** | 16 | Balance between capacity and size |
| **LoRA alpha** | 32 | Typically 2× rank |
| **Dropout** | 0.05 | Regularization |
| **Target modules** | q/k/v/o_proj, gate/up/down_proj | Attention + MLP |
| **Epochs** | 3 | Avoid overfitting |
| **Batch size** | 1 | Per-device |
| **Grad accumulation** | 16 | Effective batch size = 16 |
| **Learning rate** | 2e-4 | Standard for QLoRA |
| **Max seq length** | 4096 | Fits Dockerfile + context |
| **Optimizer** | paged_adamw_8bit | Memory-efficient |

### Hardware Estimates

With 4-bit quantization + LoRA r=16:
- Base model: ~3 GB VRAM
- LoRA params: ~50 MB
- Optimizer states: ~2 GB
- Activations: ~3 GB
- **Total:** ~8-10 GB VRAM

## Training on Google Colab

For users without local GPU access:

1. Upload [`train_colab.ipynb`](./train_colab.ipynb) to Google Colab
2. Set Runtime > Change runtime type > GPU (T4)
3. Run cells sequentially
4. Download adapter zip at completion

**Colab Tips:**
- Use Colab Pro for faster GPUs (A100/V100)
- Enable "High RAM" runtime if available
- Regularly save checkpoints to Google Drive
- Free tier may timeout after ~12 hours

## Output Artifacts

Training produces the following artifacts in `models/adapters/qwen15b-lora-v0.1/`:

```
models/adapters/qwen15b-lora-v0.1/
├── adapter_config.json       # LoRA configuration
├── adapter_model.bin          # PyTorch adapter weights
├── adapter_model.safetensors # SafeTensors format (preferred)
├── metadata.json              # Training metadata
├── checksums.sha256           # File integrity checksums
├── tokenizer_config.json      # Tokenizer config
├── tokenizer.json             # Tokenizer vocabulary
└── special_tokens_map.json    # Special tokens
```

### Verify Adapter Integrity

```bash
cd models/adapters/qwen15b-lora-v0.1
sha256sum -c checksums.sha256
```

Expected output:
```
adapter_model.bin: OK
adapter_model.safetensors: OK
```

## Exporting to GGUF (Optional)

For deployment with llama.cpp:

```bash
# Install llama.cpp tools
pip install llama-cpp-python

# Convert adapter to GGUF
python -m llama_cpp.convert \
  --model models/adapters/qwen15b-lora-v0.1 \
  --outfile models/adapters/qwen15b-lora-v0.1/adapter.gguf \
  --outtype q4_k_m
```

## Integration with CODI

Once training is complete:

1. **Verify adapter location:**
   ```bash
   ls -lh models/adapters/qwen15b-lora-v0.1/
   ```

2. **Rebuild Complete container:**
   ```bash
   make build-complete
   ```

3. **Test with LLM endpoints:**
   ```bash
   docker run -v $PWD:/work codi:complete codi llm rank \
     --candidates runs/<ts>/candidates/*.Dockerfile
   ```

4. **Check adapter version in logs:**
   ```bash
   docker logs <container-id> | grep "adapter_version"
   ```

## Troubleshooting

### Out of Memory (OOM)

**Solutions:**
1. Reduce `per_device_train_batch_size` to 1
2. Increase `gradient_accumulation_steps` to maintain effective batch size
3. Reduce `max_seq_length` from 4096 to 2048
4. Enable gradient checkpointing (trades compute for memory):
   ```yaml
   training:
     gradient_checkpointing: true
   ```

### Training is slow

**Check:**
1. GPU utilization: `nvidia-smi` should show ~90%+ usage
2. DataLoader workers: Increase `dataloader_num_workers` if CPU-bound
3. Mixed precision: Ensure `bf16: true` for Ampere+ GPUs

### Loss not decreasing

**Try:**
1. Increase `warmup_ratio` from 0.05 to 0.1
2. Reduce `learning_rate` from 2e-4 to 1e-4
3. Check dataset quality: Ensure pairs are diverse and correctly formatted
4. Monitor train/val loss divergence (overfitting)

### bitsandbytes not available (macOS)

**Workaround:**
- Use Google Colab or cloud GPU instance (Linux)
- macOS users: Train on cloud, download adapter for local inference

### Adapter size exceeds 400 MB

**Reduce:**
1. Lower LoRA rank: `r: 8` instead of `r: 16`
2. Fewer target modules: Remove MLP projections
3. Use SafeTensors format (typically smaller than .bin)

## Advanced: Hyperparameter Tuning

### Experiment Tracking

Use W&B or MLflow for experiment tracking:

```bash
pip install wandb
wandb login

# Update config.yaml
training:
  report_to: "wandb"
  run_name: "qwen15b-lora-experiment-01"
```

### Grid Search

Common parameters to tune:
- `lora_r`: [8, 16, 32]
- `lora_alpha`: [16, 32, 64]
- `learning_rate`: [1e-4, 2e-4, 5e-4]
- `num_train_epochs`: [2, 3, 5]

### Learning Rate Finder

```python
from transformers.trainer_utils import get_last_checkpoint
from torch.optim.lr_scheduler import LambdaLR

# Add to train.py before trainer.train()
lr_finder = trainer.lr_finder()
lr_finder.plot()
```

## References

- [Qwen2.5-Coder Model Card](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct)
- [QLoRA Paper](https://arxiv.org/abs/2305.14314)
- [PEFT Documentation](https://huggingface.co/docs/peft)
- [Transformers Trainer Guide](https://huggingface.co/docs/transformers/main_classes/trainer)

## License

Training scripts and configuration inherit the CODI project license.
Base model (Qwen2.5-Coder) follows its own license terms.

