#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "This helper is Bash-only; run: make base-hash" >&2
  return 1 2>/dev/null || exit 1
fi

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_FILE="${REPO_ROOT}/release.env"
BASE_DOCKERFILE="${REPO_ROOT}/infra/docker/base/Dockerfile.ml"
BASE_REQUIREMENTS="${REPO_ROOT}/infra/docker/base/requirements.ml.txt"
RELEASE_PHASE="startup"
RELEASE_PHASE_STARTED_AT=$SECONDS

release_log() {
  printf '[release %s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >&2
}

release_phase_start() {
  RELEASE_PHASE="$1"
  RELEASE_PHASE_STARTED_AT=$SECONDS
  release_log "START: ${RELEASE_PHASE}"
}

release_phase_end() {
  release_log "DONE: ${RELEASE_PHASE} (duration: $((SECONDS - RELEASE_PHASE_STARTED_AT))s)"
}

release_error_trap() {
  local status=$?
  local source_file="${BASH_SOURCE[1]-${BASH_SOURCE[0]}}"
  local source_line="${BASH_LINENO[0]-unknown}"
  release_log "ERROR: phase=${RELEASE_PHASE}, status=${status}, location=${source_file}:${source_line}, command=${BASH_COMMAND}"
}

release_exit_trap() {
  local status=$?
  if test "$status" -ne 0; then
    release_log "EXIT: release stopped in phase=${RELEASE_PHASE}, status=${status}, elapsed=$((SECONDS - RELEASE_PHASE_STARTED_AT))s"
  fi
}

trap release_error_trap ERR
trap release_exit_trap EXIT

fail() {
  release_log "ERROR: $*"
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
  if ! awk '
    /^[[:space:]]*($|#)/ { next }
    /^[A-Z][A-Z0-9_]*=[-A-Za-z0-9._:\/@+]+$/ {
      split($0, pair, "=")
      key = pair[1]
      if (key !~ /^(IMAGE_REPOSITORY|APP_IMAGE_TAG|BASE_IMAGE_TAG|BASE_INPUT_SHA|SOURCE_SHA|DB_REVISION)$/ || seen[key]++) {
        exit 1
      }
      next
    }
    { exit 1 }
  ' "$RELEASE_FILE"; then
    fail "release.env must contain each supported manifest key at most once as a safe KEY=VALUE entry."
  fi
  set -a
  # release.env was validated above and contains only immutable deployment metadata.
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
  local dockerfile_sha requirements_sha
  if command -v sha256sum >/dev/null 2>&1; then
    dockerfile_sha="$(sha256sum "$BASE_DOCKERFILE" | awk '{print $1}')"
    requirements_sha="$(sha256sum "$BASE_REQUIREMENTS" | awk '{print $1}')"
  else
    dockerfile_sha="$(shasum -a 256 "$BASE_DOCKERFILE" | awk '{print $1}')"
    requirements_sha="$(shasum -a 256 "$BASE_REQUIREMENTS" | awk '{print $1}')"
  fi
  printf 'Dockerfile.ml=%s\nrequirements.ml.txt=%s\n' "$dockerfile_sha" "$requirements_sha" \
    | (sha256sum 2>/dev/null || shasum -a 256) | awk '{print "sha256:" $1}'
}

bump_app_patch() {
  local tag="$1"
  if [[ ! "$tag" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    fail "APP_IMAGE_TAG must be SemVer vMAJOR.MINOR.PATCH, got: $tag"
  fi
  printf 'v%s.%s.%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "$((BASH_REMATCH[3] + 1))"
}

bump_base_minor() {
  local tag="$1"
  if [[ ! "$tag" =~ ^base-([0-9]+)\.([0-9]+)$ ]]; then
    fail "BASE_IMAGE_TAG must be base-MAJOR.MINOR, got: $tag"
  fi
  printf 'base-%s.%s\n' "${BASH_REMATCH[1]}" "$((BASH_REMATCH[2] + 1))"
}

release_value_from_ref() {
  local ref="$1"
  local key="$2"
  git -C "$REPO_ROOT" show "${ref}:release.env" | awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); exit }'
}
