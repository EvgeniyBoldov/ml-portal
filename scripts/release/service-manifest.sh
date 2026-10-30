#!/usr/bin/env bash

# Canonical service groups used by deployment. Image build/push targets are
# discovered by Compose from docker-compose.build.yml and are not repeated here.
# When adding a production service, update its runtime group here once.

# Runtime application services are stopped, pulled and started as one release.
# Services may share an image (for example beat/worker) or use a public image
# (for example flower/docling), so this is intentionally separate from build targets.
readonly APPLICATION_SERVICES=(
  api frontend docling netbox-mcp-custom dbhub-mcp atlassian-jira-mcp atlassian-mcp ml-inference-mcp
  emb rerank hipporag worker beat flower nginx
)

readonly STATEFUL_SERVICES=(postgres postgres-tool-results postgres-remote redis qdrant minio)
