# PLAN: Agent Needs Contract + Plan/Task Journal

> Статус: к реализации через Cursor.
> Цель: ввести единый расширенный контракт ответа агента (`status` + `needs[]`),
> сущность «план + журнал задач», метаданные способностей агента для роутинга
> потребностей, и счётчик «пауз» вместо ретраев. Планер остаётся единственным,
> кто финализирует и роутит. Иерархия «менеджер/исполнитель» НЕ вводится как
> жёсткий класс — «менеджер» становится частным случаем агента, чей ответ почти
> всегда `needs_input` + план.

---

## 1. Контекст и проблема

Сегодня:
- Результат суб-агента — бесформенный dict (`apps/api/src/app/runtime/agent_executor.py`, блок `state.add_agent_result(...)`). Менеджер и исполнитель неразличимы.
- Планер видит только `last_iteration_result` (резюме ПОСЛЕДНЕЙ итерации), а не накопленный план — `PlannerInputBuilder.build` (`apps/api/src/app/runtime/input_builders.py`).
- Нет сущности «план + журнал задач»: где, кто, что решал, какой `need` закрыт, каким значением.
- `missing_inputs` и `PlannerIterationResult.outcome == "needs_input"` уже существуют, но не образуют замкнутый цикл «агент заявил потребность → планер закрыл → дозвал агента».

Цель — замкнуть этот цикл и сделать его наблюдаемым.

## 2. Согласованная модель (инварианты)

1. **Финализирует только планер.** `status` в ответе агента — сигнал, а не команда. Агент не может ни заставить финализировать, ни запретить.
2. **Агент всегда терминальный.** Mid-run resume отсутствует. «Пауза» — это вид завершения (`completion_kind = "paused_need"`). Повторный вызов = НОВЫЙ вызов с инъекцией контекста (что сделал, что просил, что найдено — доведи задачу).
3. **Агент декларирует потребность в данных, не просит агента.** `need` = типизированная заявка («нужен `lun_uuid` чтобы презентовать на вирте при создании ВМ»). Кого дёрнуть — решает планер.
4. **Лимит — число пауз на (агент, задача), а не ретраи.** Исчерпан → планер помечает пункт `deferred` и продолжает остальной план.
5. **Тип агента (способности) и тип ответа — разные оси.** Тип ответа управляет циклом; способности агента управляют роутингом потребностей.

## 3. Изменения контракта

### 3.1 Ответ агента (AgentResult) — расширение

Добавить в payload `state.add_agent_result(...)` (executor строит его в `agent_executor.py`):

```text
status: "complete" | "needs_input" | "failed"   # advisory сигнал планеру
completion_kind: "answered" | "paused_need" | "error"
needs: [
  {
    ref: str            # локальный id потребности ("need-lun-uuid")
    kind: str           # тип: "data" | "artifact" | "decision"
    key: str            # машинный ключ для роутинга ("lun_uuid")
    description: str     # человекочитаемо, зачем
    context?: dict       # доп. контекст (например {"vm_purpose": "..."} )
    resolved_value?: any # заполняется планером при дозвоне
    resolved_by?: str    # slug агента, закрывшего потребность
  }
]
# существующие поля сохраняются: summary, facts, attachments, success,
# missing_inputs, error, error_code, retryable, phase_id, iteration
```

Правила:
- `status == "needs_input"` ⇒ есть непустой `needs[]`.
- `needs[].key` ОБЯЗАТЕЛЕН и машинно-роутируемый (не свободный текст). Свободный текст идёт в `description`.
- `missing_inputs` остаётся как legacy-зеркало `needs[].key` (для обратной совместимости планерных проверок).

### 3.2 Метаданные способностей агента (для роутинга)

`apps/api/src/app/models/agent.py`:
- Переиспользовать существующий `tags: ARRAY(String)` для «направления» (network/storage/virt) — без миграции.
- Добавить структурное поле способностей (рекомендуется, 1 миграция):
  ```text
  provides_keys: ARRAY(String)  # какие need.key этот агент умеет закрывать ("lun_uuid", ...)
  ```
  Планер по `needs[].key` находит агента, у которого `key in provides_keys`.
- НЕ вводим жёсткий enum `kind=manager|executor`. «Менеджер» = агент, у которого `provides_keys` пуст/мал, а ответ — план + needs.

> Открытый вопрос для обсуждения при реализации (НЕ блокирует MVP):
> как именно вести `provides_keys` при росте числа агентов — вручную в карточке
> агента или авто-выводить из биндингов операций. На старте — вручную.

### 3.3 Сущность: План + Журнал задач

Новое поле в `RuntimeTurnState` (`apps/api/src/app/runtime/turn_state.py`):

```text
task_journal: List[TaskJournalEntry]

TaskJournalEntry:
  task_id: str               # стабильный id пункта плана
  title: str                 # что делаем
  assigned_agent: str|None    # кто решал/должен решать
  status: "pending" | "in_progress" | "paused_need" | "resolved" | "deferred" | "failed"
  needs: [ {ref, key, description, resolved_value, resolved_by, status} ]
  attempts: int               # сколько раз дозывали
  max_pauses: int             # лимит пауз для этой задачи
  summary: str                # что сделано (для финального саммари)
  origin_agent: str|None      # кто породил пункт (например менеджер-план)
  depends_on: [str]           # task_id зависимостей
```

Назначение:
- Планер видит ВЕСЬ план, а не только последнюю итерацию.
- По журналу строится финальное саммари и принимается решение о финализации.
- Гарантирует, что мы «не перепутаем агента» — каждая задача знает своего исполнителя и свою потребность.

Методы на `RuntimeTurnState`: `add_task`, `update_task`, `record_need_resolution`, `pending_tasks`, `can_finalize` (расширить: финал запрещён, пока есть `pending`/`in_progress`/`paused_need` без `deferred`).

## 4. Поток выполнения (целевой)

1. Планер `CALL_AGENT` на агента A по задаче `task_id`.
2. A завершается:
   - `status=complete` → журнал: задача `resolved`, `summary` записан.
   - `status=needs_input` + `needs[]` → журнал: задача `paused_need`, needs зафиксированы.
3. Планер на следующей итерации видит `paused_need`:
   - для каждого `need.key` ищет агента-резолвера (`provides_keys`),
   - `CALL_AGENT` на резолвера → получает значение → `record_need_resolution`.
4. Когда все needs задачи закрыты → планер дозванивает A:
   - `agent_input` обогащается: `{prior_summary, resolved_needs:[{key,value}], instruction:"доведи задачу"}`,
   - `attempts += 1`.
5. Если `attempts > max_pauses` и задача всё ещё `paused_need` → `deferred` (планер идёт дальше).
6. Когда `can_finalize()` истинно → `FINAL` → синтезер собирает из `task_journal` + attachments + sources.

## 5. Изменения по файлам (карта)

- `apps/api/src/app/models/agent.py` — добавить `provides_keys` (+ миграция). `tags` уже есть.
- `apps/api/src/app/runtime/turn_state.py` — `TaskJournalEntry`, `task_journal`, методы, расширить `can_finalize()`.
- `apps/api/src/app/runtime/agent_executor.py` — парсить `status`/`needs` из финала суб-агента; писать их в AgentResult; обогащать `agent_input` при дозвоне (инъекция `resolved_needs`/`prior_summary`).
- `apps/api/src/app/runtime/planner/iteration_policy.py` — `build_iteration_result` пробрасывает `status`/`needs`; helper `resolve_pending_needs`.
- `apps/api/src/app/runtime/stages/planner_call_agent_dispatcher.py` — обновлять `task_journal`; роутинг потребностей; учёт `attempts`/`max_pauses`.
- `apps/api/src/app/runtime/input_builders.py` — `PlannerInputBuilder` отдаёт планеру `task_journal` (план целиком) + `open_needs`. `SynthesizerInputBuilder` строит саммари из `task_journal`.
- `apps/api/src/app/runtime/planner/validator.py` — финал блокируется, пока есть незакрытые/недефернутые задачи (через `can_finalize()`).
- `apps/api/src/app/runtime/contracts.py` — при необходимости типы `NeedSpec`/`AgentAnswerStatus`.
- Промпт PLANNER (`system_llm_roles`, роль PLANNER) — правило: needs закрывать роутингом, не финализировать при открытых needs.
- Промпт агентов (соглашение вывода) — как агент декларирует `status`/`needs` (в MVP — через структурированный финал/парсинг).

## 6. Скоуп

**В скоупе (MVP):**
- Контракт `status` + `needs[]` (структурный, `key` обязателен).
- `task_journal` в state + методы + расширение `can_finalize`.
- Роутинг потребностей планером через `provides_keys`.
- Дозвон агента с инъекцией контекста.
- Счётчик пауз на (агент, задача) + `deferred`.
- Синтез финала из журнала.

**Вне скоупа (отдельные итерации):**
- «Думающий модуль» (пред-планер reformulation + ре-планер для дефер-пунктов) — спроектировать позже.
- Авто-вывод `provides_keys` из биндингов.
- Персистентный кросс-сессионный профиль пользователя (частые темы → факты). Записано в `TODO.md`.
- Жёсткий enum роли агента `manager|executor`.
- Mid-run resume агента (намеренно НЕ делаем).

## 7. Критерии приёмки

1. Агент может вернуть `status=needs_input` со структурированными `needs[]`; это фиксируется в `task_journal` как `paused_need`, НЕ как финал.
2. Планер по `need.key` находит агента-резолвера через `provides_keys` и закрывает потребность за один шаг (без перебора наугад).
3. После закрытия всех needs задачи планер дозванивает исходного агента, и в его `agent_input` присутствуют `prior_summary` и `resolved_needs[{key,value}]`.
4. Дозвон ограничен `max_pauses`: при превышении задача переходит в `deferred`, а ран не зависает.
5. `FINAL` невозможен, пока есть задачи в `pending|in_progress|paused_need` без перевода в `deferred` (проверяется `can_finalize()` и `validate_next_step`).
6. Финальное саммари синтезера собирается из `task_journal` (видно: какой агент, какая задача, какой статус), а аттачи по-прежнему доходят до синтезера, минуя планер.
7. Планер по-прежнему НЕ получает attachments/сырых данных в payload (проверить `PlannerInputBuilder`).
8. Нет регрессий: существующие сценарии (RAG doc_search, SQL, table aggregate) проходят; `outcome="needs_input"` и `missing_inputs` сохраняют обратную совместимость.
9. Защита от циклов: `need.key`, который не закрывается за N дозвонов, не вызывает бесконечный цикл (учитывается `recent_action_signatures` + `attempts`).

## 8. Definition of Done

- Контракт и `task_journal` реализованы; миграция `provides_keys` применяется без потери данных (`server_default`/nullable).
- Unit-тесты: (а) needs-цикл (заявка→роутинг→дозвон→resolve), (б) лимит пауз→deferred, (в) блок финализации при открытых задачах, (г) обратная совместимость `missing_inputs`.
- Интеграционный сценарий: «создай ВМ, нужен LUN» — исполнитель виртуализации заявляет `need.key=lun_uuid` → планер роутит на агента СХД → дозвон виртуализации с `lun_uuid` → финал.
- В trace/инспекторе видно: задача, назначенный агент, needs и их резолюции, статус.
- Документация в `docs/architecture/AGENT_RUNTIME.md` дополнена разделом «Agent Needs Contract & Task Journal».
- Промпты PLANNER и агентов обновлены и засеяны.

## 9. Риски и митигейшн

- **Свободный текст в needs ломает роутинг** → `key` обязателен и машинный; `description` отдельно.
- **Циклы дозвонов / взрыв стоимости** → `max_pauses` на задачу + `recent_action_signatures` + бюджеты.
- **Планер финализирует на плане** → `can_finalize()` + `validate_next_step` + правило в промпте.
- **Повторный вызов теряет контекст** → контекст берётся из `task_journal` (а не из состояния агента), инъекция в `agent_input`.
- **Рост числа агентов и `provides_keys` вручную** → на старте вручную; авто-вывод вынесен из скоупа.
