SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python

.PHONY: help setup lint format test build-slim build-complete run-slim run-slim-cli run-slim-api test-slim clean \
        data-collect data-extract data-label data-prepare data-prepare-full data-split data-clean \
        data-sync-r2 data-sync-r2-dry-run data-sync-r2-splits data-sync-r2-colab \
        data-download-r2 data-download-r2-colab data-download-r2-all data-download-r2-dry-run \
        train-lora train-lora-dry-run train-lora-resume llm-runtime llm-runtime-test

help: ## Show available make targets.
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

setup: ## Create a local virtual environment and install dependencies.
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e .[dev]

lint: ## Run static analysis (Ruff and Black in check mode).
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .

format: ## Format code using Ruff (imports) and Black.
	$(VENV)/bin/ruff check --select I --fix .
	$(VENV)/bin/black .

test: ## Execute the Python test suite.
	$(VENV)/bin/pytest

build-slim: ## Build the Slim CODI container image.
	docker build -f docker/Dockerfile.slim -t codi:slim .

build-complete: ## Build the Complete CODI container image.
	docker build -f docker/Dockerfile.complete -t codi:complete .

run-slim: ## Run the Slim container API server (default).
	docker run --rm -it -v "$(PWD)":/work -p 8000:8000 codi:slim

run-slim-cli: ## Run the Slim container with CLI access (override entrypoint).
	docker run --rm -it -v "$(PWD)":/work codi:slim /bin/bash

run-slim-api: ## Same as run-slim, explicitly starts the API server.
	docker run --rm -it -v "$(PWD)":/work -p 8000:8000 codi:slim

test-slim: ## Test the Slim container with demo/node project.
	@echo "Testing Slim container build..."
	@docker run --rm -v "$(PWD)":/work codi:slim codi all demo/node --dry-run || echo "Build test requires demo apps"

clean: ## Remove local caches, build artifacts, and the virtual environment.
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info runs/

# --- Release & Publishing (Wave 18) ---

REGISTRY ?= docker.io
IMAGE_NAMESPACE ?= guschiriboga
RELEASE_VERSION ?= dev

release-images: ## Build Slim & Complete images tagged for release (loads into local Docker).
	@echo "Building release images (version: $(RELEASE_VERSION))"
	@REGISTRY=$(REGISTRY) IMAGE_NAMESPACE=$(IMAGE_NAMESPACE) \
		RELEASE_VERSION=$(RELEASE_VERSION) PUSH=false \
		docker/scripts/release_images.sh

publish-images: ## Build and push Slim & Complete images (set RELEASE_VERSION, registry login required).
	@if [ -z "$(RELEASE_VERSION)" ] || [ "$(RELEASE_VERSION)" = "dev" ]; then \
		echo "❌ Set RELEASE_VERSION=vX.Y.Z when publishing images."; \
		exit 1; \
	fi
	@echo "Publishing release images to $(REGISTRY)/$(IMAGE_NAMESPACE) (version: $(RELEASE_VERSION))"
	@REGISTRY=$(REGISTRY) IMAGE_NAMESPACE=$(IMAGE_NAMESPACE) \
		RELEASE_VERSION=$(RELEASE_VERSION) PUSH=true \
		docker/scripts/release_images.sh

# --- Data Pipeline Targets (LLM Wave) ---

data-collect: ## Collect Dockerfiles from GitHub (requires GITHUB_TOKEN).
	$(PYTHON_BIN) data/collect_github.py --count 500 --output data/raw/

data-extract: ## Extract CMD/ENTRYPOINT scripts from collected Dockerfiles.
	$(PYTHON_BIN) data/extract_cmd_scripts.py --input data/raw/ --output data/raw/scripts/

data-label: ## Label Dockerfiles with quality metrics and smells.
	$(PYTHON_BIN) data/label_smells.py --input data/raw/ --output data/raw/labels/

data-prepare: ## Standardize, generate pairs, and split dataset (incremental mode).
	@echo "=== Running data preparation pipeline (incremental mode) ==="
	@echo "=== Standardizing raw data ==="
	$(PYTHON_BIN) data/standardize.py --input data/raw/ --output data/curated/
	@echo "=== Generating training pairs ==="
	$(PYTHON_BIN) data/synth_pairs_from_rules.py --curated data/curated/ --output data/pairs/
	@echo "=== Splitting into train/val/test ==="
	$(PYTHON_BIN) data/split_dataset.py --input data/pairs/training_pairs.jsonl --output data/splits/
	@echo "=== Data preparation complete ==="

data-prepare-full: ## Reprocess all data (disable incremental mode).
	@echo "=== Running data preparation pipeline (full mode) ==="
	@echo "=== Standardizing raw data ==="
	$(PYTHON_BIN) data/standardize.py --input data/raw/ --output data/curated/ --full
	@echo "=== Generating training pairs ==="
	$(PYTHON_BIN) data/synth_pairs_from_rules.py --curated data/curated/ --output data/pairs/ --full
	@echo "=== Splitting into train/val/test ==="
	$(PYTHON_BIN) data/split_dataset.py --input data/pairs/training_pairs.jsonl --output data/splits/ --full
	@echo "=== Data preparation complete (full reprocessing) ==="

data-split: ## Split training pairs into train/val/test sets (incremental).
	$(PYTHON_BIN) data/split_dataset.py --input data/pairs/training_pairs.jsonl --output data/splits/

data-clean: ## Remove all generated data (raw, curated, pairs, splits).
	rm -rf data/raw/* data/curated/* data/pairs/* data/splits/*
	@echo "Data directories cleaned (structure preserved)"

# --- R2 Storage Targets ---

data-sync-r2: ## Upload all data directories to R2 (includes colab-zip-files).
	$(PYTHON_BIN) data/sync_to_r2.py --directories raw,curated,pairs,splits,colab-zip-files

data-sync-r2-dry-run: ## Test R2 sync without uploading (dry-run mode).
	$(PYTHON_BIN) data/sync_to_r2.py --directories raw,curated,pairs,splits,colab-zip-files --dry-run

data-sync-r2-splits: ## Upload only training splits to R2 (for Colab).
	$(PYTHON_BIN) data/sync_to_r2.py --directories splits

data-sync-r2-colab: ## Upload colab-zip-files to R2 (for distribution).
	$(PYTHON_BIN) data/sync_to_r2.py --directories colab-zip-files

data-download-r2: ## Download training datasets from R2 (splits only).
	$(PYTHON_BIN) data/download_from_r2.py --datasets splits --output data/

data-download-r2-colab: ## Download colab-zip-files from R2.
	$(PYTHON_BIN) data/download_from_r2.py --datasets colab-zip-files --output data/

data-download-r2-all: ## Download all datasets from R2.
	$(PYTHON_BIN) data/download_from_r2.py --datasets all --output data/

data-download-r2-dry-run: ## Test R2 download without downloading (dry-run mode).
	$(PYTHON_BIN) data/download_from_r2.py --datasets splits --dry-run

# --- Training Targets (LLM Wave) ---

train-lora: ## Train QLoRA adapter for Qwen2.5-Coder-1.5B (requires GPU).
	$(PYTHON_BIN) training/qwen15b_lora/train.py --config training/qwen15b_lora/config.yaml

train-lora-dry-run: ## Validate training environment without training (dry-run mode).
	$(PYTHON_BIN) training/qwen15b_lora/train.py --config training/qwen15b_lora/config.yaml --dry-run

train-lora-resume: ## Resume training from latest checkpoint.
	@CHECKPOINT=$$(ls -td training/qwen15b_lora/checkpoints/checkpoint-* 2>/dev/null | head -1); \
	if [ -z "$$CHECKPOINT" ]; then \
		echo "❌ No checkpoint found in training/qwen15b_lora/checkpoints/"; \
		exit 1; \
	fi; \
	echo "Resuming from $$CHECKPOINT"; \
	$(PYTHON_BIN) training/qwen15b_lora/train.py --config training/qwen15b_lora/config.yaml --resume-from "$$CHECKPOINT"

train-colab-zip: ## Create ZIP file for Google Colab training (essential files only).
	@echo "=== Creating Colab training ZIP (essential files) ==="
	@if [ ! -f data/splits/train.jsonl ]; then \
		echo "❌ Training data not found. Run 'make data-prepare' first."; \
		exit 1; \
	fi
	@$(PYTHON_BIN) training/qwen15b_lora/create_colab_zip.py
	@echo "✅ ZIP file created successfully!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Upload ZIP from data/colab-zip-files/ to Google Colab"
	@echo "  2. Open training/qwen15b_lora/train_colab.ipynb"
	@echo "  3. Follow instructions in notebook cells"

train-colab-zip-full: ## Create ZIP file for Colab with optional files (test data, notebooks).
	@echo "=== Creating Colab training ZIP (full, with optional files) ==="
	@if [ ! -f data/splits/train.jsonl ]; then \
		echo "❌ Training data not found. Run 'make data-prepare' first."; \
		exit 1; \
	fi
	@$(PYTHON_BIN) training/qwen15b_lora/create_colab_zip.py --full
	@echo "✅ ZIP file created successfully!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Upload ZIP from data/colab-zip-files/ to Google Colab"
	@echo "  2. Open training/qwen15b_lora/train_colab.ipynb"
	@echo "  3. Follow instructions in notebook cells"

# --- LLM Runtime Targets (Wave LLM-3) ---

llm-runtime: ## Validate LLM runtime start/stop (dry-run, no network required).
	@echo "=== Testing Local LLM Server Start/Stop ==="
	@echo "Starting LLM server in background..."
	@$(PYTHON_BIN) -c "from core.llm import LocalLLMServer, LocalLLMConfig; \
		from pathlib import Path; \
		import os; \
		import time; \
		config = LocalLLMConfig( \
			host='127.0.0.1', \
			port=8082, \
			code_model=os.getenv('CODE_MODEL', 'qwen2.5-coder-1.5b'), \
			adapter_path=Path(os.getenv('ADAPTER_PATH', 'models/adapters/qwen15b-lora-v0.1')), \
			adapter_version=os.getenv('ADAPTER_VERSION', 'unknown') \
		); \
		server = LocalLLMServer(config); \
		print('Starting server...'); \
		server.start(); \
		print(f'✅ Server started at {server.base_url}'); \
		health = server.health_check(); \
		print(f'✅ Health check passed: {health}'); \
		time.sleep(0.5); \
		server.stop(); \
		print('✅ Server stopped cleanly')"
	@echo ""
	@echo "=== Runtime validation passed ==="

llm-runtime-test: ## Run LLM runtime integration tests.
	@echo "=== Running LLM Runtime Tests ==="
	$(VENV)/bin/pytest tests/test_llm.py -v -k "test_server or test_config"
	@echo "✅ LLM runtime tests passed"

eval-llm: ## Run LLM evaluation harness on demo projects (offline).
	$(PYTHON_BIN) eval/eval_suite.py --output eval

