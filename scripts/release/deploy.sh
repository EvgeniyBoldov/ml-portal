#!/usr/bin/env bash

# This script is executed by the root-owned ml-portal-deploy controller after a
# release bundle was staged in /opt/ml-portal/releases/<immutable-release-id>.
# Do not invoke it from a GitLab checkout or grant the runner Docker access.

set -Eeuo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/common.sh"

readonly APPLICATION_SERVICES=(
  api frontend netbox-mcp-custom dbhub-mcp atlassian-jira-mcp ml-inference-mcp
  emb rerank worker flower nginx
)
readonly STATEFUL_SERVICES=(postgres postgres-remote redis qdrant minio)

APP_ROOT="${ML_PORTAL_APP_ROOT:-/opt/ml-portal}"
STATE_DIR="${ML_PORTAL_STATE_DIR:-/var/lib/ml-portal}"
PROD_ENV_FILE="${PROD_ENV_FILE:-/etc/ml-portal/prod.env}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-ml-portal}"
DEPLOY_WAIT_TIMEOUT="${DEPLOY_WAIT_TIMEOUT:-180}"
RELEASE_DIR=""

usage() {
  cat >&2 <<'EOF'
Usage:
  deploy.sh deploy --release-dir DIR [--app-root DIR] [--state-dir DIR] [--prod-env FILE]
  deploy.sh rollback [--app-root DIR] [--state-dir DIR] [--prod-env FILE]
  deploy.sh status [--app-root DIR] [--state-dir DIR] [--prod-env FILE]
  deploy.sh validate --release-dir DIR [--app-root DIR] [--state-dir DIR] [--prod-env FILE]
EOF
  exit 2
}

require_root() {
  test "${EUID}" -eq 0 || fail "deploy.sh must run through the root-owned ml-portal-deploy controller."
}

parse_options() {
  while test "$#" -gt 0; do
    case "$1" in
      --release-dir) RELEASE_DIR="$2"; shift 2 ;;
      --app-root) APP_ROOT="$2"; shift 2 ;;
      --state-dir) STATE_DIR="$2"; shift 2 ;;
      --prod-env) PROD_ENV_FILE="$2"; shift 2 ;;
      *) usage ;;
    esac
  done
}

require_runtime_paths() {
  require_command docker
  require_command flock
  test -d "$APP_ROOT" || fail "Application root is missing: $APP_ROOT"
  test -d "$STATE_DIR" || fail "State directory is missing: $STATE_DIR"
  test -r "$PROD_ENV_FILE" || fail "Production environment file is not readable: $PROD_ENV_FILE"
}

release_id_from_dir() {
  basename "$1"
}

current_release_dir() {
  test -L "${APP_ROOT}/current" || return 1
  readlink -f "${APP_ROOT}/current"
}

previous_release_dir() {
  test -L "${APP_ROOT}/previous" || return 1
  readlink -f "${APP_ROOT}/previous"
}

load_release_manifest() {
  local release_dir="$1"
  RELEASE_FILE="${release_dir}/release.env"
  load_release_file
}

compose() {
  docker compose \
    --project-name "$COMPOSE_PROJECT" \
    --env-file "$PROD_ENV_FILE" \
    --env-file "$RELEASE_FILE" \
    -f "${RELEASE_DIR}/docker-compose.prod.yml" \
    "$@"
}

require_expected_services() {
  local service
  local configured_services
  configured_services="$(compose config --services)"
  for service in "${APPLICATION_SERVICES[@]}" "${STATEFUL_SERVICES[@]}"; do
    grep -Fxq "$service" <<< "$configured_services" || \
      fail "Production compose is missing required service: $service"
  done
}

validate_release_bundle() {
  local release_dir="$1"
  test -d "$release_dir" || fail "Release directory is missing: $release_dir"
  test -f "${release_dir}/.release-id" || fail "Release directory has no immutable release marker: $release_dir"
  test -f "${release_dir}/docker-compose.prod.yml" || fail "Production compose is missing in $release_dir"
  test -f "${release_dir}/release.env" || fail "release.env is missing in $release_dir"

  RELEASE_DIR="$release_dir"
  load_release_manifest "$release_dir"
  export PROD_ENV_FILE
  release_phase_start "validate release $(release_id_from_dir "$release_dir")"
  compose config --quiet
  require_expected_services
  release_phase_end
}

verify_stateful_services() {
  local service container state health
  release_phase_start "verify stateful dependencies"
  for service in "${STATEFUL_SERVICES[@]}"; do
    container="$(compose ps -q "$service")"
    test -n "$container" || fail "Stateful service is not running: $service"
    state="$(docker inspect --format '{{.State.Status}}' "$container")"
    test "$state" = "running" || fail "Stateful service is not running: $service (state=$state)"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")"
    case "$health" in
      healthy|none) ;;
      *) fail "Stateful service is not healthy: $service (health=$health)" ;;
    esac
  done
  release_phase_end
}

pull_application_images() {
  release_phase_start "pull application images"
  compose pull "${APPLICATION_SERVICES[@]}" || return
  release_phase_end
}

apply_migrations() {
  release_phase_start "apply database migration ${DB_REVISION}"
  compose run --rm --no-deps api alembic upgrade "$DB_REVISION" || return
  release_phase_end
}

start_application_services() {
  release_phase_start "start application services"
  compose up -d --no-deps --wait --wait-timeout "$DEPLOY_WAIT_TIMEOUT" "${APPLICATION_SERVICES[@]}" || return
  release_phase_end
}

smoke_check() {
  release_phase_start "run application smoke checks"
  compose exec -T api curl --fail --silent --show-error http://localhost:8000/api/v1/healthz >/dev/null || return
  compose exec -T nginx wget --no-verbose --tries=1 --spider http://api:8000/api/v1/healthz || return
  release_phase_end
}

switch_link() {
  local link_name="$1"
  local target="$2"
  local temporary_link="${APP_ROOT}/.${link_name}.$$.new"
  ln -s "$target" "$temporary_link"
  mv -Tf "$temporary_link" "${APP_ROOT}/${link_name}"
}

record_result() {
  local result="$1"
  local release_dir="${2:-}"
  local temporary_file="${STATE_DIR}/.last-deploy.$$.new"
  {
    printf 'RESULT=%s\n' "$result"
    printf 'TIMESTAMP=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
    printf 'RELEASE_ID=%s\n' "${release_dir:+$(release_id_from_dir "$release_dir")}"
    printf 'APP_IMAGE_TAG=%s\n' "${APP_IMAGE_TAG:-unknown}"
    printf 'DB_REVISION=%s\n' "${DB_REVISION:-unknown}"
  } > "$temporary_file"
  mv -f "$temporary_file" "${STATE_DIR}/last-deploy.env"
}

deploy_application_release() {
  local release_dir="$1"
  RELEASE_DIR="$release_dir"
  load_release_manifest "$release_dir"
  export PROD_ENV_FILE
  pull_application_images || return
  start_application_services || return
  smoke_check
}

rollback_to_release() {
  local target_dir="$1"
  test -d "$target_dir" || fail "Rollback release directory is missing: $target_dir"
  release_log "Rolling back application services to $(release_id_from_dir "$target_dir"). Database migrations remain forward-only."
  deploy_application_release "$target_dir" || return
  switch_link current "$target_dir"
  record_result rolled_back "$target_dir"
}

rollback_application() {
  local previous_dir old_current
  old_current="$(current_release_dir)" || fail "No active release is available for rollback."
  previous_dir="$(previous_release_dir)" || fail "No previous release is available for rollback."
  rollback_to_release "$previous_dir"
  switch_link previous "$old_current"
}

deploy() {
  local old_current=""
  validate_release_bundle "$RELEASE_DIR"
  old_current="$(current_release_dir || true)"
  verify_stateful_services
  if ! apply_migrations; then
    record_result migration_failed "$RELEASE_DIR"
    fail "Database migration failed before application replacement."
  fi

  if ! deploy_application_release "$RELEASE_DIR"; then
    release_log "Application deployment failed after migrations. Attempting application-only rollback."
    if test -n "$old_current"; then
      if ! rollback_to_release "$old_current"; then
        record_result rollback_failed "$RELEASE_DIR"
        fail "Application deployment and automatic rollback both failed. Manual intervention is required."
      fi
    fi
    test -n "$old_current" || record_result failed "$RELEASE_DIR"
    fail "Application deployment failed; previous application release was restored when available."
  fi

  if test -n "$old_current" && test "$old_current" != "$RELEASE_DIR"; then
    switch_link previous "$old_current"
  fi
  switch_link current "$RELEASE_DIR"
  record_result success "$RELEASE_DIR"
  release_log "Deployment complete: release=$(release_id_from_dir "$RELEASE_DIR"), app=${APP_IMAGE_TAG}, source=${SOURCE_SHA}"
}

status() {
  local active=""
  active="$(current_release_dir || true)"
  if test -z "$active"; then
    echo "ACTIVE_RELEASE=none"
    test -f "${STATE_DIR}/last-deploy.env" && cat "${STATE_DIR}/last-deploy.env"
    return 0
  fi
  validate_release_bundle "$active"
  echo "ACTIVE_RELEASE=$(release_id_from_dir "$active")"
  echo "APP_IMAGE_TAG=${APP_IMAGE_TAG}"
  echo "SOURCE_SHA=${SOURCE_SHA}"
  echo "DB_REVISION=${DB_REVISION}"
  compose ps
  test -f "${STATE_DIR}/last-deploy.env" && cat "${STATE_DIR}/last-deploy.env"
}

main() {
  local command="${1:-}"
  test -n "$command" || usage
  shift
  require_root
  parse_options "$@"
  require_runtime_paths
  exec 9>"${STATE_DIR}/deploy.lock"
  flock -n 9 || fail "Another deployment is already running."

  case "$command" in
    deploy)
      test -n "$RELEASE_DIR" || usage
      deploy
      ;;
    rollback)
      rollback_application
      ;;
    status)
      status
      ;;
    validate)
      test -n "$RELEASE_DIR" || usage
      validate_release_bundle "$RELEASE_DIR"
      ;;
    *) usage ;;
  esac
}

main "$@"
