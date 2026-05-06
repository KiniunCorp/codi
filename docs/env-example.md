# Environment Configuration

Copy this configuration to a `.env` file in the project root and fill in your actual values.

```bash
# ===== Cloudflare R2 Configuration =====
# Used for data sync, training data storage, and model distribution

# Your Cloudflare account ID (found in R2 dashboard)
R2_ACCOUNT_ID=your-account-id

# R2 API credentials (generate from Cloudflare dashboard)
R2_ACCESS_KEY_ID=your-access-key-id
R2_SECRET_ACCESS_KEY=your-secret-access-key

# R2 bucket name for CODI training data
R2_BUCKET_NAME=codi-training-data

# R2 endpoint URL (automatically constructed from account ID)
# Format: https://{account-id}.r2.cloudflarestorage.com
R2_ENDPOINT_URL=https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com

# Optional: Custom region for R2 (usually auto)
# R2_REGION=auto

# ===== GitHub API Configuration =====
# Used for data collection from GitHub repositories

# GitHub personal access token (for higher rate limits)
# GITHUB_TOKEN=ghp_your_token_here

# ===== Training Configuration =====
# Optional overrides for training parameters

# TRAINING_OUTPUT_DIR=training/qwen15b_lora/checkpoints
# TRAINING_LOGS_DIR=training/qwen15b_lora/logs

# ===== API Configuration =====
# For running CODI API server

# API_HOST=0.0.0.0
# API_PORT=8000

# ===== LLM Configuration =====
# For LLM-based ranking and explanation

# LLM_PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434
# LLM_MODEL=qwen2.5-coder:1.5b

# ===== Development Configuration =====
# For local development and testing

# LOG_LEVEL=INFO
# DEBUG=false
```

## Setup Instructions

1. **Copy the configuration above** to a new file named `.env` in the project root
2. **Get your R2 credentials** from the Cloudflare dashboard:
   - Go to R2 → Overview → Manage R2 API Tokens
   - Create a new API token with read/write permissions
   - Copy the Account ID, Access Key ID, and Secret Access Key
3. **Create an R2 bucket** named `codi-training-data` (or your preferred name)
4. **Update the `.env` file** with your actual credentials

## Security Notes

- ⚠️ **Never commit `.env` files** to version control
- The `.env` file is already in `.gitignore`
- Keep your R2 credentials secure and rotate them regularly
- Use separate credentials for development and production

