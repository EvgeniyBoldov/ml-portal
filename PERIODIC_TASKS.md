# Periodic Tasks (Beat)

Временный документ-реестр периодических задач.

Источник конфигурации: `apps/api/src/app/celery_app.py` (`app.conf.beat_schedule`).

## Active Periodic Tasks

- `models-health-check`
  - task: `app.workers.tasks_health_check.health_check_all_models`
  - schedule: every `300s` (5 min)

- `mcp-connectors-health-check`
  - task: `app.workers.tasks_health.probe_mcp_connectors`
  - schedule: every `60s`

- `data-connectors-health-check`
  - task: `app.workers.tasks_health.probe_data_connectors`
  - schedule: every `60s`

- `embedding-models-health-check`
  - task: `app.workers.tasks_health.probe_embedding_models`
  - schedule: every `60s`

- `rerank-models-health-check`
  - task: `app.workers.tasks_health.probe_rerank_models`
  - schedule: every `60s`

- `llm-models-health-check`
  - task: `app.workers.tasks_health.probe_llm_models`
  - schedule: every `600s` (10 min)

- `discovery-rescan`
  - task: `app.workers.tasks_health.rescan_discovery`
  - schedule: every `600s` (10 min)

- `collections-vectorization-reconcile`
  - task: `app.workers.tasks_collection_vectorize.reconcile_collection_vectorization`
  - schedule: every `120s` (2 min)

- `document-membership-reconcile`
  - task: `app.workers.tasks_membership_reconcile.reconcile_document_collection_memberships`
  - schedule: every `600s` (10 min)

- `rag-stale-reindex-reconcile`
  - task: `app.workers.tasks_rag_reindex.reconcile_stale_rag_reindex`
  - schedule: every `900s` (15 min)
  - purpose: пакетный запуск reindex для stale RAG документов (model version mismatch)

- `ldap-users-sync`
  - task: `app.workers.tasks_ldap_sync.sync_ldap_users`
  - schedule: cron from `AUTH_LDAP_SYNC_CRON`

- `ldap-health-check`
  - task: `app.workers.tasks_ldap_sync.ldap_health_check`
  - schedule: every `300s` (5 min)

- `sandbox-sessions-expired-cleanup`
  - task: `app.workers.tasks_cleanup.cleanup_expired_sandbox_sessions`
  - schedule: every `600s` (10 min)

- `deprecated-entities-cleanup`
  - task: `app.workers.tasks_cleanup.cleanup_deprecated_entities`
  - schedule: every `3600s` (1 hour)
  - purpose: hard-delete lifecycle entities in status `deprecated` after retention TTL
  - scope: `tenant` (except platform default), `user`, `collection`, `agent`, `rbac_rule`
  - retention: per-entity `retention_days`, fallback `14` days

## Notes

- Это временный реестр "для записи".
- Далее задачи будут отображаться на отдельной admin-странице (task center).
