# SSE Status Streams — Architecture Reference

> **Status: IMPLEMENTED** (all stages 0-6 complete)

## Overview

Two dedicated SSE endpoints deliver real-time document status updates:

| Endpoint | Purpose | Redis channel |
|----------|---------|---------------|
| `GET /{collection_id}/status/events` | Aggregated statuses for collection page | `rag:agg:admin` / `rag:agg:tenant:{id}` |
| `GET /{collection_id}/docs/{doc_id}/status/events` | Per-document detailed steps for status modal | `rag:doc:{doc_id}` |

---

## Redis Channels

```
rag:agg:admin                  — aggregate_update, document_archived/unarchived,
                                 document_added/deleted  (for admin subscribers)
rag:agg:tenant:{tenant_id}     — same events, filtered to tenant
rag:doc:{doc_id}               — ALL events for one document:
                                 status_update, aggregate_update, lifecycle events
```

### Publishing logic

| Method | Channels |
|--------|----------|
| `publish_status_update` | `rag:doc:{id}` only |
| `publish_aggregate_status` | `rag:agg:admin` + `rag:agg:tenant:{id}` + `rag:doc:{id}` |
| `publish_document_archived/unarchived` | `rag:agg:admin` + `rag:agg:tenant:{id}` + `rag:doc:{id}` |
| `publish_document_added/deleted` | `rag:agg:admin` + `rag:agg:tenant:{id}` + `rag:doc:{id}` |
| `publish_status_initialized` | `rag:doc:{id}` only |
| `publish_ingest_started` | `rag:doc:{id}` only |

---

## Event Types and Payloads

### `aggregate_update`
```json
{
  "event_type": "aggregate_update",
  "document_id": "<uuid>",
  "tenant_id": "<uuid>",
  "agg_status": "ready",
  "agg_details": { "effective_status": "ready", "effective_reason": null },
  "status": "ready",
  "timestamp": "2024-01-01T00:00:00Z"
}
```
Emitted on collection stream. Triggers `setQueriesData` patch in `CollectionDataPage`.

### `status_update`
```json
{
  "event_type": "status_update",
  "document_id": "<uuid>",
  "stage": "extract",
  "status": "processing",
  "error": null,
  "metrics": {},
  "timestamp": "2024-01-01T00:00:00Z"
}
```
Emitted on doc stream only. Triggers `invalidateQueries` in `StatusModalNew`.

### `document_archived` / `document_unarchived`
```json
{
  "event_type": "document_archived",
  "document_id": "<uuid>",
  "archived": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```
Emitted on both streams. Triggers full list `invalidateQueries`.

### `document_added` / `document_deleted`
```json
{
  "event_type": "document_added",
  "document_id": "<uuid>",
  "collection_id": "<uuid>",
  "tenant_id": "<uuid>",
  "timestamp": "2024-01-01T00:00:00Z"
}
```
Emitted on collection stream. Triggers full list refetch.

### `snapshot` (collection stream)
```json
{
  "items": [
    {
      "document_id": "<uuid>",
      "name": "My Doc",
      "agg_status": "ready",
      "agg_details": { "effective_status": "ready" },
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "collection_id": "<uuid>"
}
```
Sent on connect and every 60s. Frontend patches React Query cache with `setQueriesData`.

### `snapshot` (document stream)
```json
{
  "document_id": "<uuid>",
  "graph": { /* full StatusGraphResponse */ }
}
```
Sent once on connect. Frontend sets query data via `queryClient.setQueryData(queryKey, graph)`.

---

## Authentication

SSE connections authenticate via **httpOnly cookie** `access_token` only.

- Browser sends cookie automatically with `EventSource` + `withCredentials: true`
- No token in URL query params
- `get_current_user_sse` dependency reads from `Authorization` header or `access_token` cookie

---

## Deduplication

`_update_aggregate_status` in `RAGStatusManager` reads the current `agg_status` and `effective_status` from DB before publishing. If neither changed, `publish_aggregate_status` is **skipped** to reduce noise on the collection stream.

---

## Snapshot & Resync

| Stream | On connect | Periodic |
|--------|-----------|----------|
| Collection | Sends `snapshot` with all active docs | Resync every 60s |
| Document | Sends `snapshot` with full StatusGraphResponse | No (modal is short-lived) |

---

## Frontend Integration

### CollectionDataPage
- Creates `SSEClient` on mount, tears down on unmount
- `snapshot` events → `queryClient.setQueriesData` (patch `agg_status` per doc, no refetch)
- `aggregate_update`, `document_archived/unarchived`, `document_added/deleted` → `queryClient.invalidateQueries`

### StatusModalNew
- Creates SSE via `openSSE` on mount
- `snapshot` events → `queryClient.setQueryData(queryKey, graph)` (direct cache set)
- Other events → throttled `queryClient.invalidateQueries` (min 500ms between calls)

---

## Reconnect Behavior

Native `EventSource` auto-reconnect is used. On reconnect, backend sends a fresh `snapshot` as the first event, guaranteeing the client re-synchronizes without manual state management.

---

## Local Testing

Publish a test event directly to Redis:

```bash
# Aggregate update (collection stream)
docker exec ml-portal-redis-1 redis-cli PUBLISH \
  "rag:agg:tenant:<your-tenant-id>" \
  '{"event_type":"aggregate_update","document_id":"<doc-id>","agg_status":"ready","agg_details":{},"status":"ready","timestamp":"2024-01-01T00:00:00Z"}'

# Status update (doc stream)
docker exec ml-portal-redis-1 redis-cli PUBLISH \
  "rag:doc:<doc-id>" \
  '{"event_type":"status_update","document_id":"<doc-id>","stage":"extract","status":"completed","timestamp":"2024-01-01T00:00:00Z"}'
```

View active SSE connections:
```bash
docker exec ml-portal-redis-1 redis-cli CLIENT LIST | grep -i pubsub
```

---

## Files Reference

| File | Role |
|------|------|
| `apps/api/src/app/services/rag_event_publisher.py` | Publisher + Subscriber classes |
| `apps/api/src/app/services/rag_status_snapshot.py` | Snapshot builders for collection/document |
| `apps/api/src/app/services/rag_status_manager.py` | Deduplication in `_update_aggregate_status` |
| `apps/api/src/app/api/v1/routers/collections/stream_events.py` | SSE endpoint handlers |
| `apps/web/src/shared/lib/sse.ts` | SSEClient (cookie-only auth) |
| `apps/web/src/domains/collections/pages/CollectionDataPage.tsx` | Collection stream consumer |
| `apps/web/src/domains/rag/components/StatusModalNew.tsx` | Document stream consumer |
| `apps/api/tests/unit/test_sse_channels.py` | Channel routing tests |
| `apps/api/tests/unit/test_sse_snapshot.py` | Snapshot builder tests |
| `apps/api/tests/unit/test_sse_deduplication.py` | Deduplication tests |
