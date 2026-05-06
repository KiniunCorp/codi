# CODI Dashboard How-To

This guide demonstrates how to explore CODI optimisation runs via a lightweight dashboard. It ships with curated example artefacts for all three demo stacks (Node/Next.js, Python/FastAPI, Java/Spring Boot), a CLI aggregation workflow, and a static HTML viewer that can be hosted from any filesystem.

## 1. Snapshot of Included Assets

- Sample runs (full artefacts) for each stack: `docs/examples/dashboard/{node_demo,python_demo,java_demo}`
- Aggregated dataset generated from the samples: `docs/dashboard/data/sample_runs.json`
- Static dashboard bundle: `docs/dashboard/index.html`, `dashboard.js`, `styles.css`
- CLI support for exporting dashboard data: `codi dashboard`

The sample runs include:

| Stack | Directory | Highlights |
| --- | --- | --- |
| Node/Next.js | `docs/examples/dashboard/node_demo` | Candidate `node_nextjs_alpine_runtime` reduces image size by ~35% with air-gap + LLM assist enabled. |
| Python/FastAPI | `docs/examples/dashboard/python_demo` | Candidate `python_fastapi_wheels` switches to wheels workflow, shaving ~32% off size. |
| Java/Spring Boot | `docs/examples/dashboard/java_demo` | Candidate `java_springboot_jre21` multi-stage build cuts image size by ~28%. |

Each sample directory is self-contained and includes `inputs/`, `candidates/`, `metadata/`, and pre-rendered `reports/report.{md,html}` for offline viewing.

## 2. Generate Dashboard Data from Your Own Runs

1. Execute CODI runs as usual. For the demo apps:

   ```bash
   python3 -m cli.main run demo/node --out runs/demo
   python3 -m cli.main run demo/python --out runs/demo
   python3 -m cli.main run demo/java --out runs/demo
   ```

2. Aggregate the runs into a dashboard dataset:

   ```bash
   python3 -m cli.main dashboard --runs runs/demo --export-json runs/dashboard.json --relative-to docs/dashboard
   ```

   This command scans all run folders under `runs/demo`, computes per-stack improvements, and writes a JSON payload that matches the schema consumed by the static dashboard. A Rich summary table is printed to the terminal for quick inspection.

3. (Optional) Store the dataset under `docs/dashboard/data/` if you want to ship or archive it alongside documentation. When exporting into `docs/dashboard/data/`, re-run the command with `--relative-to docs/dashboard` so report links remain browsable from the static viewer.

## 3. View the Dashboard

1. Serve or open `docs/dashboard/index.html`. For local previews:

   ```bash
   python3 -m http.server --directory docs/dashboard 8001
   ```

2. In your browser, navigate to `http://127.0.0.1:8001`. By default the dashboard loads the bundled sample dataset (`data/sample_runs.json`).

3. To point the dashboard at another dataset, append a `?data=` query string with an absolute or relative path that the browser can reach. Example:

   ```text
   http://127.0.0.1:8001/index.html?data=../runs/dashboard.json
   ```

   When hosting the dashboard remotely (e.g. on S3, GitHub Pages), ensure CORS rules permit the JSON fetch.

## 4. Understanding the Dashboard

- **Dataset Overview**: Displays the originating runs root, count, and timestamp from the JSON payload.
- **Stack Improvements**: Aggregates the average delta in size (%) and build time (seconds) per stack. The “Best Run” and “Best Rule” columns help triage which candidate delivered the largest improvement.
- **Run Cards**: Each card surfaces original vs best candidate metrics, assist summary, and quick links to Markdown/HTML reports. Environment tags (`airgap`, `llm`) illuminate which safeguards were active.

The viewer is intentionally dependency-free—everything runs client-side via vanilla JavaScript so it can be hosted from static storage.

## 5. Reproducing the Sample Artefacts

The bundled samples were generated with:

```bash
python3 -m cli.main run demo/node --out docs/examples/dashboard/runs
python3 -m cli.main run demo/python --out docs/examples/dashboard/runs
python3 -m cli.main run demo/java --out docs/examples/dashboard/runs

# Copy the most recent run per stack into named folders
python3 - <<'PY'
from pathlib import Path
import shutil

root = Path('docs/examples/dashboard')
source_root = root / 'runs'

def copy_latest(stack: str) -> None:
    matches = sorted(source_root.glob(f"*-{stack}-*"))
    target = root / f"{stack}_demo"
    if not matches:
        raise SystemExit(f"No runs found for {stack}")
    latest = matches[-1]
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(latest, target)

for stack in ('node', 'python', 'java'):
    copy_latest(stack)
PY

# Render reports for each copied run
python3 - <<'PY'
from pathlib import Path
from core.report import generate_report
base = Path('docs/examples/dashboard')
for name in ('node_demo', 'python_demo', 'java_demo'):
    generate_report(base / name)
PY

# Export dashboard dataset with relative paths for the static viewer
python3 -m cli.main dashboard \
  --runs docs/examples/dashboard \
  --export-json docs/dashboard/data/sample_runs.json \
  --relative-to docs/dashboard
```

> **Tip:** If you maintain your own helper to copy runs, ensure `metadata/run.json` stores Dockerfile paths relative to the copied directory (`inputs/Dockerfile`, `candidates/*.Dockerfile`) so report generation works without referencing the original run folder.

## 6. Definition of Done Checklist

- [x] Dashboard CLI command available (`codi dashboard`).
- [x] Sample run directories committed for all three stacks with markdown + HTML reports.
- [x] Static dashboard bundle renders sample dataset without additional tooling.
- [x] Documentation covers generation, visualisation, and reproduction steps.

For deeper architectural context consult `docs/codi_mvp_prd.md` and acceptance criteria in `docs/codi_mvp_tasks.md` (`CODI-MVP-025`).
