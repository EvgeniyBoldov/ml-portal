# План: нормализация trace snapshot и инспекторов

## Цель

Сделать tracer и inspectors контрактными:

- backend фиксирует стартовый `context_snapshot` на lifecycle-событиях;
- frontend строит tree и inspector tabs из snapshot-данных;
- fallback по старым `steps` остается только для исторических логов и переходного периода.

Главный принцип: инспектор не угадывает промпт, RBAC и лимиты из соседних событий, если они уже были известны в момент старта сущности.

## Контракт `context_snapshot`

Все lifecycle `*_start` события могут нести:

```ts
context_snapshot: {
  inputs?: {
    user_request?: string
    goal?: string
    agent_input?: unknown
    planner_hint?: string
    iteration_intent?: string
  }
  system_prompt?: string
  system_prompt_hash?: string
  limits?: {
    planner_steps?: number
    agent_steps?: number
    tool_calls?: number
    tokens_in?: number
    tokens_out?: number
    tokens_total?: number
    retries?: number
    wall_time_ms?: number
  }
  rbac?: {
    candidates?: string[]
    allowed?: string[]
    denied?: string[]
    denied_by_rbac?: string[]
    denied_by_capability?: string[]
    reason?: Record<string, string>
  }
  meta?: {
    role?: string
    model?: string
    agent_slug?: string
    version_label?: string
    explicit_agent_slug?: string
    available_operations?: string[]
    available_agents?: string[]
    components?: string[]
    attempt?: number
    max_attempts?: number
    memory_digest?: {
      facts?: number
      summary_chars?: number
    }
  }
}
```

## Backend

### Принцип

`RuntimeEvent.*_start` уже поддерживают `**extra`, поэтому отдельное расширение фабрик не нужно. Нужна нормализация payload и систематическое заполнение `context_snapshot`.

### Что должно быть

1. `run_start`
- `inputs.user_request`
- `limits`
- `meta.agent_slug`
- `meta.model`

2. planner `orchestrator_start`
- `inputs.goal`
- `system_prompt` или `system_prompt_hash`
- `limits`
- `rbac`
- `meta.role = planner`
- `meta.model`

3. `planner_iteration_start`
- `inputs.goal`
- `inputs.iteration_intent`
- `limits`
- `meta.attempt`
- `meta.max_attempts`
- `meta.available_agents`
- `meta.memory_digest`

4. `agent_start`
- `inputs.goal`
- `inputs.agent_input`
- `system_prompt` compiled prompt версии агента
- `limits`
- `meta.role`
- `meta.agent_slug`
- `meta.model`
- `meta.version_label`
- `meta.available_operations`
- `rbac`

5. `synthesis_start`
- `inputs.goal`
- `inputs.planner_hint`
- `system_prompt`
- `limits`
- `meta.role = synthesizer`
- `meta.model`

6. memory `orchestrator_start`
- `inputs.user_request`
- `limits`
- `meta.role = memory`
- `meta.components`

7. memory component `agent_start` (`facts`, `conversation`)
- `inputs.user_request`
- `system_prompt`
- `limits`
- `meta.role`
- `meta.agent_slug`

### Логирование prompt

- при `logging_level=full` писать полный `system_prompt`
- при `brief` писать только `system_prompt_hash`

## Frontend

### Trace entity data

`RunData`, `OrchestratorData`, `PlannerData`, `AgentData` хранят:

- `contextSnapshot?: TraceContextSnapshot`

`buildEntityTree` переносит `raw.context_snapshot` из lifecycle event в `entity.data.contextSnapshot`.

### Snapshot getters

В `shared.tsx`:

- `getEntityContextSnapshot(entity)`
- `getEntityInputsSnapshot(entity)`
- `getEntityMetaSnapshot(entity)`
- `getEntityRbacSnapshot(entity)`
- `getEntityLimitsSnapshot(entity)`
- `getEntityPromptSnapshot(entity)`

Правило:

- сначала `entity.data.contextSnapshot`
- потом legacy `entity.data.context_snapshot`
- потом fallback по `steps` только для неснепшотных call payload

### Inspector contract

#### Entity snapshot inspectors

Показывают snapshot сущности, а не конкретный вызов.

- `Run`: `Параметры • Результат • Бюджет • RAW`
- planner orchestrator: `Параметры • Промпт • RBAC • Бюджет • RAW`
- synthesizer orchestrator: `Параметры • Промпт • Бюджет • RAW`
- memory orchestrator: `Параметры • Бюджет • RAW`
- agent: `Параметры • Задание • Промпт • Инструменты • RBAC • Бюджет • RAW`
- facts: `Параметры • Факты • Промпт • Бюджет • RAW`
- summary: `Параметры • Результат • Промпт • Бюджет • RAW`
- planner iteration: `Намерение • Решение • Бюджет • RAW`

#### Call inspectors

- `LLM`: `Инфо • Реквест • Респонс • Бюджет • RAW`
- `Tool`: `Инфо • Реквест • Респонс • Бюджет • Ошибки • RAW`

### Правила UI

- UUID не показывать в основных вкладках, только в `RAW`
- parent/caller refs humanize через tree registry, а не через сырой id
- бюджеты и лимиты для entity-снимков брать из snapshot + budget snapshots
- промпты брать из snapshot, а не искать по соседним step при наличии snapshot

## Порядок реализации

### Этап 1. Backend snapshot contract

1. Ввести helper для сборки `context_snapshot`
2. Проставить snapshot в:
   - `pipeline.py`
   - `planning_stage.py`
   - `planner_call_agent_dispatcher.py`
   - `synthesizer.py`
   - `tasks_memory.py`

### Этап 2. Frontend snapshot plumbing

3. Добавить `TraceContextSnapshot` в entity types
4. Переносить snapshot в `buildEntityTree`
5. Вынести общие getters в `shared.tsx`

### Этап 3. Inspector migration

6. `RunInspectorTabs`
7. `OrchestratorInspectorTabs`
8. `AgentInspectorTabs`
9. `PlannerInspectorTabs`
10. `LlmInspectorTabs`
11. `ToolInspectorTabs`

### Этап 4. Cleanup

12. После стабилизации убрать remaining fallback по старым non-snapshot структурам

## Риски

- memory и planner события идут параллельно с остальным runtime, поэтому фронт не должен восстанавливать snapshot по глобальному поиску без `entity_id`/`parent_entity_id`
- prompts могут быть большими; backend не должен резать snapshot, UI должен нормально рендерить длинный текст
- старые раны будут без `context_snapshot`, поэтому fallback по `steps` пока обязателен
