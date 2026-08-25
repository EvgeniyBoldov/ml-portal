#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_FILE="${REPO_ROOT}/release.env"
BASE_DOCKERFILE="${REPO_ROOT}/infra/docker/base/Dockerfile.ml"
BASE_REQUIREMENTS="${REPO_ROOT}/infra/docker/base/requirements.ml.txt"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command is unavailable: $1"
}

require_clean_worktree() {
  git -C "$REPO_ROOT" diff --quiet || fail "Working tree has unstaged changes."
  git -C "$REPO_ROOT" diff --cached --quiet || fail "Working tree has staged changes."
  test -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal)" || \
    fail "Working tree has untracked changes."
}

load_release_file() {
  test -f "$RELEASE_FILE" || fail "Missing release.env. Copy release.env.example in the production GitLab repository."
  set -a
  # release.env is a reviewed, tracked deployment manifest; it must contain only KEY=VALUE entries.
  # shellcheck disable=SC1090
  source "$RELEASE_FILE"
  set +a
  : "${IMAGE_REPOSITORY:?IMAGE_REPOSITORY is required in release.env}"
  : "${APP_IMAGE_TAG:?APP_IMAGE_TAG is required in release.env}"
  : "${BASE_IMAGE_TAG:?BASE_IMAGE_TAG is required in release.env}"
  : "${BASE_INPUT_SHA:?BASE_INPUT_SHA is required in release.env}"
  : "${SOURCE_SHA:?SOURCE_SHA is required in release.env}"
  : "${DB_REVISION:?DB_REVISION is required in release.env}"
}

base_input_sha() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$BASE_DOCKERFILE" "$BASE_REQUIREMENTS" | sha256sum | awk '{print "sha256:" $1}'
  else
    shasum -a 256 "$BASE_DOCKERFILE" "$BASE_REQUIREMENTS" | shasum -a 256 | awk '{print "sha256:" $1}'
  fi
}

bump_app_patch() {
  local tag="$1"
  if [[ ! "$tag" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    fail "APP_IMAGE_TAG must be SemVer vMAJOR.MINOR.PATCH, got: $tag"
  fi
  printf 'v%s.%s.%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$((BASH_REMATCH[3] + 1))"
}

bump_base_patch() {
  local tag="$1"
  if [[ ! "$tag" =~ ^base-v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    fail "BASE_IMAGE_TAG must be base-vMAJOR.MINOR.PATCH, got: $tag"
  fi
  printf 'base-v%s.%s.%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$((BASH_REMATCH[3] + 1))"
}

release_value_from_ref() {
  local ref="$1"
  local key="$2"
  git -C "$REPO_ROOT" show "${ref}:release.env" | awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); exit }'
}
