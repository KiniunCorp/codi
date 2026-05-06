# CODI Documentation Index

Welcome to the CODI documentation suite. Use this index to navigate the collection based on your role or task.

## 1. Getting Started

| Topic | Description |
| --- | --- |
| [INTRODUCTION.md](./INTRODUCTION.md) | Product overview, key capabilities, and personas. |
| [INSTALLATION.md](./INSTALLATION.md) | Prerequisites, setup commands, troubleshooting. |
| [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) | Cheat sheet for commands, env vars, and make targets. |

## 2. Architecture & Stack

| Topic | Description |
| --- | --- |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System diagram, module deep dive, deployment models. |
| [TECH_STACK.md](./TECH_STACK.md) | Languages, dependencies, containers, CI/CD tooling. |

## 3. Usage Guides

| Topic | Description |
| --- | --- |
| [CLI_GUIDE.md](./CLI_GUIDE.md) | Command usage, workflows, environment flags. |
| [SLIM_CONTAINER.md](./SLIM_CONTAINER.md) | Building/running rules-only container. |
| [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) | Embedded LLM runtime, adapter mounts, health checks. |
| [API_GUIDE.md](./API_GUIDE.md) | FastAPI endpoints, schemas, examples. |

## 4. Advanced Components

| Topic | Description |
| --- | --- |
| [LLM_MODULE.md](./LLM_MODULE.md) | Data pipeline, training, runtime integration, evaluation. |
| [RULES_GUIDE.md](./RULES_GUIDE.md) | Rules catalog structure, template authoring, CMD rewrites. |
| [REPORTING.md](./REPORTING.md) | Report artefacts, dashboard workflows. |

## 5. Operations & Security

| Topic | Description |
| --- | --- |
| [OPERATIONS.md](./OPERATIONS.md) | Day-2 procedures, health checks, troubleshooting. |
| [SECURITY.md](./SECURITY.md) | Air-gap controls, container hardening, compliance artefacts. |
| [CICD_RELEASE.md](./CICD_RELEASE.md) | Release steps, signing, SBOMs, rollback plans. |

## 6. Quality & Contribution

| Topic | Description |
| --- | --- |
| [PERFORMANCE.md](./PERFORMANCE.md) | Performance budgets, `codi perf`, optimisation tips. |
| [TESTING.md](./TESTING.md) | pytest suites, fixtures, coverage expectations. |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Development workflow, coding standards, review checklist. |

## 7. Reference Materials

| Topic | Description |
| --- | --- |
| [REFERENCE.md](./REFERENCE.md) | Command/API reference, file formats, glossary, roadmap. |

## 8. Role-Based Paths

| Role | Suggested Path |
| --- | --- |
| Platform Engineer | INTRODUCTION → ARCHITECTURE → CLI_GUIDE → SLIM_CONTAINER → CICD_RELEASE. |
| DevOps/SRE | INSTALLATION → OPERATIONS → SECURITY → PERFORMANCE → REPORTING. |
| ML Engineer | LLM_MODULE → DATA pipeline sections → COMPLETE_CONTAINER → REFERENCE. |
| Product/Leadership | INTRODUCTION → REPORTING → DASHBOARD sections → REFERENCE summaries. |

## Related Documentation

- [DEPRECATION_NOTICE.md](./DEPRECATION_NOTICE.md) for legacy-to-new mapping.
- [REFERENCE.md](./REFERENCE.md) when you need schema-level details beyond the index.
- [OPERATIONS.md](./OPERATIONS.md) for ongoing maintenance linked to these docs.
