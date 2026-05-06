# CODI Rules & Template Guide

CODI’s deterministic behaviour comes from the rules catalog stored in `patterns/rules.yml`. This guide explains the catalog structure, template anatomy, CMD rewrite integration, and how to extend the system with new rules.

## 1. Catalog Structure

The YAML file is organised by stack. Each rule entry typically contains:

```yaml
node:
  - id: node_nextjs_alpine_runtime
    name: Node.js Next.js Alpine Runtime
    description: >-
      Multi-stage build promoting deps to builder and stripping dev packages.
    stages:
      builder:
        base: node:20-slim
      runtime:
        base: node:20-alpine
    template: templates/node/next_alpine.jinja
    cmd_rewrite: cmd_catalog/node_default
    metadata:
      requires_llm: false
      compatibility: ["nextjs"]
```

### Key Fields
- `id`: unique identifier referenced in CLI/API output and reports.
- `description`: human-readable summary inserted into logs and dashboards.
- `stages`: builder/runtime base images and metadata.
- `template`: Jinja2 file loaded by renderer.
- `cmd_rewrite`: reference to CMD rewrite catalog entry.
- `metadata`: compatibility flags, security requirements, or gating conditions.

## 2. Template Anatomy

Templates are stored alongside the YAML file. Example snippet:

```
# syntax=docker/dockerfile:1
ARG NODE_VERSION=20-slim
FROM node:${NODE_VERSION} AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next ./.next
# ...
```

Renderer variables available in Jinja templates:

| Variable | Description |
| --- | --- |
| `context.stack` | Detected stack metadata. |
| `context.analysis.smells` | List of smells for conditional logic. |
| `context.cmd_summary` | CMD rewrite metadata. |
| `context.rule.id`, `context.rule.name` | Current rule info. |
| `context.runtime` / `context.builder` | Stage configuration. |

Avoid dynamic logic that could break determinism; templates should only use shipped variables and simple conditionals.

## 3. Restricted Instructions & Policy Notes

`patterns/rules.yml` contains allowlists for instructions that require explicit rationale (e.g., `curl`, `sudo`). Renderer injects policy notes into reports when such instructions are used.

## 4. CMD Rewrite Catalog

Located under the `cmd_rewrites` section. Each entry defines how to convert shell-form commands, promote runtime installs, and document rationale.

Example:

```yaml
cmd_rewrites:
  node_default:
    summary: Convert "npm run start" shell wrapper to exec form.
    conversions:
      - match: ["npm", "run", "start"]
        replacement: ["node", "server.js"]
    promotions:
      - pattern: "npm install"
        destination: builder
        note: "Moves npm install to builder stage for deterministic builds."
```

Renderer calls `build_cmd_runtime_summary` to produce report-ready text describing what changed.

## 5. Supported Stacks

### 5.1 Node.js / Next.js
- Rules emphasise multi-stage builds, Alpine runtimes, and Next.js asset promotion.
- CMD rewrites convert shell scripts to exec form for Next.js start scripts.

### 5.2 Python / FastAPI
- Rules promote wheel builds (`pip wheel`), handle `uvicorn` entrypoints, and convert to exec form.
- Template ensures build dependencies are removed from runtime stage.

### 5.3 Java / Spring Boot
- Uses Maven builder stage to compile applications then copies JAR into `eclipse-temurin:21-jre` runtime.
- CMD rewrites replace `java -jar` shell wrappers with exec form while preserving flags.

## 6. LLM Assist Promotions

`llm_assist` section documents which rules are LLM-aware. Each entry records adapter version, promotion timestamp, evaluation run, and report anchor. Example (timestamps quoted to keep YAML parser strict):

```yaml
llm_assist:
  promotions:
    - id: LLM-PROMO-20251125-NODE
      rule_id: node_nextjs_alpine_runtime
      adapter_version: qwen15b-lora-v0.1
      promoted_at: "2025-11-25T04:12:00Z"
      metrics:
        eval_run: eval/runs/20251125_0245
        eval_report: eval/reports/llm_eval.html#20251125_0245
        win_rate: 0.61
```

This data appears in reports and dashboards so operators can trace which adapter informed recommendations.

## 7. Adding a New Rule

1. **Create Template**: Add `templates/<stack>/<rule>.jinja` describing desired Dockerfile.
2. **Define YAML entry** in `patterns/rules.yml` with metadata, builder/runtime images, environment variables, and `cmd_rewrite` reference.
3. **Update CMD rewrite** if new runtime behaviour is required.
4. **Add Tests**: Extend `tests/test_render.py` or stack-specific tests to cover new rule.
5. **Document**: Update `RULES_GUIDE.md` (this file) and mention new rule in `REFERENCE.md`.

### Validation Checklist
- Template builds without network during runtime stages.
- Stage names align with analyzer expectations (`builder`, `runtime`).
- Security allowlists cover any potentially sensitive commands.
- CMD rewrites include rationale text.

## 8. Custom Rules

To experiment with custom rules without modifying the catalog:

1. Copy `patterns/rules.yml` to a new file.
2. Set `RULES_PATH=/path/to/custom_rules.yml` or pass `--rules-path` to CLI/API.
3. Run `codi run` to test the new template.
4. Because templates reference repo files, ensure custom rules include absolute or relative template paths.

## 9. Testing Rules

- `python -m pytest tests/test_rules.py` validates catalog schema and compatibility constraints.
- `tests/test_render.py` ensures templates render correctly for demo projects.
- `tests/test_cmd_parser.py` and `tests/test_cmd_rewrite` (future) cover CMD logic.

## 10. Reporting Integration

Reporter surfaces rule metadata in multiple places:
- Candidate summary table includes rule ID and description.
- Environment section lists `CODI_RULESET_VERSION` label emitted by templates.
- Markdown diffs highlight comments inserted by templates (rationale, stage notes).

## Related Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) for how rules integrate with other modules.
- [CLI_GUIDE.md](./CLI_GUIDE.md) for how rule metadata surfaces in user workflows.
- [LLM_MODULE.md](./LLM_MODULE.md) for adapter promotions tied to rules.
- [REFERENCE.md](./REFERENCE.md) for formal schema definitions.
