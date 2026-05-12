# Trace Workbench — Execution Plan

Статус: draft
Owner: AI Platform
Связанные документы:
- `docs/refactor/trace-engineer-view-plan.md`
- `docs/refactor/runtime-trace-workbench-plan.md`
- `docs/refactor/chat-runtime-error-contract.md`

## Контекст

Текущая реализация трейсов и sandbox имеет рабочий фундамент (semantic trace contract, normalization layer, logging levels), но визуализация — на уровне "raw JSON debug view". Этот план фиксирует конкретные шаги для доведения до уровня "AI Engineer Workbench" с понятной диагностикой для админа.

Принципы:
- Минимальные upstream-фиксы, без переписывания контракта.
- Сначала чиним краши и видимые баги, потом UX, потом фичи.
- Каждый пункт имеет проверяемый критерий выполнения (DoD).

---

## P0 — Краши и видимые баги

### [ ] 1. Fix: Sandbox hooks violation
**Файл:** `apps/web/src/domains/sandbox/components/ConfigPanel.tsx` (и/или `SandboxSessionPage.tsx`)

**Симптом:** "Rendered more hooks than during the previous render" при переключении на run inspector.

**Корневая причина:** ранний `return` для `selectedItem.type === 'run'` стоит ПОСЛЕ серии `useQuery`/`useMemo`/`useEffect`, которые зависят от `selectedItem`. Когда `selectedItem` меняет тип, набор активных условий меняется, и порядок/количество хуков расходится между рендерами.

**Действие:**
- Вынести `RunInspector` ветку в отдельный sibling-компонент на уровне `SandboxSessionPage`, не возвращать его из середины `ConfigPanel`.
- Либо: убрать ранний `return` и держать единый `ConfigPanel`, переключая контент в JSX (без изменения числа хуков).

**DoD:**
- Открытие run → клик по step → переключение обратно на agent/tool не вызывает React error.
- Console clean. Playwright/manual прогон: chat → run → step → config → step.

---

### [ ] 2. Fix: `[object Object]` в Budget/LLM/Operations диагностике
**Файл:** `apps/web/src/domains/admin/pages/AgentRunPage.tsx` (блоки `diagnostics.*`)

**Симптом:** `last budget: [object Object]`, аналогично в LLM/operations блоках.

**Корневая причина:** `String(obj)` или интерполяция объекта в JSX без сериализации.

**Действие:**
- Ввести типизированный компонент `<DiagnosticValue value={...} />`, который:
  - примитив → текст;
  - объект → форматированный key/value список (не JSON);
  - длинный объект → collapsible с превью первых N полей.

**DoD:**
- Ни одного `[object Object]` на странице ранса при любых данных.
- Для объекта показывается осмысленный preview (например, `kind=max_steps · used=10 · limit=10`).

---

### [ ] 3. Fix: Raw event payload "схлопывает окно"
**Файл:** `apps/web/src/domains/admin/pages/AgentRunPage.tsx` — `StepItem`

**Симптом:** клик по `<details>Raw event payload</details>` визуально "сворачивает" контент шага.

**Корневая причина:** клик по `<summary>` всплывает на `onClick={() => setExpanded(...)}` родительского `<div>`, который тогглит `expanded` шага.

**Действие:**
- `e.stopPropagation()` на `<details>` / `<summary>`.
- Заменить нативный `<details>` на контролируемый `Disclosure` компонент.

**DoD:**
- Открытие raw payload не закрывает родительский шаг.
- Состояние шага и состояние raw — независимы.

---

## P1 — UX визуализации трейса

### [ ] 4. Структурированный `TraceArtifactsView`
**Файл:** `apps/web/src/domains/runtimeTrace/components/TraceArtifactsView.tsx`

**Сейчас:** plain `<pre>JSON.stringify(value)</pre>` для каждой секции.

**Цель:** типизированные рендереры по категории артефакта.

**Действие:**
- `LLMRequestCard`: model, messages (collapsible per role), params (table), timeout/retries.
- `LLMResponseCard`: raw_response (collapsible), parsed_response (structured), validation (badge: ok/error).
- `OperationCard`: slug (badge), arguments (key/value), result (key/value), duration.
- `BudgetCard`: используется/лимит/осталось как 3 числа + полоса прогресса.
- `DecisionCard`: kind, rationale, agent_slug, phase_id.
- `ErrorContractCard`: code (badge), user_message, operator_message, retryable/recoverable флаги, details (collapsible).
- Fallback: JSON для неизвестного артефакта (но не как дефолт).

**DoD:**
- При `category=llm` пользователь видит модель, сообщения, ответ без раскрытия raw JSON.
- При `category=budget` видно бюджет в человеческом формате.
- Raw JSON доступен только через явный "Show raw" toggle.

---

### [ ] 5. Run Summary header
**Файл:** `apps/web/src/domains/admin/pages/AgentRunPage.tsx`

**Цель:** За 5 секунд понять, что произошло.

**Действие:** Карточка сверху с:
- Статус (success/failed/partial, цветной badge).
- Длительность (общая + по фазам).
- Кол-во шагов / итераций / LLM-вызовов / tool-вызовов.
- Бюджет: использовано/лимит.
- Error code + user_message, если упал.
- Agent slug + version.

**DoD:**
- Все 6 пунктов рендерятся из существующего `diagnostics` payload без новых backend-полей.
- Failure case явно выделен (красная рамка + код ошибки).

---

### [ ] 6. Phase Timeline
**Файл:** новый `apps/web/src/domains/runtimeTrace/components/PhaseTimeline.tsx`

**Цель:** Визуальная полоса фаз (input → routing → planning → execution → final) с количеством событий и длительностью.

**Действие:**
- Сгруппировать `SemanticEvent[]` по `phase`.
- Рендер: горизонтальная полоса с сегментами пропорционально `duration_ms`.
- Клик по сегменту → скролл к первому событию этой фазы.

**DoD:**
- Видно распределение времени между фазами.
- Клик работает, скролл попадает в нужный блок.

---

### [ ] 7. Категорийное цветовое кодирование шагов
**Файл:** `AgentRunPage.module.css` + `StepItem`

**Действие:**
- `category=error` → красная левая граница.
- `category=llm` → синяя.
- `category=operation` → зелёная.
- `category=budget|policy|retry` → жёлтая/оранжевая.
- `category=final` → акцент.
- Status `error` оверрайдит цвет в красный.

**DoD:**
- На скриншоте трейса визуально различимы типы шагов без чтения текста.

---

## P2 — Sandbox parity

### [ ] 8. Унифицировать RunInspector и AgentRunPage StepItem
**Файлы:** `RunInspector.tsx`, `ChatStepItem.tsx`, `AgentRunPage.tsx`

**Цель:** Один и тот же `<SemanticEventView>` примитив используется и в admin, и в sandbox.

**Действие:**
- Вынести `SemanticEventView` в `domains/runtimeTrace/components/`.
- Удалить дублирующую логику нормализации/рендера из `ChatStepItem` и `StepItem`.

**DoD:**
- Поиск по `extractTraceArtifacts` показывает использование только из shared компонента.
- Sandbox inspector и admin run page рендерят одинаково для одинаковых данных.

---

### [ ] 9. Sandbox всегда `full` logging, admin берёт из агента
**Файлы:** `apps/api/src/app/api/v1/routers/sandbox/runs.py`, `app/services/run_store.py`

**Действие:**
- В sandbox runs.py при `start_run` форсить `logging_level='full'` независимо от `agent.logging_level`.
- В admin chat path использовать `agent.logging_level` как сейчас.
- Документировать в коде комментарием.

**DoD:**
- Sandbox run всегда имеет `raw.data` со всеми payload (включая prompts/messages).
- Admin run для агента с `brief` не пишет payload, но пишет metadata.

---

## P3 — Адаптивность под logging level

### [ ] 10. UI адаптируется под `run.logging_level`
**Файл:** `AgentRunPage.tsx`, `RunInspector.tsx`

**Действие:**
- При `logging_level=brief`:
  - Не показывать пустые секции "LLM Request/Response".
  - Показывать баннер "Brief logging — payloads are not stored. Enable full logging for deep diagnostics."
- При `logging_level=none`:
  - Скрывать таб trace целиком, показывать только overview + final result.

**DoD:**
- Для `brief` ранса нет пустых блоков-заглушек.
- Для `none` UI не пытается отрисовать несуществующие шаги.

---

### [ ] 11. UI для смены logging level агента
**Файлы:** admin agent edit page

**Действие:**
- Select в редакторе агента: `none | brief | full`.
- Подсказка: "Use `full` for new/experimental agents, `brief` for production stable agents, `none` only for noise-heavy automations."

**DoD:**
- Изменение уровня сохраняется в БД.
- Новые run'ы агента пишутся согласно новому уровню (старые не меняются).

---

## P4 — Полировка

### [ ] 12. Поиск/фильтрация шагов в трейсе
- Поиск по `title`, `summary`, `slug`.
- Фильтр по `category`, `status`, `iteration`.
- **DoD:** для ранса с 50+ шагов админ может найти все `error` или все `llm` шаги одним кликом.

### [ ] 13. Копирование шага как JSON
- Кнопка "Copy raw" на каждом шаге.
- **DoD:** clipboard содержит валидный JSON шага.

### [ ] 14. Permalink на конкретный шаг
- URL с `?step=<id>` открывает страницу с раскрытым нужным шагом.
- **DoD:** ссылка восстанавливает состояние UI.

---

## Глобальные критерии готовности

- [ ] Все P0 закрыты — никаких визуальных багов и крашей.
- [ ] P1 закрыт — админ за 30 секунд диагностирует упавший ранс без чтения raw JSON.
- [ ] P2 закрыт — sandbox и admin используют один набор примитивов.
- [ ] P3 закрыт — UI честно отражает выбранный уровень логирования.
- [ ] Smoke-сценарий проходит:
  1. Запустить sandbox session, прогнать агент.
  2. Открыть run, видеть структурированную диагностику.
  3. В admin открыть production ранс агента с `brief` — видеть metadata view без пустот.
  4. Симулировать ошибку — видеть error contract карточку с кодом и сообщением.

---

## Что НЕ входит в этот план

- Изменение backend semantic trace contract (`RunTrace`, `SemanticEvent`) — он считается стабильным.
- Изменение схем БД для агента/ранса (используем существующие `logging_level` и `agent_run_steps.data`).
- Новые источники телеметрии (метрики/трассировка вне `agent_run_steps`).
- Перенос трейсов в OpenTelemetry/ClickHouse — отдельный трек.
