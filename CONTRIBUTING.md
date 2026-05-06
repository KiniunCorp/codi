# Contributing to CODI

## Prerequisites

- Python 3.12+
- Docker 24+ with BuildKit (for container workflows)
- Make
- git

## Setup

```bash
git clone https://github.com/KiniunCorp/codi.git
cd codi
make setup              # create .venv and install all dev dependencies
source .venv/bin/activate
codi --version          # verify the install
```

`make setup` creates `.venv/`, upgrades pip, and installs CODI in editable mode (`pip install -e .[dev]`).

## Development workflow

- One branch per change, branched from `main`.
- Run `make lint && make test` before opening a PR.
- Open a PR against `main` with a `feat:`, `fix:`, `docs:`, or `chore:` prefix in the title.

## Running checks

```bash
make lint    # Ruff + Black in check mode
make test    # full pytest suite

# Individual steps
python3 -m ruff check .
python3 -m black --check .
python3 -m pytest --ignore=tests/test_training.py --ignore=tests/test_data_pipeline.py
```

## Versioning policy

Every PR that changes product code (anything under `core/`, `cli/`, `api/`, `patterns/`, `docker/`) must:

1. Bump the `version` field in `pyproject.toml`.
2. Add an entry to `CHANGELOG.md` under the new version heading.

PRs that only touch documentation, workflows, or test fixtures do not require a version bump unless the change alters observable CLI or API behaviour.

## Opening issues

Use the GitHub issue templates:
- **Bug report** — for unexpected behaviour or errors.
- **Feature request** — for new capabilities or improvements.

## Security

Do not open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## Code of conduct

This project follows the Contributor Covenant. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
