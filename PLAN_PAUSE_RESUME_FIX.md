# План фикса Pause/Resume (Chat + Sandbox)

## Контекст

Текущее состояние сломано в трёх местах:

1. **Песочница вместо resume запускает новый run** — пользователь жмёт "Ответить" на вопрос → создаётся новый `SandboxRun`, рантайм гоняется второй раз с нуля.
2. **Текст вопроса агента дублируется** — приходит как `chunk`/delta-стрим (попадает в `finalContent` → карточка "Ответ"), и тот же текст приходит как `waiting_input`/`confirmation_required` → попадает в поле ввода. На скриншоте оба видны одновременно.
3. **Архитектурно неверно**: Q&A разбросан между `delta`-сообщениями, паузой и user-message нового рана. Должен быть **отдельный step `answer`** в трейсе с парой `{question, answer}`, видимый только в инспекторе. В ленте сообщений Q&A не отображается как отдельные сообщения/карточки.

---

## Этап 1. Починить корневой баг — resume вместо нового run в песочнице

### Цель
При нажатии "Ответить" в режиме паузы (`waiting_input` или `waiting_confirmation`) фронт **должен вызывать resume-эндпоинт того же `AgentRun`**, а не создавать новый `SandboxRun`.

### Корень
`apps/web/src/domains/sandbox/components/RunChat.tsx:515-519`:

```ts
const handleClarifySubmit = () => {
  const text = input.trim();
  if (!text || attachments.length > 0) return;
  onRun(text, isWaitingInput ? activeRun.runId : undefined); // ← создаёт новый run
};
```

`onRun` — это `sandboxRun.run` (новый запуск). Resume вообще не вызывается из этой ветки.

### Что менять

**`apps/web/src/domains/sandbox/components/RunChat.tsx`**
- Добавить в `Props` поле `onResumeSubmit: (text: string) => void`.
- В `handleClarifySubmit` вызывать `onResumeSubmit(text)` вместо `onRun`.

**`apps/web/src/domains/sandbox/pages/SandboxSessionPage.tsx`**
- Передавать в `<RunChat onResumeSubmit={...}>`:
  ```ts
  onResumeSubmit={(text) => sandboxRun.confirmAction(true, text)}
  ```
- `confirmAction` уже корректно зовёт `sandboxApi.resumeRun` с SSE-стримом и `resumed_from_run_id`.

**`apps/web/src/domains/sandbox/hooks/useSandboxRun.ts`**
- Убедиться, что `confirmAction` корректно работает и для `waiting_input` (не только `waiting_confirmation`).
- Backend `/runs/{run_id}/resume` уже принимает `user_input` и пробрасывает в `continuation_meta` → ничего не менять.

### Результат
- Нажатие "Ответить" не создаёт новый `SandboxRun`.
- Бранч остаётся `main · 1`, трейс продолжается тем же `AgentRun` (continuity).
- В БД нет дубликата SandboxRun с `request_text="подтверждаю"`.

### Тест
- Запустить sandbox-run с просьбой подтверждения.
- В сетевом логе после "Ответить" видно `POST /sessions/.../runs/.../resume` (а не `/run`).
- В UI бранч показывает 1 ран, трейс единый.

---

## Этап 2. Убрать дубль "Ответ" с текстом вопроса агента

### Цель
В состоянии паузы карточка "Ответ" (`ChatAnswerCard`) **не должна** показывать текст вопроса агента. Вопрос — только в заголовке поля ввода.

### Корень
1. Агент шлёт вопрос как обычный текстовый стрим → события `chunk`/`delta` → `useSandboxRun.ts:346-348` аккумулируют в `activeRun.finalContent`.
2. `RunChat.tsx:583-588` рендерит `finalContent` в `ChatAnswerCard` как "Ответ".
3. Затем приходит `waiting_input`/`confirmation_required` → тот же текст в поле ввода → визуальный дубль.

### Что менять

**`apps/web/src/domains/sandbox/hooks/useSandboxRun.ts`** (и в `run`, и в `confirmAction`):
- При получении `waiting_input` / `confirmation_required` / `run_paused` **сбросить** `finalContent` в `''` (это был текст вопроса, а не финальный ответ).
- Опционально: не аккумулировать `chunk` в `finalContent`, если `activeRun.status` уже `waiting_*`.

**`apps/web/src/domains/sandbox/components/RunChat.tsx`**
- Условие показа `ChatAnswerCard` (`showActiveAnswerCard`) убрать показ при паузе:
  ```ts
  const showActiveAnswerCard = (isRunning || activeRun.finalContent.trim().length > 0)
    && !isWaitingInput
    && activeRun.status !== 'waiting_confirmation';
  ```
- Убрать ветку `if (isWaitingInput && latestClarifyQuestion) return latestClarifyQuestion` из `activeAssistantMessage` (вопрос больше не в "Ответ").

**Чат (`Chat.tsx` / `ChatContext.tsx`)**: симметрично — при `waiting_input`/`confirmation_required` удалить последнее ассистент-сообщение, если его контент совпадает с вопросом из события (уже частично сделано, проверить корректность работы — текст сравнивать по trim).

### Результат
- В UI паузы карточка "Ответ" не показывается.
- Вопрос виден только в заголовке поля ввода.
- В чате нет ассистент-сообщения с тем же текстом, что и в инпуте.

### Тест
- Запустить sandbox-run, дойти до паузы.
- На экране только: "Вопрос" (исходный запрос пользователя) → trace-стэпы → поле ввода с заголовком-вопросом. Никакой "Ответ" карточки.

---

## Этап 3. Q&A как отдельный step `answer` в трейсе

### Цель
Каждый цикл "вопрос агента → ответ пользователя" сохраняется как **отдельный шаг типа `answer`** в трейсе рана. Виден только в трейсе/инспекторе. В ленте сообщений (chat) и в карточках (sandbox) не отображается.

### Что менять

#### Бэкенд

**`apps/api/src/app/runtime/pipeline.py`** (или `chat_router_event_mapper.py` / `chat_stream_service.py`):
- При запуске resume-ветки (когда в `continuation_meta` есть `resume_checkpoint`) **до** продолжения исполнения эмитить событие:
  ```python
  RuntimeEvent(
      type="answer",
      data={
          "question": paused_context.get("question") or paused_action.get("question"),
          "answer": user_input,
          "resume_action": resume_action,  # "input" | "confirm"
          "paused_at_step": ...,  # optional
      },
  )
  ```
- Это событие должно проходить через стрим, маппиться в SSE как `event: answer`, и попадать в `add_run_step(step_type='answer', ...)`.

**`apps/api/src/app/services/sandbox/run_manager.py` / `sandbox_service.py`**: убедиться, что `add_run_step` принимает `step_type='answer'` без валидации против белого списка (или добавить в список).

**`apps/api/src/app/schemas/chat_events.py`**: добавить `ChatSSEEventType.ANSWER = "answer"`, payload `{question, answer, resume_action}`.

#### Фронт

**`apps/web/src/domains/sandbox/hooks/useSandboxRun.ts`**:
- Удалить старую `question_answer`-логику.
- Принимать `answer` event и добавлять в `steps` через `addStep('answer', data)`.

**`apps/web/src/domains/sandbox/components/TraceSteps`** (или соответствующий рендер):
- Добавить визуализацию step `answer` — компактная карточка "В: ... → О: ..." (без больших панелей).

**`apps/web/src/domains/sandbox/components/entityInspector/kinds/`**:
- Создать `AnswerInspectorTabs.tsx` с вкладками "Информация / Вопрос / Ответ / Raw".

**`apps/web/src/domains/chat/contexts/ChatContext.tsx`**:
- На `answer`-событии **не** добавлять сообщение в чат-ленту (только обновить trace, если она есть в чате — сейчас в чате trace не показывается → просто игнорировать в ленте).

### Результат
- В трейсе рана появляется отдельный шаг `answer` между шагами до/после паузы.
- В инспекторе шага видны вопрос и ответ.
- Ни в ленте чата, ни в карточках песочницы Q&A как отдельный визуальный элемент не показывается.
- Continuity рана сохраняется (один `AgentRun`).

### Тест
- Sandbox: запустить run с подтверждением, ответить — в трейсе виден шаг `answer` с Q&A.
- Кликнуть на шаг — инспектор показывает вкладки с вопросом и ответом.
- Chat: после ответа на clarify в trace (если включена) виден шаг `answer`, в ленте чата ничего нового не появилось.

---

## Порядок реализации

1. **Этап 1** — критичный, без него ничего не работает. Маленькие правки во фронте sandbox.
2. **Этап 2** — UX-фикс, маленькие правки во фронте.
3. **Этап 3** — архитектурный, требует согласованных правок бэка + фронта + инспектора.

После каждого этапа — ручной smoke-тест по описанию выше, перед переходом к следующему.

## Forbidden / Out of scope

- Не рефакторить `RuntimePipeline` целиком.
- Не менять контракт `PipelineRequest`/`continuation_meta` помимо добавления данных в `answer`-event.
- Не добавлять Q&A в ленту сообщений чата ни в каком виде.
