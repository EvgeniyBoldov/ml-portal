#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command git
require_clean_worktree

branch="$(git -C "$REPO_ROOT" branch --show-current)"
test "$branch" = "main" || fail "update-source must run on main, current branch: ${branch:-detached}"
git -C "$REPO_ROOT" remote get-url origin >/dev/null || fail "Missing origin remote (production GitLab)."
git -C "$REPO_ROOT" remote get-url source >/dev/null || fail "Missing source remote (GitHub source repository)."

git -C "$REPO_ROOT" fetch origin main
git -C "$REPO_ROOT" merge --ff-only origin/main
git -C "$REPO_ROOT" fetch source main
git -C "$REPO_ROOT" merge --no-edit source/main

echo "Source updated. Review and test this local production branch, then run: make release"
