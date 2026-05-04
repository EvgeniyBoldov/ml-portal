# Collection Status Stream — Redesign Plan

## 1. Текущее состояние (как есть)

### 1.1 Что отображает фронт

**Страница коллекции** (`http://localhost/gpt/collections/{slug}` для юзера):
- Список документов
- На каждый документ — **одно слово статуса** (`agg_status`): `uploaded` / `processing` / `ready` / `failed` / `partial` / `archived`
- Источник данных: `GET /api/v1/collections/{id}/documents` → поле `agg_status` (вычисляется бэком из `RAGDocument.agg_status` или налету через `calculate_aggregate_status`)
- **Этапные статусы здесь не нужны.**

**Модалка статусбара** (клик по документу):
- Pipeline по этапам: `upload → extract → normalize → chunk` (статус каждого, метрики, время)
- Embedding models (по каждой целевой модели)
- Index models
- Источник данных: `GET /api/v1/collections/{id}/docs/{doc_id}/status-graph`
- Здесь нужны **детальные пошаговые события**.

### 1.2 Что шлёт бэкенд в Redis

Все события идут в **один канал** `rag:status:admin` (или `rag:status:tenant:{id}`):
- `status_update` — изменение статуса этапа (extract→processing, extract→completed, ...). Публикуется в `_update_node_status`.
- `aggregate_update` — пересчёт агрегата. Публикуется в `_update_aggregate_status` после **каждого** `status_update`.
- `status_initialized`, `ingest_started`, `document_archived`, `document_unarchived` — события жизненного цикла.

**Цепочка на один этап:**
```
worker: extract → processing
  → publish_status_update (event_type=status_update)
  → _update_aggregate_status
    → publish_aggregate_status (event_type=aggregate_update)
worker: extract → completed
  → publish_status_update
  → _update_aggregate_status
    → publish_aggregate_status   # agg_status может быть тот же!
```

То есть на каждый этап летит **минимум 2 события**, и часто `aggregate_update` дублируется (статус не меняется).

### 1.3 Проблемы текущей реализации

| # | Проблема | Симптом |
|---|----------|---------|
| 1 | `aggregate_update` шлётся даже когда `agg_status` не изменился | Шум, лишние события на коллекционный стрим |
| 2 | На фронте каждое SSE событие → `invalidateQueries` → HTTP refetch | Шторм запросов `documents?page=1&size=500` |
| 3 | Один Redis канал на всё → SSE endpoint вынужден фильтровать в Python | Лишняя работа, шум по сети между Redis и API |
| 4 | Два SSE соединения в dev из-за React StrictMode | 2 подписчика, удвоение нагрузки в dev |
| 5 | Membership cache на старте стрима — снапшот на момент открытия (был, удалён) | Новые документы не попадают |
| 6 | Дублирующийся `tenant_id`-резолв в каждом publisher | Лёгкое усложнение |
| 7 | Нет snapshot при подключении — клиент должен делать отдельный HTTP | Race между HTTP и первым SSE событием |

---

## 2. Целевая архитектура

### 2.1 Принципы

1. **Push-only после snapshot** — при подключении SSE сразу пушит снапшот, дальше только дельты. Никаких HTTP refetch на каждое событие.
2. **Раздельные каналы Redis** — `rag:agg:{scope}` (агрегаты + lifecycle) и `rag:doc:{doc_id}` (этапы конкретного документа). SSE endpoint просто пересылает то, что прилетает в его канал, без фильтрации по типу.
3. **Дедупликация на источнике** — `publish_aggregate_status` шлёт только если `agg_status` действительно изменился (или изменились видимые на UI поля).
4. **Один SSE на страницу, один SSE на модалку** — никаких смешанных подписок.
5. **Frontend применяет дельты к кэшу через `setQueryData`** — не вызывая HTTP refetch.

### 2.2 Каналы Redis

| Канал | Что публикуется | Кто читает |
|-------|-----------------|------------|
| `rag:agg:admin` | `aggregate_update`, `document_archived`, `document_unarchived`, `document_deleted` | Коллекционный SSE для admin |
| `rag:agg:tenant:{tenant_id}` | то же, но per-tenant | Коллекционный SSE для не-admin |
| `rag:doc:{doc_id}` | `status_update`, `aggregate_update`, lifecycle | Документный SSE (модалка) |

`status_update` события **не идут** в `rag:agg:*` — это убирает шум для коллекционной подписки на корню.

### 2.3 SSE endpoints

**`GET /api/v1/collections/{collection_id}/status/events`**
1. Subscribe на `rag:agg:{scope}`.
2. Первое сообщение — `snapshot` event с массивом `[{document_id, agg_status, agg_details_summary, archived}]` для всех документов коллекции.
3. Далее — пересылает события из канала AS-IS, фильтруя по `event.document_id ∈ collection_doc_ids` (с lazy-обновлением списка при `document_added`/`document_deleted`).

**`GET /api/v1/collections/{collection_id}/docs/{doc_id}/status/events`**
1. Subscribe на `rag:doc:{doc_id}`.
2. Первое сообщение — `snapshot` event с полным `StatusGraphResponse`.
3. Далее — пересылает все события AS-IS.

### 2.4 Frontend контракт

**Коллекционная страница:**
```ts
// Один useEffect на mount:
//  1. Открыть SSE
//  2. На 'snapshot' — setQueryData (заменить список целиком)
//  3. На 'aggregate_update' — patch одного документа в кэше через setQueryData
//  4. На 'document_archived' / 'document_unarchived' — patch одного документа
//  5. На 'document_deleted' — удалить из кэша
//  6. cleanup → disconnect
```

Никаких `invalidateQueries` от SSE. Только `setQueryData`. HTTP `GET /documents` вызывается **один раз** при первом mount + polling раз в 30s через `staleTime` для устойчивости к разрывам.

**Модалка:**
```ts
// Один useEffect на open:
//  1. Открыть SSE per-doc
//  2. На 'snapshot' — setQueryData (StatusGraphResponse)
//  3. На любое событие — setQueryData (или invalidate если структура сильно меняется)
//  4. cleanup → disconnect
```

---

## 3. Этапы реализации

### Этап 0 — Cookie-only auth для SSE

**Файлы:**
- `apps/web/src/shared/lib/sse.ts`
- `apps/api/src/app/api/deps.py` (опционально, для cleanup после миграции)
- Login flow — проверить что cookie выставляется правильно.

**Шаги:**
1. Проверить в DevTools → Application → Cookies: после логина есть `access_token` httpOnly с правильными атрибутами.
2. Проверить CORS: `Access-Control-Allow-Credentials: true`, `Access-Control-Allow-Origin` = конкретный origin.
3. В `SSEClient.connect()` убрать блок добавления `?token=` (оставить только `withCredentials: true`).
4. Удалить `getAccessToken` из всех вызовов `openSSE` / `new SSEClient` в проекте (grep по проекту).
5. Удалить параметр из типа `SSEClientOptions` и `openSSE`.
6. (Опционально, отдельный PR) Удалить query-fallback в `get_current_user_sse`.

**Acceptance:**
- Network tab: SSE запрос без `?token=`, заголовок `Cookie: access_token=...`.
- Стрим работает в prod-сборке.

### Этап 1 — Backend: разделение каналов и дедупликация

**Файлы:**
- `apps/api/src/app/services/rag_event_publisher.py`
- `apps/api/src/app/services/rag_status_manager.py`

**Шаги:**
1. Ввести константы каналов:
   ```python
   CHANNEL_AGG_ADMIN = "rag:agg:admin"
   CHANNEL_AGG_TENANT_FMT = "rag:agg:tenant:{tenant_id}"
   CHANNEL_DOC_FMT = "rag:doc:{doc_id}"
   ```
2. `publish_status_update` → публикует **только** в `rag:doc:{doc_id}`.
3. `publish_aggregate_status` → публикует в `rag:agg:admin`, `rag:agg:tenant:{tenant_id}`, и **продублировать** в `rag:doc:{doc_id}` (модалка тоже хочет видеть смену агрегата).
4. `publish_document_archived/unarchived` → в `rag:agg:*` + `rag:doc:{doc_id}`.
5. **Дедупликация в `_update_aggregate_status`**: сравнить новый `(agg_status, effective_status)` со старым, перед `UPDATE` и `publish`. Если ничего user-visible не изменилось — не публиковать.
6. Удалить старые каналы `CHANNEL_LEGACY` и упоминания в `RAGEventSubscriber`. Оставить только `subscribe_aggregate(scope)` и `subscribe_document(doc_id)` методы.

**Acceptance:**
- Запуск ingest одного документа порождает в `rag:agg:*` ровно столько `aggregate_update`, сколько раз менялся agg_status (типично 2: `uploaded` → `processing` → `ready`).
- В `rag:doc:{doc_id}` приходят все этапные события + те же агрегаты.

### Этап 2 — Backend: snapshot при подключении

**Файлы:**
- `apps/api/src/app/api/v1/routers/collections/stream_events.py`
- (возможно) `apps/api/src/app/services/rag_status_snapshot.py` (новый)

**Шаги:**
1. Создать сервис `build_collection_snapshot(session, collection_id)` → список `{document_id, agg_status, agg_details_summary, archived, updated_at}`.
2. Создать сервис `build_document_snapshot(session, doc_id)` → `StatusGraphResponse` (используя существующую логику из роутера).
3. В `stream_collection_aggregate_status` — первым сообщением слать `event: snapshot` с массивом.
4. В `stream_document_status` — первым сообщением слать `event: snapshot` с графом.
5. Lazy-resolve membership: подписаться **внутри** generator на `rag:agg:{scope}`, фильтровать по `event.document_id ∈ collection_doc_ids`. Список doc_ids обновлять при получении `document_added`/`document_deleted` (новые события).
6. Добавить публикацию `document_added` в `CollectionDocumentUploadService` и `document_deleted` в delete handler.
7. **Периодический resync**: в коллекционном generator каждые 60 секунд (через `asyncio.wait_for` timeout) перечитывать snapshot и слать его как `event: snapshot`. Это гарантирует устойчивость к потере событий в Redis pub/sub. Документный generator resync не делает.

**Acceptance:**
- При открытии стрима первое SSE событие — `event: snapshot` с заполненным массивом.
- Загрузка нового документа → `document_added` event → стрим начинает пропускать его aggregate события.
- Каждые 60s в стриме появляется фоновый `event: snapshot` — фронт перезаписывает кэш.

### Этап 3 — Frontend: переход на patch-based кэш

**Файлы:**
- `apps/web/src/domains/collections/pages/CollectionDataPage.tsx`
- `apps/web/src/domains/rag/components/StatusModalNew.tsx`
- `apps/web/src/shared/api/hooks/useCollectionDocumentsStream.ts` (новый)
- `apps/web/src/shared/api/hooks/useDocumentStatusStream.ts` (новый)

**Шаги:**
1. Создать хук `useCollectionDocumentsStream(collectionId)`:
   - Управляет одним SSE клиентом.
   - На `snapshot` → `queryClient.setQueryData(['collections','documents',collectionId], snapshotItems)`.
   - На `aggregate_update` → `setQueryData(..., old => patchOne(old, payload))`.
   - На `document_added`/`document_deleted` → инвалидация (редкое событие).
   - На разрыв (onerror) → один `invalidateQueries` чтобы синхронизироваться после reconnect.
2. Создать хук `useDocumentStatusStream(collectionId, docId)`:
   - На `snapshot` → `setQueryData(['collections','doc-status',docId], snapshot)`.
   - На любое событие → инкрементальный merge или просто replace (StatusGraph меняется атомарно).
3. Удалить из `CollectionDataPage` весь код управления `SSEClient` напрямую.
4. Удалить из `StatusModalNew` весь код управления `openSSE` напрямую.
5. Уже существующий `useQuery` оставить как fallback (initial fetch до прихода snapshot + при разрыве).
6. **StrictMode guard**: в новых хуках использовать `useRef` для idempotent connect (отдельный helper `useStableSSE` который защищён от double-mount). Решение опциональное — можно оставить 2 соединения в dev.

**Acceptance:**
- Открытие страницы коллекции → 1 SSE соединение → 1 HTTP `GET /documents` (initial) → дальше никаких HTTP до polling 30s.
- Изменение статуса документа на бэке → виден в UI без HTTP запроса.

### Этап 4 — Cleanup и удаление мёртвого кода

**Файлы:**
- Удалить `_resolve_document_membership` если больше не используется в стримах.
- Удалить `invalidateDocsRef`, `collectionSseRef`, прямой код в `CollectionDataPage` (после миграции на хук).
- Удалить legacy `?document_id=` в `getStatusEventsUrl` (уже сделано).
- Привести `RAGEventSubscriber` к минимальному API: `subscribe_aggregate`, `subscribe_document`, `listen`, `unsubscribe`.

### Этап 5 — Тесты

#### Backend (`apps/api/tests/`)

1. **Unit** `test_rag_event_publisher_dedupe.py`:
   - Вызов `publish_aggregate_status` дважды подряд с тем же значением → одна публикация.
   - Изменение `agg_status` → новая публикация.
2. **Unit** `test_rag_event_channels.py`:
   - `publish_status_update` публикует **только** в `rag:doc:{doc_id}`, не в `rag:agg:*`.
   - `publish_aggregate_status` публикует в `rag:agg:*` и в `rag:doc:{doc_id}`.
3. **Integration** `test_collection_stream_snapshot.py`:
   - Создать коллекцию с 3 документами → подключиться к SSE → первое событие `snapshot` с 3 элементами.
4. **Integration** `test_collection_stream_delta.py`:
   - Подключиться → имитировать `aggregate_update` → клиент получает событие.
5. **Integration** `test_document_stream.py`:
   - Подключиться к doc-stream → имитировать `status_update` для extract → получаем событие.
   - `status_update` другого документа не приходит.

#### Frontend (`apps/web/`)

1. **Unit** хука `useCollectionDocumentsStream.test.ts`:
   - Mock SSE → snapshot event → проверить `setQueryData` вызван с массивом.
   - aggregate_update event → проверить patch одного элемента.
2. **Unit** хука `useDocumentStatusStream.test.ts`:
   - Snapshot → setQueryData вызван.
   - status_update → setQueryData merge.
3. **Playwright e2e** `collection-status-stream.spec.ts`:
   - Открыть страницу коллекции с документом в `processing`.
   - Через API форсировать переход в `ready`.
   - Проверить что строка документа в UI стала `Готов` без перезагрузки.

### Этап 6 — Документация

**Файлы:**
- `docs/sse-status-streams.md` (новый) — описание каналов, событий, payload'ов.
- Обновить `docs/architecture.md` если есть.
- JSDoc на новых хуках.
- Docstrings на новых сервисах.

**Содержание `docs/sse-status-streams.md`:**
- Diagram: worker → publisher → Redis channels → SSE endpoints → frontend.
- Event types и их JSON-схемы.
- Контракт snapshot.
- Поведение при reconnect.
- Как тестировать локально (`docker exec redis-cli PUBLISH ...`).

---

## 4. Принятые архитектурные решения

### 4.1 Аутентификация — cookie-only

Текущее состояние:
- Бэкенд (`get_current_user_sse`) уже принимает токен из httpOnly cookie `access_token` и из `Authorization` header. Query-параметр `?token=` оставлен как dev-fallback.
- Фронтовый `SSEClient` приклеивает `?token=` через `getAccessToken()`, при этом `EventSource` создаётся с `withCredentials: true`.

Целевое состояние:
- Браузер шлёт SSE с httpOnly cookie автоматически. Никаких токенов в URL.
- Query-fallback на бэке оставить только для `ENV != production` (уже так), но фронт **никогда** его не использует.

**Этап 0 (выполнить до Этапа 3):**
1. Убедиться что login flow выставляет `access_token` httpOnly cookie с `SameSite=Lax`, `Secure` (в prod), `Path=/`.
2. Проверить что CORS на API: `Access-Control-Allow-Credentials: true` и `Access-Control-Allow-Origin` — конкретный origin (не `*`).
3. В `SSEClient.connect()` убрать ветку `getAccessToken` для production. Оставить только `withCredentials: true`.
4. Убрать `getAccessToken` из вызовов `new SSEClient(...)` в коллекционной странице и модалке (после миграции на новые хуки).
5. Удалить параметр `getAccessToken` из публичного API хуков SSE.
6. Удалить query-fallback в `get_current_user_sse` после успешной миграции (опционально, в отдельный PR).

**Risks:** cookie не отправляется при cross-origin без правильных заголовков. Тест в staging обязателен.

### 4.2 Reconnect стратегия

- Использовать **нативный auto-reconnect** `EventSource` (он экспоненциальный по умолчанию в Chromium ~3-30s).
- При reconnect бэкенд **снова шлёт snapshot** первым событием → клиент гарантированно синхронизируется. Никакой ручной логики реконнекта на фронте не нужно.
- Никаких `Last-Event-Id` для дельт — мы не строим event log, а полагаемся на snapshot-on-connect.
- Если соединение в `readyState === CLOSED` дольше 60s — хук покажет toast "Realtime updates disconnected" и упадёт обратно на HTTP polling через `staleTime`.

### 4.3 Архивированные документы в snapshot

- Snapshot **включает** только активные (не-архивные) документы коллекции, **в соответствии с фильтром `GET /documents`** (там сейчас `status != archived`).
- При архивации документа бэкенд шлёт `document_archived` event → фронт удаляет из кэша.
- Если страница "Архив" в UI — отдельный SSE-стрим / отдельный фильтр (вне scope этого редизайна).

### 4.4 Multi-tenant

- `tenant_id` определяется на момент connect из JWT в cookie.
- Смена tenant'а на фронте — full page reload (так и сейчас работает в проекте). SSE переподключается естественно.

### 4.5 Backpressure / потеря событий

- Redis pub/sub без persistence: при медленном чтении возможна потеря.
- Mitigation: **периодический snapshot-resync каждые 60s** на коллекционном стриме (бэкенд сам шлёт `event: snapshot` раз в минуту). Фронт при snapshot перезаписывает кэш через `setQueryData` целиком. Это и страховка, и гарантия eventual consistency.
- Документный стрим (модалка) — без resync, она открыта недолго.

---

## 5. Risks & Mitigation

| Риск | Mitigation |
|------|-----------|
| Дублирование событий после reconnect | Использовать `event.id` (timestamp + version) для idempotency на фронте |
| Snapshot большой (1000+ документов) | Пагинация snapshot'а по 100, либо передача только `agg_status` без `agg_details` |
| Гонка snapshot vs первое delta-событие | Buffer события до получения snapshot, потом применять в порядке прихода |
| Падение Redis | Fallback на HTTP polling каждые 30s через `staleTime` (уже есть) |
| Worker публикует в неправильный канал | Линтер тестов + integration тест на каждый publish метод |

---

## 6. Estimate

- Этап 0: 0.25 дня (cookie auth migration)
- Этап 1: 0.5 дня (publisher rework + dedup)
- Этап 2: 0.75 дня (snapshot + periodic resync + new lifecycle events)
- Этап 3: 1 день (frontend хуки + миграция компонентов)
- Этап 4: 0.5 дня (cleanup)
- Этап 5: 1 день (тесты backend + frontend)
- Этап 6: 0.25 дня (доки)

**Total: ~4.25 дня.**

---

## 7. Порядок исполнения

1. **Этап 0** — изолированный, не ломает текущий функционал (cookie уже работает параллельно с token).
2. **Этап 1 + 2 + добавление новых событий + дедупликация** — одним PR на бэке, тесты сразу.
3. **Этап 3** — фронт мигрирует на новые хуки, удаляет прямой код.
4. **Этап 4** — cleanup мёртвого кода (только после прогона на staging).
5. **Этап 5** — тесты пишутся параллельно с этапами 1-3, но финальный прогон после 4.
6. **Этап 6** — доки финализируются последними.

Каждый этап — отдельный PR, мерджим только после code review.
