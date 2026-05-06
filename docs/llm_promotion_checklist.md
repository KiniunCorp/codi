# LLM Promotion Checklist

This document codifies how evaluator wins are promoted into the deterministic
rule catalog. Follow this checklist whenever new adapters or templates are ready
to ship so that `patterns/rules.yml` stays aligned with offline metrics and the
security guardrails newly enforced in `core.security`.

## 1. Run the evaluation harness
1. Mount the adapters you intend to validate (default:
   `models/adapters/qwen15b-lora-v0.1`).
2. Execute `make eval-llm` (or `python3 -m eval.eval_suite`) against the demo
   projects to refresh `eval/metrics/*` and `eval/reports/llm_eval.html`.
3. Capture the run identifier (e.g. `20251125_0245`) and inspect the HTML
   dashboard for:
   - Win rate per rule (`win_rate` column)
   - Average size/layer deltas
   - Adapter/version metadata embedded in the report header

## 2. Prepare a promotion proposal
1. Record the adapter version and checksum from
   `models/adapters/<adapter>/metadata.json`.
2. Export the relevant metrics into a short note (see the template in this file).
3. Diff the rendered candidates and reports to ensure the template edit is
   limited to deterministic sections (no raw Dockerfile fragments).

## 3. Update `patterns/rules.yml`
1. Insert compatibility labels/env tags inside the affected rule template:
   `LABEL codi.rule_id=...`, `LABEL codi.ruleset_version=...`,
   `ENV CODI_RULESET_VERSION=...`.
2. Append a new entry under `llm_assist.promotions` with:
   - `id`: stable identifier (e.g. `LLM-PROMO-YYYYMMDD-STACK`)
   - `rule_id`: must match an existing rule
   - `adapter_version`: matches metadata
   - `promoted_at`: ISO8601 timestamp
   - `metrics`: `eval_run`, `eval_report`, `sample_size`, `win_rate`,
     `avg_size_delta_mb`, `avg_layer_delta`
   - `guardrails`: 
     - `allowed_instructions`: copy/paste the exact Docker instructions that
       changed (first token must be `RUN|ENV|LABEL|...` to satisfy
       `core.security.ensure_instruction_allowlist`)
     - `rationale_tags`: free-form descriptors that reporters can reference
3. If the adapter compatibility matrix changes, add/modify an entry under
   `llm_assist.compatibility_matrix.adapters`.

## 4. Validate guardrails
1. Run `python3 -m pytest tests/test_rules.py tests/test_security.py`.
2. The new `core.security.ensure_instruction_allowlist` will raise a clear error
   if a promotion attempts to introduce a token that is not already present in
   codified templates.
3. Inspect `runs/<id>/metadata/llm_metrics.json` after `codi run` to confirm the
   `ruleset_version` label matches the promotion entry.

## 5. Document and merge
1. Update `docs/mvp_estimates.md` and `docs/codi_mvp_tasks.md` with the new
   promotion identifier, adapter version, and completion time.
2. Reference this checklist (or paste it into the PR description) so reviewers
   can trace metrics back to the evaluator run.
3. Ship the PR only after reviewers confirm:
   - The promotion metrics align with `eval/reports/llm_eval.html`
   - No disallowed instructions bypass the allowlist
   - Compatibility tags (`LABEL codi.*`) appear in the rendered Dockerfiles

## Promotion note template

```
Promotion: <LLM-PROMO-ID> / <rule_id>
Adapter  : <adapter_version> (checksum <sha256>)
Eval run : <eval_run> / <eval_report>
Metrics  : win_rate=<0.xx>, Δsize=<MB>, Δlayers=<n>, sample_size=<n>
Guardrail delta:
- <allowed_instruction line 1>
- <allowed_instruction line 2>
```

Store this snippet alongside the PR to keep the provenance discoverable.
