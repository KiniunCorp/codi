#!/usr/bin/env bash
set -euo pipefail

# Builds Slim and Complete CODI images with reproducible tags.
# Configuration (env vars):
#   REGISTRY          - Container registry (default: ghcr.io)
#   IMAGE_NAMESPACE   - Namespace/project inside the registry (default: local/codi)
#   RELEASE_VERSION   - Semantic version or ref tag applied to both images (default: dev)
#   ADDITIONAL_TAG    - Optional secondary tag (default: latest)
#   PUSH              - When "true", pushes instead of loading into local Docker (default: false)
#   PLATFORMS         - Target platforms for buildx (default: linux/amd64)
#   BUILD_PROGRESS    - buildx progress output flag, e.g. "--progress=plain"

REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-local/codi}"
RELEASE_VERSION="${RELEASE_VERSION:-dev}"
ADDITIONAL_TAG="${ADDITIONAL_TAG:-latest}"
PUSH="${PUSH:-false}"
PLATFORMS="${PLATFORMS:-linux/amd64}"
BUILD_PROGRESS="${BUILD_PROGRESS:---progress=plain}"

IMAGE_NAMESPACE="$(echo "${IMAGE_NAMESPACE}" | tr '[:upper:]' '[:lower:]' | sed 's#^/##;s#/$##')"
REGISTRY="$(echo "${REGISTRY}" | sed 's#/*$##')"

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ docker is required on PATH" >&2
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  echo "❌ docker buildx is required (Docker 20.10+)" >&2
  exit 1
fi

if [[ -z "${RELEASE_VERSION}" ]]; then
  echo "❌ RELEASE_VERSION must be set (e.g. v1.2.3)" >&2
  exit 1
fi

if [[ "${PUSH}" == "true" ]]; then
  OUTPUT_FLAG="--push"
  echo "🚀 Push mode enabled. Images will be published to ${REGISTRY}/${IMAGE_NAMESPACE}"
else
  OUTPUT_FLAG="--load"
  echo "📦 Local mode enabled. Images will be loaded into the local Docker engine."
fi

build_image() {
  local variant="$1"
  local dockerfile="$2"
  local image_ref="${REGISTRY}/${IMAGE_NAMESPACE}/${variant}"
  local tags=("-t" "${image_ref}:${RELEASE_VERSION}")

  if [[ -n "${ADDITIONAL_TAG}" ]]; then
    tags+=("-t" "${image_ref}:${ADDITIONAL_TAG}")
  fi

  echo ""
  echo "=== Building ${variant} from ${dockerfile} ==="
  echo "Image reference: ${image_ref}"
  echo "Applying tags: ${RELEASE_VERSION}${ADDITIONAL_TAG:+, ${ADDITIONAL_TAG}}"

  docker buildx build \
    --platform "${PLATFORMS}" \
    -f "${dockerfile}" \
    "${tags[@]}" \
    ${BUILD_PROGRESS} \
    "${OUTPUT_FLAG}" \
    .

  if [[ "${OUTPUT_FLAG}" == "--push" ]]; then
    echo "✅ Published ${image_ref}:${RELEASE_VERSION}"
  else
    echo "✅ Loaded ${image_ref}:${RELEASE_VERSION} into the local Docker cache"
  fi
}

build_image "codi-slim" "docker/Dockerfile.slim"
build_image "codi-complete" "docker/Dockerfile.complete"

echo ""
echo "🎉 Release build finished. VERSION=${RELEASE_VERSION} PUSH=${PUSH}"
