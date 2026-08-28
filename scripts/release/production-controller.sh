#!/usr/bin/env bash

# Install this file as /usr/local/sbin/ml-portal-deploy (root:root, mode 0750).
# It is the only command the production GitLab Runner may invoke directly.

set -Eeuo pipefail

CONFIG_FILE="/etc/ml-portal/controller.env"

controller_log() {
  printf '[ml-portal-deploy %s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >&2
}

fail() {
  controller_log "ERROR: $*"
  exit 1
}

trap 'status=$?; test "$status" -eq 0 || controller_log "EXIT: status=$status, command=$BASH_COMMAND"' EXIT

test "${EUID}" -eq 0 || fail "This controller must run as root."
test -r "$CONFIG_FILE" || fail "Missing root-owned controller configuration: $CONFIG_FILE"
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${APP_ROOT:?APP_ROOT is required in controller.env}"
: "${STATE_DIR:?STATE_DIR is required in controller.env}"
: "${PROD_ENV_FILE:?PROD_ENV_FILE is required in controller.env}"
: "${CI_BUILDS_ROOT:?CI_BUILDS_ROOT is required in controller.env}"
: "${DEPLOY_GROUP:=ml-portal-deploy}"

usage() {
  cat >&2 <<'EOF'
Usage:
  ml-portal-deploy deploy --source CI_CHECKOUT --release CI_COMMIT_SHA
  ml-portal-deploy rollback
  ml-portal-deploy status
EOF
  exit 2
}

require_safe_config() {
  test "$(stat -c '%U:%G:%a' "$CONFIG_FILE")" = "root:root:600" || \
    fail "Controller configuration must be root:root with mode 0600: $CONFIG_FILE"
  test -r "$PROD_ENV_FILE" || fail "Production environment file is not readable: $PROD_ENV_FILE"
  install -d -o root -g "$DEPLOY_GROUP" -m 0750 "$APP_ROOT" "$APP_ROOT/releases" "$STATE_DIR"
}

canonical_path() {
  realpath -e "$1"
}

require_ci_source() {
  local source="$1"
  local source_root
  source="$(canonical_path "$source")" || fail "CI source directory does not exist: $1"
  source_root="$(canonical_path "$CI_BUILDS_ROOT")" || fail "Configured CI_BUILDS_ROOT does not exist: $CI_BUILDS_ROOT"
  case "$source" in
    "${source_root}"/*) printf '%s\n' "$source" ;;
    *) fail "CI source must be inside CI_BUILDS_ROOT: $source" ;;
  esac
}

stage_release_bundle() {
  local source="$1"
  local release_id="$2"
  local destination="${APP_ROOT}/releases/${release_id}"
  local temporary_dir
  local file
  local -a required_files=(
    docker-compose.prod.yml
    release.env
    scripts/release/common.sh
    scripts/release/deploy.sh
  )

  if test -e "$destination"; then
    test -f "${destination}/.release-id" || fail "Existing release directory is invalid: $destination"
    test "$(<"${destination}/.release-id")" = "$release_id" || fail "Existing release marker does not match: $destination"
    printf '%s\n' "$destination"
    return
  fi

  for file in "${required_files[@]}"; do
    test -f "${source}/${file}" || fail "Release bundle is missing required file: ${file}"
  done

  temporary_dir="$(mktemp -d "${APP_ROOT}/releases/.${release_id}.XXXXXX")"
  trap 'test -n "${temporary_dir:-}" && rm -rf "$temporary_dir"' RETURN
  install -D -o root -g "$DEPLOY_GROUP" -m 0640 "${source}/docker-compose.prod.yml" "${temporary_dir}/docker-compose.prod.yml"
  install -D -o root -g "$DEPLOY_GROUP" -m 0640 "${source}/release.env" "${temporary_dir}/release.env"
  install -D -o root -g "$DEPLOY_GROUP" -m 0640 "${source}/scripts/release/common.sh" "${temporary_dir}/scripts/release/common.sh"
  install -D -o root -g "$DEPLOY_GROUP" -m 0750 "${source}/scripts/release/deploy.sh" "${temporary_dir}/scripts/release/deploy.sh"
  printf '%s\n' "$release_id" > "${temporary_dir}/.release-id"
  chown -R root:"$DEPLOY_GROUP" "$temporary_dir"
  chmod 0750 "$temporary_dir" "${temporary_dir}/scripts" "${temporary_dir}/scripts/release"
  chmod 0640 "${temporary_dir}/.release-id"
  mv "$temporary_dir" "$destination"
  trap - RETURN
  printf '%s\n' "$destination"
}

release_helper() {
  local release_dir="$1"
  local helper="${release_dir}/scripts/release/deploy.sh"
  test -x "$helper" || fail "Release helper is unavailable: $helper"
  printf '%s\n' "$helper"
}

deploy() {
  local source=""
  local release_id=""
  while test "$#" -gt 0; do
    case "$1" in
      --source) source="$2"; shift 2 ;;
      --release) release_id="$2"; shift 2 ;;
      *) usage ;;
    esac
  done
  [[ "$release_id" =~ ^[0-9a-f]{7,64}$ ]] || fail "Release ID must be a Git commit SHA."
  source="$(require_ci_source "$source")"
  controller_log "Staging immutable release ${release_id} from ${source}"
  local release_dir
  release_dir="$(stage_release_bundle "$source" "$release_id")"
  controller_log "Deploying release ${release_id}"
  PROD_ENV_FILE="$PROD_ENV_FILE" ML_PORTAL_APP_ROOT="$APP_ROOT" ML_PORTAL_STATE_DIR="$STATE_DIR" \
    bash "$(release_helper "$release_dir")" deploy --release-dir "$release_dir"
}

rollback() {
  local release_dir
  release_dir="$(readlink -f "${APP_ROOT}/current")" || fail "No active release is available."
  PROD_ENV_FILE="$PROD_ENV_FILE" ML_PORTAL_APP_ROOT="$APP_ROOT" ML_PORTAL_STATE_DIR="$STATE_DIR" \
    bash "$(release_helper "$release_dir")" rollback
}

status() {
  local release_dir
  if ! release_dir="$(readlink -f "${APP_ROOT}/current")"; then
    echo "ACTIVE_RELEASE=none"
    test -f "${STATE_DIR}/last-deploy.env" && cat "${STATE_DIR}/last-deploy.env"
    return
  fi
  if test ! -x "${release_dir}/scripts/release/deploy.sh"; then
    echo "ACTIVE_RELEASE=$(basename "$release_dir")"
    echo "STATUS_ERROR=active release helper is missing: ${release_dir}/scripts/release/deploy.sh"
    test -f "${STATE_DIR}/last-deploy.env" && cat "${STATE_DIR}/last-deploy.env"
    return 0
  fi
  PROD_ENV_FILE="$PROD_ENV_FILE" ML_PORTAL_APP_ROOT="$APP_ROOT" ML_PORTAL_STATE_DIR="$STATE_DIR" \
    bash "$(release_helper "$release_dir")" status
}

main() {
  local command="${1:-}"
  test -n "$command" || usage
  shift
  require_safe_config
  case "$command" in
    deploy) deploy "$@" ;;
    rollback) test "$#" -eq 0 || usage; rollback ;;
    status) test "$#" -eq 0 || usage; status ;;
    *) usage ;;
  esac
}

main "$@"
