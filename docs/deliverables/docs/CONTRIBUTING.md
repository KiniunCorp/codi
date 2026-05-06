# Contributing to CODI

This guide explains how to propose changes, add new stacks or rules, extend the LLM pipeline, and maintain code quality.

## 1. Development Workflow

1. Fork or clone the repository.
2. Create a feature branch (`git checkout -b feature/<topic>`).
3. Run `make setup` to install dependencies.
4. Implement changes with accompanying tests.
5. Run `make lint` and `make test`.
6. Update relevant documentation under `docs/deliverables/docs/`.
7. Submit a pull request with a clear description and testing evidence.

## 2. Coding Standards

| Area | Standard |
| --- | --- |
| Formatting | Black (line length 100) via `make format`. |
| Imports | Ruff handles sorting (`ruff check --select I --fix`). |
| Linting | Ruff configured in `pyproject.toml`. |
| Types | mypy with strict settings for core modules. |
| Documentation | Markdown in `docs/`; reference other docs with relative links. |

## 3. Git Hygiene

- Keep commits focused; prefer small logical units.
- Reference issues or tasks in commit messages if applicable.
- Rebase on latest `main` before opening PRs to avoid merge conflicts.

## 4. Adding a New Stack or Rule

1. Extend detector/analyzer if new stack heuristics are required.
2. Author Jinja template under `patterns/templates/<stack>/`.
3. Add rule entry to `patterns/rules.yml` with metadata and CMD rewrite reference.
4. Update tests (`tests/test_render.py`, `tests/test_rules.py`) to cover new rule.
5. Document changes in `RULES_GUIDE.md` and `REFERENCE.md`.

## 5. Enhancing the LLM Pipeline

- Update dataset scripts under `data/` when adding new smells or instructions.
- Modify training configs or notebooks in `training/qwen15b_lora/`.
- Package adapters with checksums and metadata; update `patterns/rules.yml` promotions.
- Record evaluation runs under `eval/` and mention them in `LLM_MODULE.md`.

## 6. Testing Requirements

- New modules require unit tests; CI should run `make test` before merging.
- For CLI/API changes, add or update tests in `tests/test_cli.py` / `tests/test_api.py`.
- Performance-sensitive changes should include `codi perf` results in PR description.

## 7. Documentation Expectations

- All user-facing changes must update relevant docs (e.g., CLI commands → `CLI_GUIDE.md`).
- Keep terminology consistent (Slim container, Complete container, adapter, rules catalog).
- Mention new environment variables or file formats in `REFERENCE.md`.

## 8. Review Checklist

- [ ] Code formatted and linted.
- [ ] Tests added/updated and passing.
- [ ] Documentation updated.
- [ ] No stray debug prints or secrets.
- [ ] Release considerations noted (if applicable).

## 9. Communication

- Use descriptive PR titles (“Add Python 3.13 detection support”).
- Include reproduction steps for bug fixes.
- Attach generated reports or metrics when relevant.

## Related Documentation

- [TESTING.md](./TESTING.md) for required coverage.
- [PERFORMANCE.md](./PERFORMANCE.md) for benchmarks to include in PRs.
- [RULES_GUIDE.md](./RULES_GUIDE.md) when editing templates.
- [LLM_MODULE.md](./LLM_MODULE.md) when touching adapters or runtime integration.
