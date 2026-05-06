# CODI Data Pipeline

This directory contains the data collection and preparation pipeline for training CODI's local LLM enhancement module.

## Overview

The pipeline transforms raw Dockerfiles from GitHub into curated training pairs suitable for fine-tuning a code instruction model:

```
GitHub → Raw Collection → Labeling → Standardization → Pair Generation → Train/Val/Test Splits
```

## Directory Structure

```
data/
├── raw/              # Raw collected Dockerfiles + metadata
│   ├── logs/         # Collection logs
│   ├── scripts/      # Extracted CMD/ENTRYPOINT scripts
│   └── labels/       # Quality labels (smells, metrics)
├── curated/          # Standardized, deduplicated Dockerfiles
├── pairs/            # Training pairs (instruction-input-output)
└── splits/           # Train/val/test splits (JSONL)
```

## Pipeline Scripts

### 1. `collect_github.py` — Raw Data Collection

Collects diverse Dockerfiles from GitHub with provenance metadata.

**Usage:**
```bash
# Requires GITHUB_TOKEN environment variable
export GITHUB_TOKEN="your_github_token"

# Collect 500 Dockerfiles
python3 data/collect_github.py --count 500 --output data/raw/

# Filter by stack
python3 data/collect_github.py --stack node --count 200 --output data/raw/

# Dry-run (test without API calls)
python3 data/collect_github.py --dry-run
```

**Outputs:**
- `data/raw/*.Dockerfile` — Collected Dockerfiles
- `data/raw/*.Dockerfile.meta.json` — Provenance metadata (repo, URL, SHA, stack hint)
- `data/raw/manifest.json` — Collection summary
- `data/raw/stats.json` — Stack distribution

**Features:**
- Rate limit handling
- Stack detection (Node, Python, Java)
- Compose file detection
- Checksums for deduplication

### 2. `extract_cmd_scripts.py` — CMD/ENTRYPOINT Script Extraction

Extracts shell scripts referenced in CMD/ENTRYPOINT instructions.

**Usage:**
```bash
# Extract scripts (requires GITHUB_TOKEN for repo fetching)
python3 data/extract_cmd_scripts.py --input data/raw/ --output data/raw/scripts/

# Without token (uses placeholders)
python3 data/extract_cmd_scripts.py --input data/raw/ --output data/raw/scripts/
```

**Outputs:**
- `data/raw/scripts/<dockerfile_id>/*.sh` — Extracted scripts
- `data/raw/scripts/extraction_summary.json` — Summary with fetch stats

### 3. `label_smells.py` — Quality Labeling

Labels Dockerfiles with quality metrics, smells, and CMD flags using CODI's analyzer.

**Usage:**
```bash
# Label using CODI analyzer
python3 data/label_smells.py --input data/raw/ --output data/raw/labels/

# With hadolint (if installed)
python3 data/label_smells.py --input data/raw/ --output data/raw/labels/ --use-hadolint
```

**Outputs:**
- `data/raw/labels/labels.jsonl` — JSONL with labels per file
- `data/raw/labels/labeling_summary.json` — Quality distribution

**Label Schema:**
```json
{
  "file": "path/to/file.Dockerfile",
  "stack": "node",
  "smells": ["latest_tag", "shell_form_cmd"],
  "cmd_flags": {
    "uses_shell_form": true,
    "installs_packages": false
  },
  "security_issues": [],
  "quality_score": 0.75,
  "hadolint_codes": ["DL3008", "DL3009"]
}
```

### 4. `standardize.py` — Dataset Standardization

Normalizes, deduplicates, and filters Dockerfiles into curated dataset.

**Usage:**
```bash
python3 data/standardize.py --input data/raw/ --output data/curated/
```

**Outputs:**
- `data/curated/*.Dockerfile` — Normalized Dockerfiles
- `data/curated/*.meta.json` — Metadata with quality info
- `data/curated/index.json` — Dataset index
- `data/curated/standardization_report.txt` — Readable report

**Filtering:**
- Removes duplicates (semantic hash-based)
- Filters test/example files (< 500 bytes)
- Filters low quality (score < 0.2)
- Validates structure (requires FROM + ≥3 instructions)

### 5. `synth_pairs_from_rules.py` — Training Pair Generation

Generates instruction-output pairs from CODI rules and analyzer outputs.

**Usage:**
```bash
python3 data/synth_pairs_from_rules.py \
  --curated data/curated/ \
  --output data/pairs/ \
  --rules patterns/rules.yml
```

**Outputs:**
- `data/pairs/training_pairs.jsonl` — Training pairs (JSONL)
- `data/pairs/pair_generation_stats.json` — Generation stats

**Pair Types:**
1. **Rewrite Task** — Generate optimized candidates from original Dockerfile
2. **Ranking Task** — Rank multiple candidates by quality
3. **Explanation Task** — Explain changes and benefits

**Pair Schema:**
```json
{
  "id": "abc123_rewrite",
  "instruction": "Optimize this node Dockerfile addressing: latest_tag, shell_form_cmd",
  "input": {
    "dockerfile": "FROM node:latest...",
    "stack": "node",
    "smells": ["latest_tag", "shell_form_cmd"],
    "cmd_flags": {"uses_shell_form": true}
  },
  "output": {
    "reasoning": ["Applied multi-stage build", "Converted to exec-form"],
    "candidates": [{
      "name": "optimized",
      "dockerfile": "FROM node:20-slim AS builder...",
      "rationale": "Applied node multi-stage | Converted CMD to exec-form"
    }],
    "recommendations": ["Generated 1 optimized candidate(s)"]
  },
  "metadata": {
    "task": "rewrite",
    "stack": "node"
  }
}
```

### 6. `split_dataset.py` — Train/Val/Test Splitting

Splits training pairs with stratification by stack.

**Usage:**
```bash
python3 data/split_dataset.py \
  --input data/pairs/training_pairs.jsonl \
  --output data/splits/ \
  --train-ratio 0.7 \
  --val-ratio 0.15 \
  --test-ratio 0.15 \
  --seed 42
```

**Outputs:**
- `data/splits/train.jsonl` — Training set
- `data/splits/val.jsonl` — Validation set
- `data/splits/test.jsonl` — Test set
- `data/splits/stats.json` — Split statistics
- `data/splits/split_report.txt` — Readable report

**Features:**
- Stratification by stack (maintains stack distribution)
- Deterministic splitting (fixed seed)
- Leakage verification (ensures no ID overlap)

## Makefile Targets

Convenient one-command workflows:

```bash
# Full pipeline (standardize → pair generation → splitting)
make data-prepare       # Incremental mode (default, fast)
make data-prepare-full  # Full reprocessing (use when rules change)

# Individual steps
make data-collect       # Collect from GitHub (requires GITHUB_TOKEN)
make data-extract       # Extract CMD scripts
make data-label         # Label quality metrics
make data-split         # Split into train/val/test

# Cleanup
make data-clean         # Remove all generated data
```

**Note:** `data-prepare` uses incremental processing by default. See [Incremental Processing](../docs/INCREMENTAL_PROCESSING.md) for details.

## Example Workflow

### Complete Pipeline (Local)

```bash
# 1. Set up environment
export GITHUB_TOKEN="ghp_your_token_here"
make setup  # Install dependencies

# 2. Collect raw data
make data-collect

# 3. Extract scripts
make data-extract

# 4. Label with quality metrics
make data-label

# 5. Prepare training dataset
make data-prepare
```

### Quick Test (Dry-run)

```bash
# Test collection without API calls
python3 data/collect_github.py --dry-run

# Test with existing demo data
python3 data/label_smells.py --input demo/ --output /tmp/labels/
```

## Dataset Statistics

Expected outputs from a 500-Dockerfile collection:

| Metric | Expected Value |
|--------|---------------|
| Raw collected | 500 |
| After standardization | 300-400 (duplicates removed) |
| Training pairs | 600-1200 (2-3 pairs per Dockerfile) |
| Train set | ~70% |
| Val set | ~15% |
| Test set | ~15% |

## Data Quality

### Filtering Criteria

- **Duplicate removal** — Semantic hash-based (ignores comments/whitespace)
- **Minimum size** — ≥50 bytes, ≥3 instructions
- **Quality score** — ≥0.2 (filters severely broken Dockerfiles)
- **Structure** — Must have `FROM` instruction and start with valid pattern
  - Accepts: `FROM`, `ARG` (before FROM), or comments (before FROM)
  - Rejects: Invalid instructions, GitHub issues, non-Dockerfile content
  - See [Dockerfile Validation](../docs/DOCKERFILE_VALIDATION.md) for details

### Invalid File Handling

Files that fail structural validation are marked with `.invalid.json` markers and automatically skipped in subsequent runs. This improves incremental processing performance by ~9.5x for unchanged datasets.

### Label Distribution

Common smells in collected data:
- `latest_tag` — ~40% of Dockerfiles
- `shell_form_cmd` — ~30%
- `apt_no_clean` — ~25%
- `root_user` — ~20%

## Integration with Training

Generated datasets feed into the training pipeline:

```bash
# Training data ready at:
data/splits/train.jsonl     # For fine-tuning
data/splits/val.jsonl       # For validation
data/splits/test.jsonl      # For evaluation
```

**Next Steps:**
- QLoRA training config → `training/qwen15b_lora/`
- Runtime integration → `docker/Dockerfile.complete`

## Troubleshooting

### GitHub Rate Limits

```bash
# Check rate limit status
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit
```

Rate limits:
- **Unauthenticated:** 60 requests/hour
- **Authenticated:** 5000 requests/hour
- **Search API:** 30 requests/minute (authenticated)

Solution: Use a GitHub token and add delays between requests.

### Missing Dependencies

```bash
# Install requests if missing
pip install requests>=2.31.0

# Verify imports
python3 -c "import requests; print('OK')"
```

### Small Dataset

If collection yields < 100 files:
1. Check token validity
2. Increase `--count` parameter
3. Remove stack filter (`--stack`)
4. Check logs in `data/raw/logs/`

## Security & Privacy

- **No outbound calls** during labeling (air-gapped operation)
- **Anonymization** — No secrets/credentials in collected data
- **Checksums** — All files verified for integrity
- **Deterministic** — Fixed seeds ensure reproducible splits

## Contributing

To extend the pipeline:

1. **New smells** — Add patterns to `label_smells.py::SMELL_PATTERNS`
2. **New pair types** — Extend `synth_pairs_from_rules.py::PairGenerator`
3. **Custom filters** — Modify `standardize.py::filter_quality`

## References

- PRD: `docs/codi_mvp_prd.md` §7 (LLM Integration)
- Tasks: `docs/codi_mvp_tasks.md` (LLM-001, LLM-002)
- Estimates: `archive/pre-public-cleanup/docs/wave-notes/mvp_estimates.md` (archived)

