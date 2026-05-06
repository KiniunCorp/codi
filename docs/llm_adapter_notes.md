# LLM Adapter Notes

This guide centralises adapter metadata, mounting procedures, and verification
commands for the Complete CODI runtime. It complements `models/README.md`,
`docs/runbook.md`, and the promotion workflow documented in
`docs/llm_promotion_checklist.md`.

## 1. Adapter Inventory

| Adapter ID | Ruleset Version | Compatible Rules | Validation Run | Notes |
|------------|----------------|------------------|----------------|-------|
| `qwen15b-lora-v0.1` | `2025.11-llm` | `node_nextjs_alpine_runtime`, `python_fastapi_wheels`, `java_springboot_jre21` | `eval/runs/20251125_0245` (win rate ≥0.61) | Mounted under `/models/adapters/qwen15b-lora-v0.1`; checksum listed below. |

**Checksums**

Compute and record SHA256 sums whenever new weights land:

```bash
shasum -a 256 models/adapters/qwen15b-lora-v0.1/adapter_model.safetensors
shasum -a 256 models/adapters/qwen15b-lora-v0.1/adapter_config.json
```

## 2. Mounting & Verification

```bash
# Create local cache
export MODEL_MOUNT_PATH="$HOME/.codi-models"
mkdir -p "$MODEL_MOUNT_PATH/adapters/qwen15b-lora-v0.1"

# Copy weights (from training output or artifact store)
cp -r training/qwen15b_lora/output/* "$MODEL_MOUNT_PATH/adapters/qwen15b-lora-v0.1/"

# Verify integrity
python3 docker/scripts/verify_adapter.py \
  "$MODEL_MOUNT_PATH/adapters/qwen15b-lora-v0.1"

# Launch Complete runtime with adapter mounted
docker run --rm -it \
  -v "$PWD:/work" \
  -v "$MODEL_MOUNT_PATH/adapters:/models/adapters" \
  -e AIRGAP=true \
  -e LLM_ENABLED=true \
  -e ADAPTER_PATH=/models/adapters/qwen15b-lora-v0.1 \
  -e CODE_MODEL=qwen2.5-coder-1.5b \
  -p 8000:8000 -p 8081:8081 \
  codi:complete
```

Post-launch checks:

1. `docker exec <container> python3 /opt/codi/scripts/verify_adapter.py $ADAPTER_PATH`
2. `curl -s http://localhost:8081/healthz`
3. `python3 -m cli.main llm rank demo/node --out runs/llm-smoke`
4. Inspect `runs/llm-smoke/llm_metrics.json` for `adapter_version`, `ruleset_version`,
   and ranking payloads.

## 3. Required Toggles

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_ENABLED` | Enables LLM-assisted ranking/rationale flows. | `false` in Slim / `true` in Complete |
| `AIRGAP` | Blocks outbound HTTP(S). Keep `true` unless a remote LLM endpoint is explicitly allowlisted. | `true` |
| `ADAPTER_PATH` | Absolute path to mounted adapter directory. | `/models/adapters/qwen15b-lora-v0.1` |
| `CODI_RULESET_VERSION` | Propagated label in rendered templates; ties promotions to adapters. | `2025.11-llm` |
| `LLM_ENDPOINT` | Override to hit an external (still internal) LLM runtime. Requires `AIRGAP_ALLOWLIST`. | `http://127.0.0.1:8081` |

## 4. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Adapter status logs as `not_mounted` | Confirm bind mount path, permissions, and directory spelling. |
| `/llm/rank` returns `llm_disabled` | Ensure `LLM_ENABLED=true` _and_ `ADAPTER_PATH` points to a readable directory. |
| Rank responses missing `ruleset_version` | Rebuild/render after updating `patterns/rules.yml`; confirm templates now include `LABEL codi.ruleset_version`. |
| Promotion validation fails (`ensure_instruction_allowlist`) | Update guardrails in `patterns/rules.yml` to reference only `RUN|ENV|LABEL|...` instructions that exist in templates. |

## 5. Promotion Tie-In

- Every adapter promotion must reference the adapter matrix above and be logged
  in `llm_assist.promotions` within `patterns/rules.yml`.
- Use `docs/llm_promotion_checklist.md` to capture eval metrics, guardrails, and
  timestamps before merging template changes.
- Update `ADAPTER_VERSION` metadata in `models/adapters/<id>/metadata.json`
  whenever weights change so `core.llm.read_adapter_metadata` reports accurate
  versions in CLI/API responses.
