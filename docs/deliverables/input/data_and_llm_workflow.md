# Data and LLM Workflow

## Data Lifecycle
- **Collection**: gather Dockerfiles and metadata from repositories, capturing context needed for stack detection and rule matching.
- **Curation and Standardization**: normalize inputs, deduplicate, and enforce quality labels so downstream renders stay deterministic.
- **Synthetic Pair Generation**: create rule-derived before/after examples to enrich coverage beyond collected samples.
- **Splitting and Storage**: maintain structured directories for raw inputs, curated sets, training pairs, and train/validation/test splits to preserve lineage.

## Training and Runtime Enablement
- **Adapter Preparation**: QLoRA-ready configurations and packaged adapters (e.g., `qwen15b-lora-v0.1`) optimized for CPU-friendly runtimes such as llama.cpp or Ollama.
- **Evaluation Artefacts**: `llm_metrics.json` and HTML evaluation harnesses capture ranking quality, rationale clarity, and compatibility labels for templates.
- **Runtime Guardrails**: the LLM ranks candidates and explains rationale while Dockerfile output remains template-rendered; policy checks reject unsafe content.
- **RAG Memory**: a lightweight SQLite index stores embeddings of prior runs to surface similar contexts and improve recommendation relevance.

## Incremental Improvement Loop
- **Performance Measurement**: CPU-only sanity checks record analysis, render, and end-to-end timings to track efficiency over time.
- **Security Verification**: outbound HTTP is blocked by default; allowlists and validation routines ensure air-gapped guarantees during training and inference.
- **Promotion Workflow**: compatibility labels and promotion metadata keep track of which rules are safe to surface with LLM assistance.

## Usage Patterns
- **Local Development**: run CLI commands (`codi run`, `codi report`, `codi perf`) against sample or real projects; artefacts are written under `runs/<timestamp>` for inspection.
- **API Consumption**: invoke FastAPI endpoints for analysis, rewrite, run, report, or LLM ranking to integrate with automation pipelines.
- **Dashboard Sharing**: export datasets with `codi dashboard` and serve the static viewer to communicate optimization impact through cards, summaries, and links to generated reports.

## Outputs that Demonstrate Value
- **Optimization Metrics**: per-run size and layer reductions, timing statistics, and CMD rewrite summaries that quantify improvement.
- **Explainability**: Markdown and HTML reports include human-readable rationales, environment configuration snapshots, and RAG-sourced similar runs.
- **Model Lineage**: adapter versioning and configuration metadata accompany LLM outputs to simplify auditing and comparison across iterations.
