#!/usr/bin/env bash
set -euo pipefail

# Build only an image; this script never installs into Conda or runs Docker.
# Override these values from a controlled CI/build environment when needed.
TDMELODIC_REPOSITORY="${TDMELODIC_REPOSITORY:-https://github.com/PKSHATechnology-Research/tdmelodic.git}"
TDMELODIC_COMMIT="${TDMELODIC_COMMIT:-master}"
IMAGE_NAME="${IMAGE_NAME:-japanmfa-tdmelodic}"
IMAGE_TAG="${IMAGE_TAG:-${TDMELODIC_COMMIT}}"
DOCKERFILE="${DOCKERFILE:-Dockerfile.tdmelodic}"

if [[ "${TDMELODIC_COMMIT}" == "master" || "${TDMELODIC_COMMIT}" == "main" ]]; then
  echo "TDMELODIC_COMMIT must be an immutable commit or release tag" >&2
  exit 2
fi

BUILD_COMMAND=(docker build \
  --build-arg "TDMELODIC_REPOSITORY=${TDMELODIC_REPOSITORY}" \
  --build-arg "TDMELODIC_COMMIT=${TDMELODIC_COMMIT}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file "${DOCKERFILE}" \
  .)

# The wrapper is intentionally a command generator. A caller or CI job must
# review and execute the printed command in its own controlled Docker context.
printf '%q ' "${BUILD_COMMAND[@]}"
printf '\n'
