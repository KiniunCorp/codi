#!/usr/bin/env python3
"""
CODI QLoRA Training Script
Trains a LoRA adapter for Qwen2.5-Coder-1.5B on Dockerfile optimization pairs.

Usage:
    python train.py --config config.yaml [--dry-run] [--resume-from checkpoint]
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Conditional imports - handle gracefully for dry-run mode
try:
    import torch
    from datasets import load_dataset
    from peft import (
        LoraConfig,
        get_peft_model,
        prepare_model_for_kbit_training,
    )
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
    )

    DEPS_AVAILABLE = True
except ImportError as e:
    DEPS_AVAILABLE = False
    IMPORT_ERROR = str(e)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class CodiTrainer:
    """Handles QLoRA training for CODI Dockerfile optimization."""

    def __init__(self, config_path: str, dry_run: bool = False):
        self.config_path = Path(config_path)
        self.dry_run = dry_run
        self.config = self._load_config()
        self.repo_root = self._find_repo_root()

    def _find_repo_root(self) -> Path:
        """Find repository root by looking for patterns/rules.yml."""
        current = Path.cwd()
        while current != current.parent:
            if (current / "patterns" / "rules.yml").exists():
                return current
            current = current.parent
        return Path.cwd()  # Fallback to current directory

    def _load_config(self) -> dict[str, Any]:
        """Load and validate training configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        logger.info(f"✓ Loaded config from {self.config_path}")
        return config

    def validate_environment(self) -> bool:
        """Validate training environment and dependencies."""
        logger.info("=== Environment Validation ===")

        # Check dependencies
        if not DEPS_AVAILABLE:
            logger.error(f"❌ Missing dependencies: {IMPORT_ERROR}")
            logger.error(
                "Install with: pip install transformers peft bitsandbytes datasets accelerate"
            )
            return False

        logger.info("✓ Dependencies available")

        # Check dataset files
        train_path = self.repo_root / self.config["training"]["train_data"]
        val_path = self.repo_root / self.config["training"]["val_data"]

        if not train_path.exists():
            logger.error(f"❌ Training data not found: {train_path}")
            logger.error("Run: make data-prepare")
            return False

        if not val_path.exists():
            logger.warning(f"⚠️  Validation data not found: {val_path}")

        logger.info(f"✓ Training data: {train_path}")
        logger.info(f"✓ Validation data: {val_path}")

        # Check CUDA availability
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info(f"✓ GPU detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")

            min_vram = self.config["hardware"]["min_vram_gb"]
            if vram_gb < min_vram:
                logger.warning(f"⚠️  VRAM below minimum ({min_vram} GB). Training may fail.")
        else:
            logger.warning("⚠️  No CUDA GPU detected. Training will be slow on CPU.")

        # Check bitsandbytes availability (required for QLoRA)
        try:
            import bitsandbytes

            logger.info(f"✓ bitsandbytes {bitsandbytes.__version__}")
        except ImportError:
            logger.error("❌ bitsandbytes not available. QLoRA requires bitsandbytes.")
            logger.error("Note: bitsandbytes requires Linux/WSL (not macOS)")
            return False

        return True

    def prepare_datasets(self):
        """Load and prepare training/validation datasets."""
        logger.info("=== Preparing Datasets ===")

        train_path = str(self.repo_root / self.config["training"]["train_data"])
        val_path = str(self.repo_root / self.config["training"]["val_data"])

        # Load JSONL datasets
        dataset_dict = {}
        dataset_dict["train"] = load_dataset("json", data_files=train_path, split="train")

        if Path(val_path).exists():
            dataset_dict["validation"] = load_dataset("json", data_files=val_path, split="train")

        logger.info(f"✓ Train examples: {len(dataset_dict['train'])}")
        if "validation" in dataset_dict:
            logger.info(f"✓ Validation examples: {len(dataset_dict['validation'])}")

        return dataset_dict

    def load_model_and_tokenizer(self):
        """Load base model with 4-bit quantization and tokenizer."""
        logger.info("=== Loading Model ===")

        model_name = self.config["model"]["base_model"]
        logger.info(f"Base model: {model_name}")

        # Configure 4-bit quantization
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=self.config["model"]["load_in_4bit"],
            bnb_4bit_compute_dtype=getattr(torch, self.config["model"]["bnb_4bit_compute_dtype"]),
            bnb_4bit_quant_type=self.config["model"]["bnb_4bit_quant_type"],
            bnb_4bit_use_double_quant=self.config["model"]["bnb_4bit_use_double_quant"],
        )

        # Load model
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )

        # Prepare for k-bit training
        model = prepare_model_for_kbit_training(model)

        logger.info("✓ Model loaded with 4-bit quantization")

        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True,
        )

        # Set padding token if not present
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            model.config.pad_token_id = model.config.eos_token_id

        logger.info("✓ Tokenizer loaded")

        return model, tokenizer

    def apply_lora(self, model):
        """Apply LoRA configuration to model."""
        logger.info("=== Applying LoRA ===")

        lora_config = LoraConfig(
            r=self.config["lora"]["r"],
            lora_alpha=self.config["lora"]["lora_alpha"],
            lora_dropout=self.config["lora"]["lora_dropout"],
            target_modules=self.config["lora"]["target_modules"],
            bias=self.config["lora"]["bias"],
            task_type=self.config["lora"]["task_type"],
        )

        model = get_peft_model(model, lora_config)

        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in model.parameters())

        logger.info(
            f"✓ LoRA applied (r={self.config['lora']['r']}, alpha={self.config['lora']['lora_alpha']})"
        )
        logger.info(
            f"  Trainable params: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)"
        )
        logger.info(f"  Total params: {total_params:,}")

        return model

    def format_instruction(self, example: dict[str, str]) -> str:
        """Format training example into instruction prompt."""
        instruction = example.get("instruction", "")
        input_text = example.get("input", "")
        output_text = example.get("output", "")

        # CODI-specific prompt format
        prompt = f"""### Instruction:
{instruction}

### Input:
{input_text}

### Output:
{output_text}"""

        return prompt

    def preprocess_function(self, examples, tokenizer):
        """Tokenize examples for training."""
        texts = [self.format_instruction(ex) for ex in examples]

        model_inputs = tokenizer(
            texts,
            max_length=self.config["training"]["max_seq_length"],
            truncation=True,
            padding="max_length",
        )

        # Clone input_ids to labels (causal LM training)
        model_inputs["labels"] = model_inputs["input_ids"].copy()

        return model_inputs

    def train(self, resume_from: str | None = None):
        """Execute training loop."""
        logger.info("=== Starting Training ===")

        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - Validation only, no training")
            return

        # Load datasets
        datasets = self.prepare_datasets()

        # Load model and tokenizer
        model, tokenizer = self.load_model_and_tokenizer()

        # Apply LoRA
        model = self.apply_lora(model)

        # Tokenize datasets
        logger.info("Tokenizing datasets...")
        tokenized_datasets = {
            split: ds.map(
                lambda examples: self.preprocess_function(examples, tokenizer),
                batched=True,
                remove_columns=ds.column_names,
            )
            for split, ds in datasets.items()
        }

        # Training arguments
        output_dir = str(self.repo_root / self.config["training"]["output_dir"])

        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=self.config["training"]["num_train_epochs"],
            per_device_train_batch_size=self.config["training"]["per_device_train_batch_size"],
            per_device_eval_batch_size=self.config["training"]["per_device_eval_batch_size"],
            gradient_accumulation_steps=self.config["training"]["gradient_accumulation_steps"],
            learning_rate=self.config["training"]["learning_rate"],
            lr_scheduler_type=self.config["training"]["lr_scheduler_type"],
            warmup_ratio=self.config["training"]["warmup_ratio"],
            weight_decay=self.config["training"]["weight_decay"],
            max_grad_norm=self.config["training"]["max_grad_norm"],
            optim=self.config["training"]["optim"],
            evaluation_strategy=self.config["training"]["evaluation_strategy"],
            eval_steps=self.config["training"]["eval_steps"],
            save_strategy=self.config["training"]["save_strategy"],
            save_steps=self.config["training"]["save_steps"],
            save_total_limit=self.config["training"]["save_total_limit"],
            logging_steps=self.config["training"]["logging_steps"],
            logging_dir=str(self.repo_root / self.config["training"]["logging_dir"]),
            fp16=self.config["training"]["fp16"],
            bf16=self.config["training"]["bf16"],
            seed=self.config["training"]["seed"],
            dataloader_num_workers=self.config["training"]["dataloader_num_workers"],
            remove_unused_columns=self.config["training"]["remove_unused_columns"],
            group_by_length=self.config["training"]["group_by_length"],
            report_to="tensorboard",
        )

        # Initialize trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_datasets["train"],
            eval_dataset=tokenized_datasets.get("validation"),
        )

        # Resume from checkpoint if specified
        checkpoint = None
        if resume_from:
            checkpoint = resume_from
            logger.info(f"Resuming from checkpoint: {checkpoint}")

        # Train!
        logger.info("🚀 Training started...")
        trainer.train(resume_from_checkpoint=checkpoint)

        logger.info("✅ Training complete!")

        # Save final adapter
        self.save_adapter(model, tokenizer)

    def save_adapter(self, model, tokenizer):
        """Save trained adapter with metadata."""
        logger.info("=== Saving Adapter ===")

        adapter_dir = self.repo_root / self.config["adapter"]["output_path"]
        adapter_dir.mkdir(parents=True, exist_ok=True)

        # Save adapter weights
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))

        logger.info(f"✓ Adapter saved to {adapter_dir}")

        # Generate metadata
        metadata = self._generate_metadata()
        metadata_path = adapter_dir / "metadata.json"

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"✓ Metadata saved to {metadata_path}")

        # Generate checksums
        self._generate_checksums(adapter_dir)

    def _generate_metadata(self) -> dict[str, Any]:
        """Generate adapter metadata."""
        train_data_path = self.repo_root / self.config["training"]["train_data"]

        # Count training examples
        num_examples = 0
        if train_data_path.exists():
            with open(train_data_path) as f:
                num_examples = sum(1 for _ in f)

        # Get git commit (if available)
        dataset_commit = "unknown"
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
            )
            if result.returncode == 0:
                dataset_commit = result.stdout.strip()[:8]
        except Exception:
            pass

        # Get rules version
        rules_version = "unknown"
        rules_path = self.repo_root / "patterns" / "rules.yml"
        if rules_path.exists():
            with open(rules_path, "rb") as f:
                rules_hash = hashlib.sha256(f.read()).hexdigest()[:8]
                rules_version = rules_hash

        metadata = {
            "version": self.config["adapter"]["metadata"]["version"],
            "base_model": self.config["model"]["base_model"],
            "adapter_name": self.config["model"]["adapter_name"],
            "training_date": datetime.utcnow().isoformat() + "Z",
            "dataset_commit": dataset_commit,
            "rules_version": rules_version,
            "hyperparameters": {
                "lora_r": self.config["lora"]["r"],
                "lora_alpha": self.config["lora"]["lora_alpha"],
                "lora_dropout": self.config["lora"]["lora_dropout"],
                "target_modules": self.config["lora"]["target_modules"],
                "num_epochs": self.config["training"]["num_train_epochs"],
                "learning_rate": self.config["training"]["learning_rate"],
                "effective_batch_size": (
                    self.config["training"]["per_device_train_batch_size"]
                    * self.config["training"]["gradient_accumulation_steps"]
                ),
            },
            "dataset": {
                "num_train_examples": num_examples,
                "train_data": self.config["training"]["train_data"],
                "val_data": self.config["training"]["val_data"],
            },
        }

        return metadata

    def _generate_checksums(self, adapter_dir: Path):
        """Generate SHA256 checksums for adapter files."""
        checksums = {}

        for file in adapter_dir.glob("*.bin"):
            with open(file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
                checksums[file.name] = file_hash

        for file in adapter_dir.glob("*.safetensors"):
            with open(file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
                checksums[file.name] = file_hash

        checksum_path = adapter_dir / "checksums.sha256"
        with open(checksum_path, "w") as f:
            for filename, checksum in sorted(checksums.items()):
                f.write(f"{checksum}  {filename}\n")

        logger.info(f"✓ Checksums saved to {checksum_path}")


def main():
    parser = argparse.ArgumentParser(description="CODI QLoRA Training")
    parser.add_argument(
        "--config",
        type=str,
        default="training/qwen15b_lora/config.yaml",
        help="Path to training config YAML",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate environment without training",
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        help="Resume training from checkpoint",
    )

    args = parser.parse_args()

    # Initialize trainer
    trainer = CodiTrainer(args.config, dry_run=args.dry_run)

    # Validate environment
    if not trainer.validate_environment():
        logger.error("❌ Environment validation failed")
        sys.exit(1)

    if args.dry_run:
        logger.info("✅ Dry-run complete. Environment is ready for training.")
        sys.exit(0)

    # Run training
    trainer.train(resume_from=args.resume_from)

    logger.info("🎉 Training pipeline complete!")


if __name__ == "__main__":
    main()
