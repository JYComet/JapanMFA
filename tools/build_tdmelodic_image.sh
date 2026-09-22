#!/usr/bin/env bash
set -euo pipefail

# Build only an image; this script never installs into Conda or modifies the
# old repository. Override these values from a controlled build environment.
TDMELODIC_REPOSITORY="${TDMELODIC_REPOSITORY:-https://github.com/PKSHATechnology-Research/tdmelodic.git}"
TDMELODIC_COMMIT="${TDMELODIC_COMMIT:-}"
IMAGE_NAME="${IMAGE_NAME:-japanmfa-tdmelodic}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${DOCKERFILE:-${PROJECT_ROOT}/tools/Dockerfile.tdmelodic}"
DOCKER_BIN="${DOCKER_BIN:-docker}"

if [[ -z "${TDMELODIC_COMMIT}" ]]; then
  echo "TDMELODIC_COMMIT must be set to an immutable commit" >&2
  exit 2
fi
if [[ ! "${TDMELODIC_COMMIT}" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "TDMELODIC_COMMIT must be a 40-character Git commit SHA" >&2
  exit 2
fi
if [[ -z "${TDMELODIC_REPOSITORY}" || -z "${IMAGE_NAME}" || -z "${DOCKERFILE}" ]]; then
  echo "repository, image name, and Dockerfile must be non-empty" >&2
  exit 2
fi

IMAGE_TAG="${IMAGE_TAG:-${TDMELODIC_COMMIT:0:12}}"
if [[ ! "${IMAGE_TAG}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "IMAGE_TAG contains unsupported characters" >&2
  exit 2
fi

"${DOCKER_BIN}" build \
  --build-arg "TDMELODIC_REPOSITORY=${TDMELODIC_REPOSITORY}" \
  --build-arg "TDMELODIC_COMMIT=${TDMELODIC_COMMIT}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file "${DOCKERFILE}" \
  "${PROJECT_ROOT}"
