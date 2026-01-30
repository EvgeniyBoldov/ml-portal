# Agent System Entities

**Контекст:** Non-commercial проект. Агентов создают Админы-АИ инженеры (не end-users).

Таблица сущностей с приоритизацией для этого сценария.

---

## ✅ Уже реализовано

| Сущность | Назначение | Статус |
|----------|-----------|--------|
| **Agent** | Профиль агента (система промпт, базовый промпт, политика, инструменты) | ✅ Есть |
| **Tool** | Определение инструмента (схема, описание для LLM) | ✅ Есть |
| **ToolInstance** | Конкретное подключение (Jira-prod, NetBox-main, RAG-local) | ✅ Есть |
| **ToolGroup** | Группировка инструментов (jira, netbox, rag) | ✅ Есть |
| **Prompt** | Контейнер для промптов с версионированием | ✅ Есть |
| **PromptVersion** | Версия промпта (draft/active/archived) | ✅ Есть |
| **Policy** | Лимиты выполнения (max_steps, max_tokens, timeout) | ✅ Есть |
| **PermissionSet** | RBAC для агентов и инструментов (scope: default/tenant/user) | ✅ Есть |
| **CredentialSet** | Зашифрованные креденшалы (scope: tenant/user) | ✅ Есть |
| **AgentRun** | История запусков агента | ✅ Есть |
| **AgentRunStep** | Шаги выполнения (llm_request, tool_call, tool_result) | ✅ Есть |
| **AgentBinding** | Связь агента с инструментом и инстансом | ✅ Есть |
| **Collection** | Динамические коллекции данных (как локальный инструмент) | ✅ Есть |
| **RoutingLog** | Логирование решений маршрутизатора | ✅ Есть |

---

## 🔴 Критично (нужны сейчас)

### 1. ExecutionContext
```
ExecutionContext (новая)
├── id, run_id, user_id, tenant_id, agent_slug
├── input (user message)
├── context (loaded from RAG/DB)
├── execution_mode (full/partial/unavailable)
├── metadata (source=chat/ide/api, client_version)
└── created_at

Зачем: Отслеживание контекста выполнения для отладки и логирования.
Для кого: Админы-инженеры при отладке агентов.
```

**Приоритет:** 🔴 High — нужна для отладки и понимания что произошло.

---

### 2. ExecutionAudit
```
ExecutionAudit (новая)
├── id, execution_id, user_id, tenant_id, agent_slug
├── action (agent_invoked, tool_called, permission_denied, error)
├── resource (agent_slug, tool_slug, instance_slug)
├── result (success/failure)
├── error_message (если failure)
├── timestamp, duration_ms
└── metadata (ip, user_agent, request_id)

Зачем: Полный audit trail для отладки и анализа проблем.
Для кого: Админы-инженеры, техподдержка.
```

**Приоритет:** 🔴 High — критично для отладки и compliance.

---

### 3. ModelCost
```
ModelCost (новая)
├── model_id (FK to ModelRegistry)
├── provider (openai, groq, azure, local)
├── cost_per_1k_input_tokens (cents)
├── cost_per_1k_output_tokens (cents)
├── updated_at

Зачем: Отслеживание стоимости моделей для анализа затрат.
Для кого: Админы для мониторинга расходов.
```

**Приоритет:** 🔴 High — нужна для контроля затрат.

---

### 4. ExecutionCost
```
ExecutionCost (новая)
├── id, execution_id, user_id, tenant_id, agent_slug
├── model_used (model_id)
├── tokens_in, tokens_out
├── cost_cents
├── timestamp

Зачем: Отслеживание затрат на каждый запуск.
Для кого: Админы для анализа и оптимизации.
```

**Приоритет:** 🔴 High — нужна для понимания затрат.

---

### 5. ToolHealthCheck
```
ToolHealthCheck (новая)
├── id, tool_instance_id
├── status (healthy/degraded/unhealthy)
├── last_check_at, next_check_at
├── error_count, success_count (за последние N проверок)
├── avg_response_time_ms
├── error_message (если unhealthy)
├── metadata (http_status, response_time, etc.)

Зачем: Мониторинг здоровья инструментов.
Для кого: Админы для оперативного реагирования на проблемы.
```

**Приоритет:** 🔴 High — нужна для надёжности системы.

---

## 🟡 Важно (нужны в ближайшем будущем)

### 6. AgentMetrics
```
AgentMetrics (новая)
├── id, agent_id, period (day/week/month)
├── total_runs, successful_runs
├── success_rate (%)
├── avg_response_time_ms
├── avg_tokens_in, avg_tokens_out
├── total_cost_cents
├── error_rate_by_type (dict: error_type -> count)
├── top_errors (list of most common errors)

Зачем: Аналитика качества агентов для оптимизации.
Для кого: Админы-инженеры для улучшения агентов.
```

**Приоритет:** 🟡 Medium — нужна для анализа и оптимизации.

---

### 7. AgentVersion
```
AgentVersion (новая)
├── id, agent_id, version (1, 2, 3...)
├── system_prompt_id, baseline_id, policy_id
├── generation_config (temperature, max_tokens, etc.)
├── capabilities (list)
├── status (draft/active/archived)
├── created_by (user_id), created_at
├── notes (what changed)

Зачем: Версионирование агентов для отката и истории изменений.
Для кого: Админы-инженеры для управления версиями.
```

**Приоритет:** 🟡 Medium — нужна для управления версиями и отката.

---

### 8. FallbackStrategy
```
FallbackStrategy (новая)
├── id, agent_id, tool_id
├── fallback_tool_id (если primary fails)
├── fallback_prompt (что сказать пользователю)
├── retry_count, retry_delay_ms
├── is_active

Зачем: Graceful degradation когда инструмент недоступен.
Для кого: Админы-инженеры для повышения надёжности.
```

**Приоритет:** 🟡 Medium — нужна для надёжности.

---

### 9. PromptExperiment
```
PromptExperiment (новая)
├── id, agent_id, prompt_id
├── control_version_id, test_version_id
├── metric (success_rate, avg_response_time, cost)
├── started_at, ended_at
├── total_runs, winner (control/test/tie)
├── control_metric_value, test_metric_value
├── notes

Зачем: A/B тестирование промптов для оптимизации.
Для кого: Админы-инженеры для научного подхода к улучшению.
```

**Приоритет:** 🟡 Medium — нужна для оптимизации промптов.

---

### 10. KnowledgeBaseVersion
```
KnowledgeBaseVersion (новая)
├── id, collection_id, version (1, 2, 3...)
├── status (draft/active/archived)
├── total_chunks, total_tokens
├── embedding_model_id
├── created_at, activated_at
├── notes (what changed)

Зачем: Версионирование коллекций для отката.
Для кого: Админы-инженеры для управления KB версиями.
```

**Приоритет:** 🟡 Medium — нужна для управления KB.

---

## 🟢 Nice-to-have (для будущего)

### 11. ExecutionFeedback
```
ExecutionFeedback (новая)
├── id, execution_id, user_id
├── rating (1-5 stars)
├── feedback_text
├── tags (helpful, incorrect, slow, etc.)
├── created_at

Зачем: Feedback loop для улучшения агентов.
Для кого: Админы-инженеры для анализа качества.
```

**Приоритет:** 🟢 Low — нужна если будут end-users.

---

### 12. DataClassification
```
DataClassification (новая)
├── id, resource_type (prompt/tool/collection)
├── resource_id
├── classification (public/internal/confidential)
├── pii_detected (boolean)
├── retention_days

Зачем: Compliance и управление данными.
Для кого: Админы для соответствия политикам.
```

**Приоритет:** 🟢 Low — нужна если есть требования compliance.

---

### 13. AgentChain
```
AgentChain (новая)
├── id, name, description
├── agents (ordered list: [agent1_id, agent2_id, ...])
├── routing_logic (sequential/conditional/parallel)
├── context_passing (what data passes between agents)
├── is_active

Зачем: Оркестрация нескольких агентов.
Для кого: Админы-инженеры для сложных workflows.
```

**Приоритет:** 🟢 Low — нужна для сложных сценариев.

---

## Итоговая таблица приоритизации

| # | Сущность | Статус | Приоритет | Причина |
|---|----------|--------|-----------|---------|
| 1 | ExecutionContext | ❌ Нет | 🔴 High | Отладка агентов |
| 2 | ExecutionAudit | ❌ Нет | 🔴 High | Audit trail + compliance |
| 3 | ModelCost | ❌ Нет | 🔴 High | Контроль затрат |
| 4 | ExecutionCost | ❌ Нет | 🔴 High | Анализ затрат |
| 5 | ToolHealthCheck | ❌ Нет | 🔴 High | Мониторинг надёжности |
| 6 | AgentMetrics | ❌ Нет | 🟡 Medium | Аналитика качества |
| 7 | AgentVersion | ❌ Нет | 🟡 Medium | Версионирование + откат |
| 8 | FallbackStrategy | ❌ Нет | 🟡 Medium | Graceful degradation |
| 9 | PromptExperiment | ❌ Нет | 🟡 Medium | A/B тестирование |
| 10 | KnowledgeBaseVersion | ❌ Нет | 🟡 Medium | Версионирование KB |
| 11 | ExecutionFeedback | ❌ Нет | 🟢 Low | Feedback loop (если end-users) |
| 12 | DataClassification | ❌ Нет | 🟢 Low | Compliance (если требуется) |
| 13 | AgentChain | ❌ Нет | 🟢 Low | Multi-agent workflows |

---

## Рекомендуемый план реализации

### Phase 1: MVP (сейчас)
- ✅ Удалить дубликаты компонентов (PermissionsEditor, CredentialSetsEditor)
- ✅ Добавить ExecutionContext, ExecutionAudit
- ✅ Добавить ModelCost, ExecutionCost
- ✅ Добавить ToolHealthCheck

**Время:** 1-2 недели

---

### Phase 2: Первый релиз (1-2 месяца)
- ✅ Добавить AgentMetrics
- ✅ Добавить AgentVersion
- ✅ Добавить FallbackStrategy
- ✅ Добавить PromptExperiment
- ✅ Добавить KnowledgeBaseVersion

**Время:** 2-3 недели

---

### Phase 3: Enterprise (3+ месяца)
- ✅ Добавить ExecutionFeedback (если будут end-users)
- ✅ Добавить DataClassification (если требуется compliance)
- ✅ Добавить AgentChain (для сложных workflows)

**Время:** 1+ месяц

---

## Примечание: Non-commercial проект

Так как это **non-commercial проект** и **агентов создают Админы-АИ инженеры**:

1. **Нет нужды в:**
   - Биллинге end-users (но нужен контроль затрат для админов)
   - Сложном RBAC для end-users (RBAC есть, но простой)
   - Feedback от end-users (но нужна аналитика для админов)

2. **Нужно сосредоточиться на:**
   - Отладке и мониторинге для админов-инженеров
   - Аналитике качества агентов
   - Версионировании для управления
   - Надёжности и graceful degradation

3. **Упрощения:**
   - Нет A/B тестирования на уровне end-users (но есть для админов)
   - Нет сложной системы квот (простые лимиты в Policy)
   - Нет многоуровневого RBAC (есть scope-based, достаточно)
