#!/usr/bin/env bash
set -euo pipefail

# Build only an image; this script never installs into Conda or modifies the
# old repository. Override these values from a controlled build environment.
TDMELODIC_REPOSITORY="${TDMELODIC_REPOSITORY:-https://github.com/PKSHATechnology-Research/tdmelodic.git}"
TDMELODIC_COMMIT="${TDMELODIC_COMMIT:-}"
TDMELODIC_UNIDIC_ARCHIVE="${TDMELODIC_UNIDIC_ARCHIVE:-}"
TDMELODIC_UNIDIC_SHA256="${TDMELODIC_UNIDIC_SHA256:-}"
IMAGE_NAME="${IMAGE_NAME:-japanmfa-tdmelodic}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${DOCKERFILE:-${PROJECT_ROOT}/tools/Dockerfile.tdmelodic}"
DOCKER_BIN="${DOCKER_BIN:-docker}"

if [[ -z "${TDMELODIC_COMMIT}" ]]; then
  echo "TDMELODIC_COMMIT must be set to an immutable commit" >&2
  exit 2
fi
if [[ -z "${TDMELODIC_UNIDIC_ARCHIVE}" || -z "${TDMELODIC_UNIDIC_SHA256}" ]]; then
  echo "TDMELODIC_UNIDIC_ARCHIVE and TDMELODIC_UNIDIC_SHA256 are required" >&2
  exit 2
fi
if [[ ! -f "${TDMELODIC_UNIDIC_ARCHIVE}" || -L "${TDMELODIC_UNIDIC_ARCHIVE}" ]]; then
  echo "TDMELODIC_UNIDIC_ARCHIVE must be a regular non-symlink file" >&2
  exit 2
fi
if [[ ! "${TDMELODIC_UNIDIC_SHA256}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "TDMELODIC_UNIDIC_SHA256 must be a 64-character SHA256" >&2
  exit 2
fi
if [[ "$(sha256sum "${TDMELODIC_UNIDIC_ARCHIVE}" | awk '{print $1}')" != "${TDMELODIC_UNIDIC_SHA256,,}" ]]; then
  echo "TDMELODIC_UNIDIC_ARCHIVE SHA256 does not match" >&2
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

STAGING_CONTEXT="$(mktemp -d "${TMPDIR:-/tmp}/japanmfa-tdmelodic.XXXXXXXX")"
trap 'rm -rf -- "${STAGING_CONTEXT}"' EXIT
cp -- "${DOCKERFILE}" "${STAGING_CONTEXT}/Dockerfile.tdmelodic"
cp -- "${TDMELODIC_UNIDIC_ARCHIVE}" "${STAGING_CONTEXT}/unidic-mecab_kana-accent-2.1.2_src.zip"

"${DOCKER_BIN}" build \
  --build-arg "TDMELODIC_REPOSITORY=${TDMELODIC_REPOSITORY}" \
  --build-arg "TDMELODIC_COMMIT=${TDMELODIC_COMMIT}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file "${STAGING_CONTEXT}/Dockerfile.tdmelodic" \
  "${STAGING_CONTEXT}"
