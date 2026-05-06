#!/bin/bash
# Script to create a ZIP file for Google Colab training
# Creates: codi-YYYYMMDD.zip or codi-YYYYMMDD-full.zip in data/colab-zip-files/

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the repository root (assumes script is in training/qwen15b_lora/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CODI Colab Training ZIP Creator${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d)

# Check for --full flag
SUFFIX=""
if [ "$1" == "--full" ]; then
    SUFFIX="-full"
fi

# Create output directory
OUTPUT_DIR="${REPO_ROOT}/data/colab-zip-files"
mkdir -p "${OUTPUT_DIR}"

ZIP_NAME="codi-${TIMESTAMP}${SUFFIX}.zip"
ZIP_PATH="${OUTPUT_DIR}/${ZIP_NAME}"

# Temporary directory for staging
TEMP_DIR=$(mktemp -d)
STAGING_DIR="${TEMP_DIR}/codi"

echo -e "${GREEN}Repository root:${NC} ${REPO_ROOT}"
echo -e "${GREEN}Output file:${NC} ${ZIP_PATH}"
echo -e "${GREEN}Staging directory:${NC} ${STAGING_DIR}"
echo ""

# Create staging directory structure
mkdir -p "${STAGING_DIR}/data/splits"
mkdir -p "${STAGING_DIR}/training/qwen15b_lora"
mkdir -p "${STAGING_DIR}/patterns"

echo -e "${BLUE}Copying files...${NC}"

# Essential files
echo -e "  ${GREEN}✓${NC} Copying training data..."
cp "${REPO_ROOT}/data/splits/train.jsonl" "${STAGING_DIR}/data/splits/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  train.jsonl not found"
cp "${REPO_ROOT}/data/splits/val.jsonl" "${STAGING_DIR}/data/splits/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  val.jsonl not found"

echo -e "  ${GREEN}✓${NC} Copying training scripts and config..."
cp "${REPO_ROOT}/training/qwen15b_lora/config.yaml" "${STAGING_DIR}/training/qwen15b_lora/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  config.yaml not found"
cp "${REPO_ROOT}/training/qwen15b_lora/train.py" "${STAGING_DIR}/training/qwen15b_lora/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  train.py not found"

# Recommended files
echo -e "  ${GREEN}✓${NC} Copying recommended files..."
cp "${REPO_ROOT}/patterns/rules.yml" "${STAGING_DIR}/patterns/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  rules.yml not found"
cp "${REPO_ROOT}/data/splits/stats.json" "${STAGING_DIR}/data/splits/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  stats.json not found"
cp "${REPO_ROOT}/training/qwen15b_lora/README.md" "${STAGING_DIR}/training/qwen15b_lora/" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠${NC}  README.md not found"

# Optional files
if [ "$1" == "--full" ]; then
    echo -e "  ${GREEN}✓${NC} Including optional files (--full mode)..."
    cp "${REPO_ROOT}/data/splits/test.jsonl" "${STAGING_DIR}/data/splits/" 2>/dev/null || \
        echo -e "  ${YELLOW}⚠${NC}  test.jsonl not found"
    cp "${REPO_ROOT}/README.md" "${STAGING_DIR}/" 2>/dev/null || \
        echo -e "  ${YELLOW}⚠${NC}  Root README.md not found"
    cp "${REPO_ROOT}/training/qwen15b_lora/train_colab.ipynb" "${STAGING_DIR}/training/qwen15b_lora/" 2>/dev/null || \
        echo -e "  ${YELLOW}⚠${NC}  train_colab.ipynb not found"
fi

echo ""

# Create the ZIP file
echo -e "${BLUE}Creating ZIP archive...${NC}"
cd "${TEMP_DIR}"
zip -r "${ZIP_PATH}" codi/ -q

# Calculate size
ZIP_SIZE=$(du -h "${ZIP_PATH}" | cut -f1)

# Cleanup
rm -rf "${TEMP_DIR}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ ZIP file created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}File:${NC} ${ZIP_PATH}"
echo -e "${GREEN}Size:${NC} ${ZIP_SIZE}"
echo ""

# List contents
echo -e "${BLUE}Contents:${NC}"
unzip -l "${ZIP_PATH}" | grep -E "codi/(data|training|patterns|README)" | awk '{print "  " $4}'
echo ""

# Statistics
TOTAL_FILES=$(unzip -l "${ZIP_PATH}" | grep -c "codi/")
echo -e "${BLUE}Statistics:${NC}"
echo -e "  Total files: ${TOTAL_FILES}"

# Check train.jsonl size
if [ -f "${REPO_ROOT}/data/splits/train.jsonl" ]; then
    TRAIN_LINES=$(wc -l < "${REPO_ROOT}/data/splits/train.jsonl")
    echo -e "  Training examples: ${TRAIN_LINES}"
fi

if [ -f "${REPO_ROOT}/data/splits/val.jsonl" ]; then
    VAL_LINES=$(wc -l < "${REPO_ROOT}/data/splits/val.jsonl")
    echo -e "  Validation examples: ${VAL_LINES}"
fi

echo ""
echo -e "${BLUE}Usage:${NC}"
echo -e "  1. Upload ${ZIP_NAME} to Google Colab"
echo -e "  2. Extract with: files.upload() then unzip"
echo -e "  3. Or directly in notebook cell 7 (Option A)"
echo ""
echo -e "${YELLOW}Options:${NC}"
echo -e "  Run with ${GREEN}--full${NC} flag to include test.jsonl and notebooks"
echo -e "  Example: ./create_colab_zip.sh --full"
echo ""

