#!/usr/bin/env bash

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

: "${PROD_ENV_FILE:?PROD_ENV_FILE must point to the protected production environment file}"
COMPOSE_PROD_FILE="${COMPOSE_PROD_FILE:-${REPO_ROOT}/docker-compose.prod.yml}"
test -r "$PROD_ENV_FILE" || fail "PROD_ENV_FILE is not readable: $PROD_ENV_FILE"
test -f "$COMPOSE_PROD_FILE" || fail "Production compose file is missing: $COMPOSE_PROD_FILE"
load_release_file

export PROD_ENV_FILE
registry_host="${IMAGE_REPOSITORY%%/*}"
if test -n "${REGISTRY_USERNAME:-}" || test -n "${REGISTRY_PASSWORD:-}"; then
  : "${REGISTRY_USERNAME:?REGISTRY_USERNAME is required when registry credentials are supplied}"
  : "${REGISTRY_PASSWORD:?REGISTRY_PASSWORD is required when registry credentials are supplied}"
  printf '%s' "$REGISTRY_PASSWORD" | docker login "$registry_host" --username "$REGISTRY_USERNAME" --password-stdin
fi

compose=(docker compose --env-file "$PROD_ENV_FILE" --env-file "$RELEASE_FILE" -f "$COMPOSE_PROD_FILE")
"${compose[@]}" config --quiet

managed_images="$("${compose[@]}" config --images | awk -v prefix="${IMAGE_REPOSITORY}/" 'index($0, prefix) == 1')"
test -n "$managed_images" || fail "Production compose contains no images from IMAGE_REPOSITORY."
while IFS= read -r image; do
  test -n "$image" && docker pull "$image"
done <<< "$managed_images"

"${compose[@]}" run --rm --no-deps api alembic upgrade "$DB_REVISION"
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout "${DEPLOY_WAIT_TIMEOUT:-180}"
echo "Deployment complete for ${APP_IMAGE_TAG} at source ${SOURCE_SHA}."
