# CODI Reporting & Dashboards

CODI produces structured artefacts for every run, including Markdown and HTML reports, metrics JSON, and dashboard datasets. This guide covers how reports are generated, where to find them, and how to publish dashboards.

## 1. Run Artefact Layout

```
runs/<timestamp>-<stack>-<label>/
├── inputs/
│   └── Dockerfile
├── candidates/
│   ├── candidate_1.Dockerfile
│   └── candidate_2.Dockerfile
├── metadata/
│   ├── run.json
│   ├── metrics.json
│   ├── llm_metrics.json (Complete)
│   ├── environment.json
│   └── rag.json
└── reports/
    ├── report.md
    └── report.html
```

`codi run` populates the entire tree. `codi report` can be re-run at any time to regenerate Markdown/HTML from metadata.

## 2. Report Generation (`core/report.py`)

The reporter ingests the stored metadata and produces two deliverables:

- **Markdown report (`report.md`)** – lightweight, version-control-friendly summary.
- **HTML report (`report.html`)** – handcrafted HTML/CSS for sharing with stakeholders.

### Sections
1. **Executive Summary** – Stack, rule IDs, top-level improvements, command to reproduce run.
2. **Metrics Table** – Estimated size reduction, layer changes, timing, air-gap status.
3. **Candidate Details** – Per-candidate rationale, CMD rewrite summary, policy notes.
4. **CMD Rewrite Summary** – Explanation of shell-form conversions and runtime promotions.
5. **Security Notes** – Highlighted allowlist hits or policy warnings.
6. **LLM Assist (Complete)** – Adapter version, confidence ranking, rationale excerpts.
7. **Environment Snapshot** – Values from `environment.json` (rules path, toggles, output root).
8. **Diffs** – Rendered diffs between original Dockerfile and each candidate.
9. **RAG Insights** – Similar runs retrieved from `runs/_rag`. (Optional)

## 3. Markdown Report Usage

- Ideal for code reviews and Git diffs.
- Can be embedded in docs or ticketing systems.
- Supports copy/paste of rationale comments.

## 4. HTML Report Usage

- Designed for non-technical stakeholders.
- All CSS is inline; no external assets required.
- Works offline; open via double-clicking the file or hosting on static web server.

## 5. Dashboard Workflow

### 5.1 CLI Aggregation

```bash
codi dashboard --runs docs/examples/dashboard \
  --export-json docs/dashboard/data/sample_runs.json \
  --relative-to docs/dashboard
```

- `--runs` points to root containing run directories (can be nested per stack or per project).
- `--relative-to` rewrites report links so they work when serving `docs/dashboard/` statically.
- CLI prints summary tables highlighting average size reductions per stack.

### 5.2 Static Viewer

Files under `docs/dashboard/` comprise a self-contained dashboard:
- `index.html`
- `dashboard.js`
- `styles.css`
- `data/sample_runs.json`

Serve locally via `python -m http.server --directory docs/dashboard 8001` or host on any static site service. Query parameter `?data=` can point the viewer at alternative JSON datasets.

### 5.3 Dataset Schema

Each run entry contains:
- `id`: run directory name.
- `stack`: detected stack.
- `rule_id`: winning rule.
- `metrics`: size/layer deltas, analysis/render timings.
- `environment`: air-gap + LLM flags.
- `reports`: relative or absolute paths to Markdown/HTML files.

Refer to `REFERENCE.md` for the exact schema.

## 6. Sharing Reports

- **Email/Chat**: Attach `report.html` or paste Markdown summary.
- **Documentation portals**: Embed Markdown or host HTML within internal wiki.
- **Dashboards**: Use aggregated JSON to visualise trends for leadership.

## 7. Automation Tips

- Include `runs/<id>/reports/report.html` as build artifact in CI.
- For long-term tracking, push dashboard datasets to object storage (S3/R2).
- Use `environment.json` to ensure runs are comparable (ruleset version, toggles).

## 8. Troubleshooting

| Issue | Resolution |
| --- | --- |
| Report generation fails | Verify `codi report` paths, ensure run directory contains `metadata/` and `candidates/`. |
| HTML references broken | Use `--relative-to` when exporting dashboard data; ensure `reports/` directory exists in final location. |
| Metrics missing | Confirm build runner produced `metrics.json`; rerun `codi run` if file absent. |
| LLM section empty | Set `LLM_ENABLED=true`, ensure adapter is mounted when generating run. |

## Related Documentation

- [CLI_GUIDE.md](./CLI_GUIDE.md) for commands that generate reports.
- [API_GUIDE.md](./API_GUIDE.md) for triggering report generation via HTTP.
- [REFERENCE.md](./REFERENCE.md) for file format schemas referenced in reports.
- [OPERATIONS.md](./OPERATIONS.md) for procedures that rely on generated artefacts.
