#!/bin/bash
# mount_adapter.sh - Helper script to validate and mount LoRA adapters for CODI Complete
#
# Usage: mount_adapter.sh [adapter_dir]
#
# This script:
# 1. Validates the adapter directory structure
# 2. Checks for required files (adapter_config.json, adapter_model.safetensors/bin)
# 3. Verifies checksums if metadata.json exists
# 4. Exports adapter metadata to environment

set -euo pipefail

ADAPTER_DIR="${1:-${ADAPTER_PATH:-/models/adapters/qwen15b-lora-v0.1}}"

echo "[mount_adapter] Validating adapter directory: ${ADAPTER_DIR}"

if [[ ! -d "${ADAPTER_DIR}" ]]; then
    echo "❌ ERROR: Adapter directory not found: ${ADAPTER_DIR}"
    echo "TIP: Mount adapters with: docker run -v /path/to/adapters:/models/adapters codi:complete"
    exit 1
fi

# Check for required adapter files
REQUIRED_FILES=(
    "adapter_config.json"
)

ADAPTER_WEIGHTS=""
if [[ -f "${ADAPTER_DIR}/adapter_model.safetensors" ]]; then
    ADAPTER_WEIGHTS="${ADAPTER_DIR}/adapter_model.safetensors"
elif [[ -f "${ADAPTER_DIR}/adapter_model.bin" ]]; then
    ADAPTER_WEIGHTS="${ADAPTER_DIR}/adapter_model.bin"
fi

for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${ADAPTER_DIR}/${file}" ]]; then
        echo "❌ ERROR: Required file missing: ${file}"
        exit 1
    fi
done

if [[ -z "${ADAPTER_WEIGHTS}" ]]; then
    echo "❌ ERROR: No adapter weights found (adapter_model.safetensors or adapter_model.bin)"
    exit 1
fi

echo "✅ Found adapter weights: $(basename "${ADAPTER_WEIGHTS}")"

# Verify checksums if metadata exists
if [[ -f "${ADAPTER_DIR}/metadata.json" ]]; then
    echo "[mount_adapter] Found metadata.json, verifying checksums..."
    python3 /opt/codi/scripts/verify_adapter.py "${ADAPTER_DIR}"
    ADAPTER_VERSION=$(python3 -c "import json; print(json.load(open('${ADAPTER_DIR}/metadata.json'))['version'])" 2>/dev/null || echo "unknown")
else
    echo "⚠️  WARNING: No metadata.json found, skipping checksum verification"
    ADAPTER_VERSION="unknown"
fi

# Export adapter metadata
export ADAPTER_PATH="${ADAPTER_DIR}"
export ADAPTER_VERSION="${ADAPTER_VERSION}"
export ADAPTER_WEIGHTS="${ADAPTER_WEIGHTS}"

echo "✅ Adapter validated successfully"
echo "   Version: ${ADAPTER_VERSION}"
echo "   Path: ${ADAPTER_PATH}"
echo "   Weights: $(basename "${ADAPTER_WEIGHTS}")"
echo ""

