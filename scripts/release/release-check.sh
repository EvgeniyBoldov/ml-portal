#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command docker
require_command git
load_release_file
require_clean_worktree

branch="$(git -C "$REPO_ROOT" branch --show-current)"
test "$branch" = "main" || fail "release must run on main, current branch: ${branch:-detached}"
git -C "$REPO_ROOT" fetch origin main
git -C "$REPO_ROOT" merge-base --is-ancestor origin/main HEAD || \
  fail "Local main is behind origin/main; run make update-source before release."

origin_tag="$(release_value_from_ref origin/main APP_IMAGE_TAG)"
test -n "$origin_tag" || fail "origin/main has no release.env APP_IMAGE_TAG."
test "$origin_tag" = "$APP_IMAGE_TAG" || fail "Local release.env is stale; expected APP_IMAGE_TAG=${origin_tag} from origin/main."

BASE_IMAGE="${IMAGE_REPOSITORY}/base-ml:${BASE_IMAGE_TAG}" \
IMAGE_REPOSITORY="$IMAGE_REPOSITORY" APP_IMAGE_TAG="$APP_IMAGE_TAG" \
  docker compose -f "${REPO_ROOT}/docker-compose.build.yml" config --quiet

echo "Release checks passed. Current base input: $(base_input_sha)"
