# CODI CI/CD & Release Guide

This document explains how CODI images are built, tested, signed, and published using both local tooling and GitHub Actions.

## 1. Release Artifacts

- Container images: `codi-slim` and `codi-complete` for linux/amd64.
- Tags: semantic version (`vX.Y.Z`), `latest`, and git SHA.
- SBOMs: SPDX JSON files for each image.
- cosign signatures and attestations.

## 2. Local Release Workflow

### 2.1 Build Release-Tagged Images

```bash
make release-images \
  REGISTRY=docker.io \
  IMAGE_NAMESPACE=KiniunCorp \
  RELEASE_VERSION=v1.4.0
```

- Builds Slim and Complete images with tags `<registry>/<namespace>/codi-{slim,complete}:v1.4.0`.
- Loads images into local Docker without pushing (`PUSH=false`).

### 2.2 Publish Images

```bash
make publish-images \
  REGISTRY=docker.io \
  IMAGE_NAMESPACE=KiniunCorp \
  RELEASE_VERSION=v1.4.0
```

- Requires `docker login` to the target registry.
- Pushes Slim and Complete images.
- For GHCR, set `REGISTRY=ghcr.io`.

### 2.3 Tag Repository

```bash
git tag v1.4.0
git push origin v1.4.0
```

Pushing the tag triggers the GitHub Actions release workflow.

## 3. GitHub Actions Workflow (`.github/workflows/release-images.yml`)

### Steps
1. Checkout code.
2. Determine version from tag or workflow input.
3. Resolve registry namespace (defaults to `<org>/<repo>` lowercase).
4. Set up QEMU + Buildx for consistent builds.
5. Log in to registry using `GITHUB_TOKEN` (for GHCR).
6. Generate Docker metadata (tags/labels) for Slim and Complete.
7. Build & push both images (linux/amd64).
8. Install cosign.
9. Sign images using keyless (OIDC) mode: `cosign sign --yes <image>@<digest>`.
10. Generate SBOM via `anchore/sbom-action`.
11. Attach SBOM attestations using `cosign attest`.
12. Upload SBOMs as workflow artifacts.

### Inputs
- `version` (when manually triggered).
- `image_namespace` (optional override).

### Concurrency
- Workflow keyed by git ref to avoid overlapping publishes.

## 4. Registry Layout

- Default registry in Makefile: `docker.io`, namespace `KiniunCorp`. Adjust as needed.
- GitHub Actions workflow uses `ghcr.io/<namespace>/codi-{slim,complete}`.
- Align local `IMAGE_NAMESPACE` with remote to prevent tag drift.

## 5. Verifying Releases

```bash
IMAGE=ghcr.io/<namespace>/codi-slim:v1.4.0
cosign verify \
  --certificate-identity "https://github.com/<org>/<repo>/.github/workflows/release-images.yml@refs/tags/v1.4.0" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$IMAGE"

cosign verify-attestation \
  --type spdxjson \
  "$IMAGE"
```

Replace `<org>/<repo>` and namespace accordingly.

## 6. SBOM Handling

- SBOMs stored in workflow artifacts named `sbom-<version>`.
- Each SBOM includes package inventory for compliance reviews.
- Attestations are pushed to registry alongside images for tamper evidence.

## 7. Release Checklist

1. Ensure tests pass (`make test`).
2. Verify docs updated (especially `REFERENCE.md`, `CICD_RELEASE.md`).
3. Build release images locally using `make release-images`.
4. Run smoke tests using freshly built images.
5. Tag repository and push tag.
6. Monitor GitHub Actions workflow for completion.
7. Verify cosign signatures and SBOMs.
8. Communicate release notes with links to documentation.

## 8. Rollback Procedure

1. Identify last known-good tag (e.g., `v1.3.2`).
2. Pull or build that version locally: `docker pull ghcr.io/<namespace>/codi-slim:v1.3.2`.
3. Update deployment manifests to reference old tag.
4. Optionally delete problematic tag or mark as revoked in release notes.

## 9. CI Testing Guidance

- Use Slim container for deterministic tests in CI.
- Mount workspace at `/work`; output runs to `/work/runs/<job-id>`.
- Publish `report.html` as artifact for each job.
- Optional: run `codi perf` nightly to track performance regressions.

## Related Documentation

- [SLIM_CONTAINER.md](./SLIM_CONTAINER.md) and [COMPLETE_CONTAINER.md](./COMPLETE_CONTAINER.md) for context on built images.
- [SECURITY.md](./SECURITY.md) covering signing, SBOM, and provenance requirements.
- [OPERATIONS.md](./OPERATIONS.md) for deployment and rollback procedures that consume released artifacts.
