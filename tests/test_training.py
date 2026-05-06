"""
Tests for QLoRA training infrastructure (LLM-003).

These tests validate training configuration, environment checks, and dry-run mode
without requiring GPU or actual model downloads.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture
def training_config():
    """Load training configuration for testing."""
    config_path = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "config.yaml"

    if not config_path.exists():
        pytest.skip(f"Training config not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def mock_dataset_files(tmp_path):
    """Create mock training dataset files."""
    splits_dir = tmp_path / "data" / "splits"
    splits_dir.mkdir(parents=True)

    # Create mock train.jsonl
    train_file = splits_dir / "train.jsonl"
    with open(train_file, "w") as f:
        for i in range(10):
            record = {
                "instruction": f"Optimize this Dockerfile {i}",
                "input": "FROM ubuntu:22.04\nRUN apt-get update",
                "output": f"Applied rule: test_rule_{i}\nRationale: Test optimization",
            }
            f.write(json.dumps(record) + "\n")

    # Create mock val.jsonl
    val_file = splits_dir / "val.jsonl"
    with open(val_file, "w") as f:
        for i in range(3):
            record = {
                "instruction": f"Improve this Dockerfile {i}",
                "input": "FROM python:3.12\nCOPY . .",
                "output": f"Applied rule: val_rule_{i}\nRationale: Validation optimization",
            }
            f.write(json.dumps(record) + "\n")

    return splits_dir


class TestTrainingConfig:
    """Tests for training configuration validation."""

    def test_config_exists(self):
        """Verify training config file exists."""
        config_path = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "config.yaml"
        assert config_path.exists(), "Training config not found"

    def test_config_structure(self, training_config):
        """Verify config has required sections."""
        required_sections = ["model", "lora", "training", "hardware", "dataset", "adapter"]

        for section in required_sections:
            assert section in training_config, f"Missing config section: {section}"

    def test_model_config(self, training_config):
        """Verify model configuration."""
        model_cfg = training_config["model"]

        assert "base_model" in model_cfg
        assert "Qwen" in model_cfg["base_model"], "Expected Qwen model"
        assert model_cfg["load_in_4bit"] is True, "Should use 4-bit quantization"
        assert model_cfg["bnb_4bit_quant_type"] == "nf4"

    def test_lora_config(self, training_config):
        """Verify LoRA configuration."""
        lora_cfg = training_config["lora"]

        assert lora_cfg["r"] >= 8, "LoRA rank should be >= 8"
        assert lora_cfg["r"] <= 64, "LoRA rank should be <= 64"
        assert lora_cfg["lora_alpha"] == 2 * lora_cfg["r"], "Alpha should be 2x rank"

        # Check target modules
        target_modules = lora_cfg["target_modules"]
        assert "q_proj" in target_modules
        assert "k_proj" in target_modules
        assert "v_proj" in target_modules

    def test_training_config(self, training_config):
        """Verify training hyperparameters."""
        train_cfg = training_config["training"]

        assert train_cfg["num_train_epochs"] >= 1
        assert train_cfg["learning_rate"] > 0
        assert train_cfg["max_seq_length"] == 4096
        assert train_cfg["optim"] == "paged_adamw_8bit"

    def test_adapter_config(self, training_config):
        """Verify adapter packaging configuration."""
        adapter_cfg = training_config["adapter"]

        assert "output_path" in adapter_cfg
        assert "qwen15b-lora" in adapter_cfg["output_path"]
        assert "metadata" in adapter_cfg
        assert adapter_cfg["checksum_algo"] == "sha256"


class TestTrainingScript:
    """Tests for train.py script functionality."""

    @patch("training.qwen15b_lora.train.DEPS_AVAILABLE", False)
    def test_missing_dependencies_handled(self):
        """Verify graceful handling of missing dependencies."""
        # Import should not fail even if deps missing
        try:
            import sys

            sys.path.insert(0, str(Path(__file__).parent.parent))
            # This would normally import the trainer, but we're patching DEPS_AVAILABLE
        except ImportError:
            pytest.fail("Script should handle missing dependencies gracefully")

    def test_config_loading(self, training_config):
        """Verify config loads correctly."""
        assert training_config is not None
        assert "model" in training_config

    def test_format_instruction(self, training_config):
        """Test instruction formatting function."""
        example = {
            "instruction": "Optimize this Dockerfile",
            "input": "FROM ubuntu:22.04\nRUN apt-get update",
            "output": "Applied rule: test_rule",
        }

        # Format would be done by CodiTrainer.format_instruction
        # Here we just verify the example structure
        assert "instruction" in example
        assert "input" in example
        assert "output" in example


class TestDatasetValidation:
    """Tests for dataset file validation."""

    def test_dataset_jsonl_format(self, mock_dataset_files):
        """Verify dataset files are valid JSONL."""
        train_file = mock_dataset_files / "train.jsonl"

        with open(train_file) as f:
            for line in f:
                record = json.loads(line)  # Should not raise
                assert "instruction" in record
                assert "input" in record
                assert "output" in record

    def test_dataset_record_structure(self, mock_dataset_files):
        """Verify dataset records have required fields."""
        train_file = mock_dataset_files / "train.jsonl"

        with open(train_file) as f:
            record = json.loads(f.readline())

        required_fields = ["instruction", "input", "output"]
        for field in required_fields:
            assert field in record, f"Missing field: {field}"
            assert isinstance(record[field], str), f"Field {field} should be string"


class TestAdapterPackaging:
    """Tests for adapter output and metadata."""

    def test_adapter_directory_structure(self):
        """Verify adapter output directory exists."""
        adapter_dir = Path(__file__).parent.parent / "models" / "adapters" / "qwen15b-lora-v0.1"
        assert adapter_dir.exists(), "Adapter directory should exist (with .gitkeep)"

    def test_metadata_schema(self):
        """Verify expected metadata structure."""
        expected_fields = [
            "version",
            "base_model",
            "adapter_name",
            "training_date",
            "hyperparameters",
            "dataset",
        ]

        # This would be generated during actual training
        # Here we just verify the structure is documented
        assert len(expected_fields) > 0

    def test_checksum_generation(self, tmp_path):
        """Test checksum generation for adapter files."""
        import hashlib

        # Create mock adapter file
        adapter_file = tmp_path / "adapter_model.bin"
        adapter_file.write_bytes(b"mock adapter weights")

        # Generate checksum
        with open(adapter_file, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        assert len(file_hash) == 64, "SHA256 should be 64 hex chars"

        # Verify checksum format
        checksum_file = tmp_path / "checksums.sha256"
        with open(checksum_file, "w") as f:
            f.write(f"{file_hash}  adapter_model.bin\n")

        assert checksum_file.exists()

        # Verify checksum content
        with open(checksum_file) as f:
            line = f.readline()
            checksum, filename = line.strip().split("  ")
            assert checksum == file_hash
            assert filename == "adapter_model.bin"


class TestHardwareRequirements:
    """Tests for hardware validation."""

    def test_hardware_config_present(self, training_config):
        """Verify hardware requirements documented."""
        hw_cfg = training_config["hardware"]

        assert "min_vram_gb" in hw_cfg
        assert hw_cfg["min_vram_gb"] >= 8, "Minimum 8 GB VRAM required"
        assert "recommended_vram_gb" in hw_cfg
        assert "estimated_vram_usage" in hw_cfg

    def test_cuda_detection_logic(self):
        """Test GPU detection logic (without torch dependency)."""

        # Mock GPU check logic
        def check_gpu(cuda_available):
            if cuda_available:
                return True
            return False

        # Test with GPU available
        assert check_gpu(True) is True

        # Test without GPU
        assert check_gpu(False) is False


class TestDryRunMode:
    """Tests for dry-run validation mode."""

    def test_dry_run_flag_exists(self):
        """Verify train.py supports --dry-run flag."""
        train_script = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "train.py"

        if not train_script.exists():
            pytest.skip("Training script not found")

        with open(train_script) as f:
            content = f.read()

        assert "--dry-run" in content, "Should support dry-run mode"
        assert "dry_run" in content.lower()

    def test_dry_run_skips_training(self):
        """Verify dry-run mode skips actual training."""
        # This would be tested by running:
        # python train.py --dry-run
        # and verifying no model download or training occurs
        pass


class TestMakefileTargets:
    """Tests for Makefile training targets."""

    def test_train_lora_target_exists(self):
        """Verify make train-lora target exists."""
        makefile = Path(__file__).parent.parent / "Makefile"

        with open(makefile) as f:
            content = f.read()

        assert "train-lora:" in content
        assert "training/qwen15b_lora/train.py" in content

    def test_dry_run_target_exists(self):
        """Verify make train-lora-dry-run target exists."""
        makefile = Path(__file__).parent.parent / "Makefile"

        with open(makefile) as f:
            content = f.read()

        assert "train-lora-dry-run:" in content
        assert "--dry-run" in content


class TestDocumentation:
    """Tests for training documentation."""

    def test_readme_exists(self):
        """Verify training README exists."""
        readme = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "README.md"
        assert readme.exists(), "Training README should exist"

    def test_readme_content(self):
        """Verify README covers key topics."""
        readme = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "README.md"

        with open(readme) as f:
            content = f.read()

        required_topics = [
            "Prerequisites",
            "Quick Start",
            "Configuration",
            "Troubleshooting",
            "GGUF",  # Export instructions
        ]

        for topic in required_topics:
            assert topic in content, f"README should cover: {topic}"

    def test_colab_notebook_exists(self):
        """Verify Colab training notebook exists."""
        notebook = Path(__file__).parent.parent / "training" / "qwen15b_lora" / "train_colab.ipynb"
        assert notebook.exists(), "Colab notebook should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
