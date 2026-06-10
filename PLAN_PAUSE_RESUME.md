# План: починка паузы и резюма runtime

## Принцип

- Один логический "разговор" — один `AgentRun` (чат) или `SandboxRun` (песочница).
- Pause/resume = продолжение **того же** ран-объекта, а не новый.
- Песочница и чат идут через **тот же RuntimePipeline**. Различие только:
  - `logging_level` (full в песочнице),
  - `await_background_tail` (True в песочнице → видим memory phase в стриме).
- Ветвление (`parent_run_id`) остаётся только для осознанных branch-сценариев пользователя в песочнице, а не для каждого clarify/confirm.

## Найденные баги (контекст)

1. **`pipeline.pause_run` затирает `paused_action={}` / `paused_context={}`** (`apps/api/src/app/runtime/pipeline.py:416-421`) — перезаписывает корректную запись, которую успели сделать sandbox runs endpoint или ChatTurnOrchestrator. В чате это приводит к тому, что resume-эндпоинт читает `{}` из `AgentRun.paused_action` и не может ни выпустить confirmation_token, ни собрать вопрос.
2. **Чат: `POST /chats/runs/{id}/resume` — обычный JSON, не SSE.** `ChatResumeOrchestrator.continue_chat` глотает все события (`async for event in send_message_stream`), отдаёт только финальный JSON. UI ждёт всё в спиннере, потом делает `loadMessages(chatId)`. Никаких deltas/planner-step'ов на резюме.
3. **Песочница: каждый confirm/input резюм = новый SandboxRun + новый snapshot** через `parent_run_id`. Старый run остаётся `confirmed`/`waiting_*`, без финального ответа, но с inline-memory-фазой (т.к. `await_background_tail=True`). Жалоба "новый трейс, старый без результата" — ровно про это.
4. **Песочница: нет резюма для `waiting_input` (clarify).** `/confirm` обрабатывает только write-фингерпринты, отдельного `input`-эндпоинта нет; чатовый `/chats/runs/{id}/resume` для sandbox-ранов недоступен (`chat_id=None`).

---

## Бэк (только дополнения и фиксы поведения, без переделки runtime)

### 1. Pipeline — не затирать paused-данные
`apps/api/src/app/runtime/pipeline.py:410-421`.

Убрать вызов `self._run_store.pause_run(... paused_action={}, paused_context={})` целиком. Запись paused-state — задача обвязок (sandbox runs endpoint и ChatTurnOrchestrator), которые знают полные данные из STOP-события. Pipeline в этой ветке должен только зафиксировать `status` через тонкий `run_store.set_run_status(run_id, status)` (или просто ничего не делать — статус выставится позже).

### 2. Чат — резюм через SSE
`apps/api/src/app/api/v1/routers/chat/messages.py:218-370` (`resume_run`).

Превратить ответ в `StreamingResponse(media_type="text/event-stream")`. Внутренний `ChatResumeOrchestrator.continue_chat` сейчас глотает события — переделать так, чтобы он **пробрасывал** события наружу, а терминальный JSON (`status`, `assistant_message_id`, `paused_again_*`) шёл финальным SSE-фреймом или event-ом `summary`. Никакого рефакторинга `chat_stream_service` — только обвязка.

### 3. Песочница — единый resume endpoint, продолжение того же run
Новый `POST /sandbox/sessions/{sid}/runs/{rid}/resume` (или расширить существующий `/confirm` до контракта `action: confirm|cancel|input` + `input?: string`). Контракт = чатовый, ответ — `StreamingResponse` SSE.

Логика:
- Прочитать `run.paused_action` / `run.paused_context` — должны быть полными после фикса в п.1.
- На `confirm` — выпустить `confirmation_token` через `RuntimeHitlProtocolService.extract_operation_fingerprint` + `get_confirmation_service().issue(...)` (как в чатовом resume).
- На `input` — собрать `resume_content` через `build_resume_content(...)` (тот же helper что у чата).
- Запустить `RuntimePipeline.execute(...)` с тем же `pipeline_request`, но обогащённым:
  - `confirmation_tokens=[token]` (или пусто для `input`)
  - `continuation_meta={"resume_checkpoint": ..., "resumed_from_run_id": str(rid), "resume_action": action}`
  - **тот же `run_id`** в request (не создавать новый AgentRun/SandboxRun).
- Перевести run из `waiting_*` → `running` через `SandboxService.set_run_status` (не финишить).
- События пишутся в **тот же `SandboxRun.id`** через `add_run_step`, продолжение `order_num` (`max(order_num)+1`).
- На финале — `finish_run(rid, "completed", ...)` как обычно.

Старый `parent_run_id`-путь оставить только для явного ветвления; в UI не использовать его на резюме.

### 4. RuntimePipeline — поддержать "продолжение существующего run"
Ровно одно место: при создании `AgentRun` через `run_store.start_run(...)` сейчас всегда новая строка. Нужен флаг "use existing": если `pipeline_request.continuation_meta.resume_from_run_id` совпадает с существующим run в `waiting_*` — не создавать новый, а продолжить его (поднять `started_at`, очистить `finished_at`/`error`, выставить `running`).

Это маленькая правка в `RuntimePipeline._ensure_run_record` (или эквивалент). Без этого песочница и чат всё равно склонируют run, как сейчас.

### 5. Контракт `paused_action` / `paused_context` — единый
Сейчас sandbox endpoint строит payload через `RuntimeHitlProtocolService.build_paused_from_stop`, чат — через `chat_turn_orchestrator` (свой формат). Привести оба к выходу `RuntimeHitlProtocolService` чтобы `resume_run` (общий код) читал одинаково. Не рефакторинг — просто заменить chat-сборку на тот же helper.

---

## Фронт (без жёсткого рефакторинга)

### 6. Чат: SSE-резюм
`apps/web/src/domains/gpt/pages/Chat.tsx:140-160` и `apps/web/src/shared/api/chats.ts:88-108`.

Заменить `resumeRun` (JSON POST) на стрим-функцию по аналогии с `sendMessageStream` — тот же SSE-парсер, те же handler'ы (delta / planner_action / agent_status / final / stop / error), что использует `ChatContext`. Никакого `loadMessages(chatId)` после резюма — финальное сообщение прилетает через `final`-event, ChatContext его сам зарендерит.

### 7. Песочница: использовать новый resume endpoint
`apps/web/src/domains/sandbox/hooks/useSandboxRun.ts` (и кнопки confirm/clarify в UI песочницы).

- При `confirm` / `cancel` — вызывать новый `/sandbox/.../runs/{id}/resume` через тот же SSE-клиент, что используется для `/run`. Доклеивать события в текущую ленту steps (тот же `run_id`, новый order_num).
- При ответе на clarify — также `/resume` с `action='input'`, не `/run` с request_text.
- `/run` с `parent_run_id` оставить только для явного ветвления (если такая фича есть в UI — переименовать кнопку в "Создать ветку").

### 8. Tracer — снять костыль склейки родителей
Если sandbox перестанет порождать дочерние ранов на каждом резюме (пункты 3-4), то `RuntimeTraceBuilder` ничего склеивать не должен — всё уже одно дерево. Если останутся явные branch-ы — оставить им отдельную UX-логику (вкладка "Ветки"), не пихать в основное дерево.

### 9. Sandbox-чат UI — выровнять с основным чатом
Если в песочнице есть отдельный chat-компонент (sandbox chat), он должен использовать тот же `ChatContext`-стиль обработки событий: `confirmation_required` → `pendingConfirmations`, `waiting_input` → `pausedInput`, `stop` → `pausedRunId`. Не дублировать логику.

---

## Этапы

### Этап 1 — Бэк, минимальный фикс
1. Убрать затирание paused-данных в `pipeline.pause_run`.
2. Добавить флаг "use existing run" в `RuntimePipeline._ensure_run_record`.
3. Унифицировать сборку `paused_action`/`paused_context` через `RuntimeHitlProtocolService`.

### Этап 2 — Бэк, единый resume
4. `POST /chats/runs/{id}/resume` → SSE.
5. `POST /sandbox/.../runs/{id}/resume` (новый или расширенный `/confirm`) → SSE, тот же `RuntimePipeline`, тот же run_id.

### Этап 3 — Фронт
6. Чат: `resumeRun` через SSE, убрать `loadMessages` после резюма.
7. Песочница: вместо `/run` с `parent_run_id` использовать `/resume`.
8. Tracer: убрать ветки-склейки если они есть.

### Этап 4 — Уборка
9. Если песочница больше не использует `parent_run_id` для clarify/confirm — пометить эту схему как "только branch", навести порядок в `SandboxService` (отдельный метод `branch_from_run` для осознанного ветвления).

---

## Риски

- В `RuntimePipeline` шаг "продолжить существующий run" должен корректно собирать `RuntimeTurnState` из `paused_context.frozen_state` (если он там есть) и `resume_checkpoint`. Если такого пути нет — pipeline начнёт планер заново и может выбрать другого агента → потеря HITL-контекста. Перед фиксом проверить, восстанавливает ли `PlanningStage` состояние из checkpoint, или начинает с нуля.
- `SandboxRun.snapshot_id` — снепшот настроек на старте. При продолжении того же run сохраняем тот же snapshot (не создаём новый). Это то поведение, которое мы хотим: один run = один набор оверрайдов.
- Если backend начнёт продолжать тот же run, но фронт по старой логике вызовет `/run` с `parent_run_id` — получим конфликт. Бэк должен либо вернуть ошибку "run is paused, use /resume", либо UI обновить раньше бэка. Лучше включать на фронте сначала.
