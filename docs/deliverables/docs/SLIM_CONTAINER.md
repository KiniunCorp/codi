# CODI Slim Container Guide

The Slim container packages the rules-first CLI and FastAPI service without bundling an LLM runtime. Use it for local evaluations, CI pipelines, or environments that require air-gapped execution.

## 1. Image Overview

- **Dockerfile**: `docker/Dockerfile.slim`
- **Base image**: `python:3.12-slim`
- **User**: non-root `codi`
- **Exposed port**: 8000 (FastAPI)
- **Entrypoint**: `uvicorn api.server:app`
- **Volume**: `/work` (mounted to host project root)
- **Air-gap defaults**: `AIRGAP=true`, `LLM_ENABLED=false`

## 2. Build Instructions

```bash
make build-slim
# or
docker build -f docker/Dockerfile.slim -t codi:slim .
```

## 3. Running the API Server

```bash
# From repository root
docker run --rm -it \
  -v "$PWD:/work" \
  -p 8000:8000 \
  codi:slim
```

- Access docs at `http://localhost:8000/docs`.
- Health check: `curl http://localhost:8000/healthz`.

## 4. Executing CLI Commands

Override the default entrypoint to run one-off commands:

```bash
docker run --rm \
  -v "$PWD:/work" \
  codi:slim \
  codi all /work/demo/node --dry-run
```

### Interactive Shell

```bash
make run-slim-cli
# internals: docker run --rm -it -v "$PWD:/work" codi:slim /bin/bash
```

Inside the container you can run `codi --help`, `python -m pytest`, or inspect generated artefacts under `/work/runs/` (which maps to the host). Use `exit` to leave the shell.

## 5. Volume Management

| Mount | Purpose |
| --- | --- |
| `/work` | Host project and `runs/` directory. Required for the container to see source code and persist artefacts. |

Ensure the host path is writable; the CLI writes run directories relative to `/work`.

## 6. Environment Variables

The Slim image respects the same environment variables as the CLI:

```bash
docker run --rm -v "$PWD:/work" \
  -e CODI_OUTPUT_ROOT=/work/runs/slim \
  -e AIRGAP=true \
  -e AIRGAP_ALLOWLIST="testserver" \
  codi:slim codi run /work/demo/python
```

## 7. CI/CD Usage Pattern

1. Checkout repository in pipeline workspace.
2. Run `docker build` or reuse published image `ghcr.io/<namespace>/codi-slim:<tag>`.
3. Execute CLI inside container with project workspace mounted at `/work`.
4. Archive `/work/runs/<timestamp>` as pipeline artifact.

Example GitHub Actions snippet:

```yaml
- name: Run CODI slim
  run: |
    docker run --rm \
      -v "$PWD:/work" \
      codi:slim \
      codi all /work/demo/node --out /work/runs/ci-node
- name: Upload report
  uses: actions/upload-artifact@v4
  with:
    name: codi-report
    path: runs/ci-node/reports/
```

## 8. Troubleshooting

| Issue | Resolution |
| --- | --- |
| `permission denied` writing to `/work/runs` | Ensure host path is writable; mount explicit directory (`-v "$PWD:/work"`). |
| CLI cannot access Golang libs, etc. | Mount entire repo to `/work` so relative paths resolve. |
| Slow cold start | Pre-pull base image or keep builder cache warm using `docker build --cache-from`. |
| Need to run tests inside container | Use `make run-slim-cli` then `python -m pytest`. |

## 9. Security Defaults

- Runs as UID/GID 1000 (`codi`).
- `AIRGAP=true` by default; outbound HTTP blocked unless allowlisted.
- `LLM_ENABLED=false`; only deterministic rules are used.
- `.dockerignore` minimises build context to reduce risk of leaking secrets.

## 10. Image Contents

- `/opt/codi` – application source.
- `/opt/codi/.venv` – virtual environment created during build stage.
- `/entrypoint.sh` – script launching FastAPI when no args provided.
- `/work` – mount point for user data.

## 11. Upgrading the Image

1. Pull latest repository changes.
2. Rebuild: `docker build -f docker/Dockerfile.slim -t codi:slim .`
3. Optionally push to registry using `make publish-images` (see `CICD_RELEASE.md`).

## Related Documentation

- CLI details: [CLI_GUIDE.md](./CLI_GUIDE.md)
- Complete container: [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md)
- Release workflows: `CICD_RELEASE.md`
