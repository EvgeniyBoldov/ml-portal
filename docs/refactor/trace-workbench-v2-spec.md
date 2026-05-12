# Trace Workbench v2 — Спецификация

## Контекст

Текущая визуализация Run ([`AgentRunPage.tsx`](../../apps/web/src/domains/admin/pages/AgentRunPage.tsx)) отображает агентский запуск как плоский список "итераций" с raw-шагами (`user_request`, `budget_policy`, `llm_request`, `operation_call`, `operation_result`, ...). Это отражает бэкенд-логгер, но **не отражает ментальную модель AI-инженера**, который дебажит запуск.

## Цель

Перестроить страницу Run так, чтобы она читалась как **отчёт о работе агента**, а не как дамп событий.

Страница делится на **3 логических блока**:
1. **Input** — что пришло на вход
2. **Trace Log** — что агент делал (timeline действий)
3. **Final** — финальный результат

Бэкенд **не трогаем** — работаем только с агрегацией на фронте.

---

## 1. Блок Input

Отдельная секция в начале страницы. Показывает **контекст запуска** — всё, что было дано агенту до старта исполнения.

### Содержимое:
- **Запрос пользователя** (`user_request.content`)
- **Лимиты** (`budget_policy` / `budget_init`): max_steps, max_tool_calls, max_retries, tool_timeout, wall_time
- **Конфигурация агента**: agent slug, version, logging level
- **Доступные инструменты** (tool bindings): список с пометкой tool_release если pinned
- **Доступные коллекции** (если релевантно): data sources
- **Tenant / User** (кратко)

### Компонент: `RunInputBlock`
- **Props:** `run`, `firstIteration` (для извлечения `user_request` и `budget_policy`)
- **Layout:** Компактная карточка с секциями (Запрос / Лимиты / Контекст)
- **Стиль:** accent-бордер слева (синий), как "входные данные"

---

## 2. Блок Trace Log

Timeline действий агента. Каждая **запись** = одно логическое действие (а не отдельный raw event).

### Типы записей (Trace Entries):

#### 2.1 LLM Call Entry
Объединяет `llm_request` + `llm_response` в одну карточку.

**Header (краткая форма):**
- Badge: `LLM`
- **Intent/Summary** — первое сообщение пользователя или описание задачи агента ("что попросили сделать LLM")
- Model (опционально)
- Справа: datetime, duration, toggle ▶

**Body (развернутая форма):**
- Messages (с цветовой дифференциацией ролей)
- Response content
- Model/temperature/max_tokens (детали)
- Token usage (если есть)

**Источник данных:** `llm_request` + соседний `llm_response` (matching по iteration + порядку)

#### 2.2 Tool Call Entry
Объединяет `operation_call` + `operation_result` (+ `protocol_retry` если были) в одну карточку.

**Header (краткая форма):**
- Badge: `TOOL`
- Имя инструмента (например `search_docs`)
- Статус: ✓ success / ✗ failed
- Если были retry: `↻ 2 retries`
- Справа: datetime, total duration, toggle ▶

**Body (развернутая форма):**
- **Input**: arguments (parsed JSON)
- **Output**: result / error
- **Retries** (если есть): список попыток с ошибками

**Источник данных:** `operation_call` + `operation_result`/`tool_result` + `protocol_retry` события в одной iteration

#### 2.3 Decision Entry
Routing / policy_decision события.

**Header:** `DECISION` + краткое решение (route to X, policy: allowed/blocked)

**Body:** детали решения, reasons

#### 2.4 Error Entry
Runtime errors, не относящиеся к операциям.

**Header:** `ERROR` + код ошибки

**Body:** error contract (code, user_message, operator_message, debug)

### Сквозное состояние: Budget Badge

**Каждая** карточка в Trace Log содержит badge `budget: steps 5/10 | tools 2/50` в header (правая часть, перед datetime).

**Вычисление:** frontend aggregator считает running state:
- При `llm_call` → steps++, tokens += response.tokens
- При `operation_call` → tool_calls++
- При `protocol_retry` → retries++

**Компонент:** `BudgetBadge`
- Props: `{ steps, maxSteps, tools, maxTools, tokens?, maxTokens? }`
- Отображение: компактная строка с цветовой подсветкой (90%+ — красный)

### Компонент: `RunTraceLog`
- **Props:** `traceEntries: TraceEntry[]`
- **Layout:** вертикальный список `TraceEntryCard`-ов
- **Нумерация:** сквозная (№1, №2, ...), итерации **убираем** как отдельные группы (они визуально не нужны в новой модели)

### Компонент: `TraceEntryCard`
Универсальная карточка для всех типов entries.

**Props:**
```typescript
{
  entry: TraceEntry;
  budget: BudgetState;
  index: number;
}
```

**Layout:**
```
┌─────────────────────────────────────────────┐
│ Header:                                      │
│   [Left]  №N | Type Badge | Summary         │
│   [Right] BudgetBadge | datetime | duration │
│           | toggle ▶                         │
├─────────────────────────────────────────────┤
│ Body (когда expanded):                       │
│   Тип-специфичный контент                    │
└─────────────────────────────────────────────┘
```

---

## 3. Блок Final

Финальный результат запуска.

### Содержимое:
- **Final answer** (`final` / `final_response` event)
- **Grounded in** (если есть — список refs/citations)
- **Runtime status**: completed / failed / stopped
- Если failed — **Error contract** (code, messages)
- **Hand-off**: если был вызов `agent_call` → ссылка на sub-run (это _другой_ run, просто линк)

### Компонент: `RunFinalBlock`
- **Props:** `run`, `lastIteration`
- **Layout:** карточка в конце страницы
- **Стиль:** accent-бордер слева (зелёный если success, красный если failed)

---

## 4. Агрегатор (Frontend)

### Модуль: `apps/web/src/domains/runtimeTrace/aggregator.ts`

Принимает `RunTrace` (от бэкенда) и строит новую структуру:

```typescript
interface AggregatedRun {
  input: RunInput;           // для RunInputBlock
  traceEntries: TraceEntry[]; // для RunTraceLog (с running budget)
  final: RunFinal;           // для RunFinalBlock
}

interface RunInput {
  userRequest: string;
  limits: BudgetLimits;
  agent: { slug, version, loggingLevel };
  tools: ToolBinding[];
  collections?: string[];
}

type TraceEntry =
  | { type: 'llm'; intent: string; request: LLMRequest; response?: LLMResponse; startedAt; durationMs; budgetSnapshot: BudgetState }
  | { type: 'tool'; toolName: string; input: unknown; output?: unknown; retries: RetryAttempt[]; status: 'success' | 'failed'; startedAt; durationMs; budgetSnapshot }
  | { type: 'decision'; kind: string; summary: string; details: unknown; startedAt; budgetSnapshot }
  | { type: 'error'; code: string; userMessage: string; operatorMessage: string; debug?: unknown; startedAt; budgetSnapshot };

interface BudgetState {
  steps: { used: number; limit: number };
  tools: { used: number; limit: number };
  retries: { used: number; limit: number };
  tokens?: { used: number; limit?: number };
}

interface RunFinal {
  status: 'completed' | 'failed' | 'stopped';
  answer?: string;
  groundedIn?: Reference[];
  error?: ErrorContract;
  handoffRunId?: string;
}
```

### Логика агрегации:

1. Проходим по `iterations` → flat список `SemanticEvent`
2. **Извлекаем Input**:
   - `user_request` event → `userRequest`
   - `budget_policy` / `budget_init` → `limits`
3. **Строим TraceEntries**:
   - Идём по events в порядке; для каждого события определяем, начинает ли оно новый entry или присоединяется к текущему:
     - `llm_request` → новый `llm` entry
     - `llm_response` → attach к последнему `llm` entry
     - `operation_call` / `tool_call` → новый `tool` entry
     - `operation_result` / `tool_result` → attach к последнему `tool` entry
     - `protocol_retry` → attach как retry к последнему `tool` entry
     - `routing` / `policy_decision` → `decision` entry
     - `error` → `error` entry (отдельный)
   - После создания каждого entry **вычисляем `budgetSnapshot`** (running state)
4. **Извлекаем Final**:
   - `final` / `final_response` event → `answer`
   - `run.runtime_status` + error поля → `status`/`error`

### Budget running calculator:

```typescript
function updateBudget(prev: BudgetState, entry: TraceEntry): BudgetState {
  const next = structuredClone(prev);
  if (entry.type === 'llm') {
    next.steps.used += 1;
    if (entry.response?.tokens) next.tokens.used += entry.response.tokens;
  }
  if (entry.type === 'tool') {
    next.tools.used += 1;
    next.retries.used += entry.retries.length;
  }
  return next;
}
```

---

## 5. Компоненты (итого)

### Новые:
| Компонент | Файл | Ответственность |
|---|---|---|
| `RunInputBlock` | `components/RunInputBlock.tsx` | Блок входных данных |
| `RunTraceLog` | `components/RunTraceLog.tsx` | Список trace entries |
| `TraceEntryCard` | `components/TraceEntryCard.tsx` | Универсальная карточка entry |
| `LLMEntryBody` | `components/entries/LLMEntryBody.tsx` | Тело LLM карточки (expanded) |
| `ToolEntryBody` | `components/entries/ToolEntryBody.tsx` | Тело Tool карточки (expanded) |
| `DecisionEntryBody` | `components/entries/DecisionEntryBody.tsx` | Тело Decision карточки |
| `ErrorEntryBody` | `components/entries/ErrorEntryBody.tsx` | Тело Error карточки |
| `BudgetBadge` | `components/BudgetBadge.tsx` | Компактный budget indicator |
| `RunFinalBlock` | `components/RunFinalBlock.tsx` | Блок финального ответа |
| `aggregator.ts` | `runtimeTrace/aggregator.ts` | Агрегатор SemanticEvent → TraceEntry |

### Удаляем / refactor:
- `StepItem` в `AgentRunPage.tsx` — заменяется на `TraceEntryCard`
- `TraceArtifactsView.tsx` — распадается на `*EntryBody.tsx` компоненты
- Группировка по iterations в `RunTraceLog` — **убираем** (или оставляем как optional marker)
- `PhaseTimeline` — **оставляем** как opt-in визуализация сверху

### Без изменений:
- Backend (`run_store`, `runtime_trace_builder`, SSE)
- `normalize.ts` (нормализация используется внутри aggregator)
- `artifacts.ts` (как утилита для извлечения payload'ов)

---

## 6. Разметка страницы `AgentRunPage`

```tsx
<EntityPageV2>
  <Tab title="Обзор">
    <RunSummary run={run} />
    {/* Diagnostics blocks — оставляем как есть */}
  </Tab>

  <Tab title="Трейс">
    <RunInputBlock input={aggregated.input} />
    <RunTraceLog entries={aggregated.traceEntries} />
    <RunFinalBlock final={aggregated.final} />
  </Tab>
</EntityPageV2>
```

---

## 7. План реализации (по шагам)

### Этап 1 — Типы и агрегатор
1. Создать `aggregator.ts` с типами `AggregatedRun`, `TraceEntry`, `BudgetState`
2. Реализовать `aggregateRun(trace: RunTrace, run: AgentRun): AggregatedRun`
3. Unit-тесты агрегатора на синтетических данных

### Этап 2 — Компоненты-каркас
4. `BudgetBadge` — простой компонент
5. `TraceEntryCard` — универсальная обёртка (header + toggle + slot для body)
6. `RunInputBlock` — статичный блок
7. `RunFinalBlock` — статичный блок

### Этап 3 — Бодики entries
8. `LLMEntryBody` (переиспользует логику текущего `LLMRequestCard`/`LLMResponseCard`)
9. `ToolEntryBody` (переиспользует `OperationCard`)
10. `DecisionEntryBody`
11. `ErrorEntryBody`

### Этап 4 — Интеграция
12. `RunTraceLog` — собирает всё вместе
13. Заменить секцию "Трейс" в `AgentRunPage` на новую структуру
14. Удалить старый `StepItem` из `AgentRunPage`

### Этап 5 — Полировка
15. Цветовая дифференциация карточек по типу (left border)
16. Keyboard shortcuts (expand all / collapse all)
17. Copy JSON / Copy link — в действия карточки

---

## 8. Что остаётся нерешённым (вопросы к обсуждению)

- **Sandbox parity**: нужна ли такая же структура в SandboxSessionPage? (скорее да, но отдельной задачей)
- **Raw payload**: оставляем ли `details` с JSON внизу каждой карточки для дебага? (предлагаю — да, как "Show raw")
- **Iterations**: совсем убираем или оставляем как визуальный marker/grouping? (предлагаю убрать — они не добавляют ценности в новой модели)
- **Hand-off к sub-agent**: как визуализировать (inline entry или ссылка в Final)? (предлагаю ссылку в Final)

---

## 9. Definition of Done

- [ ] Страница Run содержит 3 секции: Input / Trace Log / Final
- [ ] Trace Log показывает объединённые entries (LLM call / Tool call со всеми retries / Decision / Error)
- [ ] Каждая карточка имеет budget badge со sequential running state
- [ ] Краткая форма карточки показывает intent/tool name/decision summary (не JSON)
- [ ] Развернутая форма показывает детали (messages, args/result, retries)
- [ ] Финальный блок визуально отличается от trace (success/failed border color)
- [ ] Старый `StepItem` удалён, `TraceArtifactsView` рефакторён в `*EntryBody`
- [ ] Бэкенд не тронут
