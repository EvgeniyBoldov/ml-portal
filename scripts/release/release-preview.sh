#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_command git
load_release_file

current_base_sha="$(base_input_sha)"
next_app_tag="$(bump_app_patch "$APP_IMAGE_TAG")"
next_base_tag="$BASE_IMAGE_TAG"

if test "$current_base_sha" != "$BASE_INPUT_SHA"; then
  next_base_tag="$(bump_base_minor "$BASE_IMAGE_TAG")"
  base_state="changed (new base will be built)"
else
  base_state="unchanged (existing base will be reused)"
fi

printf '%s\n' \
  "Current app release: ${APP_IMAGE_TAG}" \
  "Next app release:    ${next_app_tag}" \
  "Current base:        ${BASE_IMAGE_TAG}" \
  "Next base:           ${next_base_tag}" \
  "Base inputs:         ${base_state}" \
  "Current DB revision:  ${DB_REVISION}" \
  "Current source SHA:   ${SOURCE_SHA}"
