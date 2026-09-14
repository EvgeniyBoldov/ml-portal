# TODO

## Platform data integrity

### Semantic-memory lifecycle

- Не вводить новый lifecycle для legacy project facts. Дальнейшее развитие
  делать только через source-backed `MemoryItem` / `MemoryClaim` и evidence
  документов.

### Осталось до production-ready Memory

- Добавить PostgreSQL integration-тесты для повторной extraction того же
  checksum, удаления исчезнувших кандидатов, rollback, конфликтующих claims и
  tenant ACL для content, aliases, relations и evidence.
- Проверить миграции `0135–0136` на копии shared-схемы и выполнить controlled
  re-extraction всех включённых документов.
- Добавить эксплуатационные метрики: extraction accepted/rejected,
  active/uncertain/stale, recall hit/miss, RAG/tool/clarification decisions,
  ACL-filtered candidates и ошибки re-extraction.
- Удалить из актуальной runtime-документации упоминания старых
  `memory.lookup/read/mark` и facts-based Project Memory.
- Проверить и при необходимости завершить разделение `summary_preview`,
  bounded trace/progress summary и пользовательского ответа.

## Semantic Memory UI

UI — отдельный этап после backend-контуров. Он не должен создавать или
редактировать память как произвольный key/value-текст: все изменения проходят
через документ, evidence и переизвлечение.

### 1. Настройка документа при загрузке

- В форме загрузки документа добавить выбор участия в Semantic Memory:
  «наследовать настройку коллекции», «включить для этого документа»,
  «исключить для этого документа».
- Добавить необязательный выбор связанных проектов из общего корпоративного
  каталога. Отсутствие проекта означает, что документ может дать
  корпоративную, а не проектную память.
- Не превращать tenant в фильтр доступных проектов: tenant определяет доступ
  к документу, а не состав project catalogue.

Критерии готовности:

- выбранный режим сохраняется как `memory.policy` (`collection`/`explicit`) и
  `memory.enabled` в source metadata;
- переключение `memory_enabled` у коллекции затрагивает только документы в
  режиме `collection`;
- выбранные project keys передаются в extraction и видны в итоговой
  применимости memory item;
- пользователь видит, какая политика реально действует для каждого документа.

Осталось реализовать:

- Подключить выбор проектов из общего корпоративного каталога; tenant не
  должен ограничивать этот список.
- Показывать effective memory policy, project keys и memory extraction status
  в списке документов.
- Добавить UI-состояния загрузки, ошибки extraction и повторного запуска.

### 2. Виртуальные коллекции «Глоссарий» и «Project Memory»

- Глоссарий и Project Memory остаются read-only виртуальными коллекциями, а
  не записями в таблице `collections`.
- В карточке знания показывать тип, актуальное состояние, применимость,
  свежесть, число источников и evidence references, доступные текущему
  tenant.
- Для procedure рендерить структурированные цель, предусловия, шаги,
  проверки, rollback и исключения, а не сырой JSON одной строкой.

Критерии готовности:

- пользователь не может изменить content memory item вручную из этих views;
- локальный tenant не видит content, evidence или счётчики чужого claim;
- glossary отображает aliases, тип и связанный проект/сущность;
- project view корректно показывает `active`, `uncertain` и `stale` на основе
  доступных claims.

Осталось реализовать:

- Завершить отображение freshness, source count и evidence references.
- Отображать relationships, descriptions и decisions отдельными типами, а не
  универсальным значением.
- Синхронизировать frontend API types со всеми полями entity/project
  projection.

### 3. Административная проверка доказательств и конфликтов

- Сделать UI над существующим admin semantic-memory API: поиск items,
  просмотр claims, документов, секций, freshness и конфликтов.
- Добавить явные действия «открыть исходный документ» и «переизвлечь
  документ»; не добавлять inline-редактирование semantic content.

Критерии готовности:

- конфликтующие claims показаны рядом с их источниками и без смешивания
  tenant-видимостей;
- оператор может понять, почему item `uncertain` или `stale`;
- повторное извлечение запускается по документу и после завершения обновляет
  отображаемое состояние;
- UI не выдаёт memory за актуальное runtime-наблюдение внешней системы.

Осталось реализовать:

- Сделать страницу поиска Semantic Memory с фильтрами scope/type/state/project.
- Сделать detail view item с claims, источниками, sections, relations,
  evaluations и причинами `uncertain`/`stale`.
- Добавить открытие исходного документа и polling состояния re-extraction.

### 4. Качество UI

- Добавить frontend unit/component tests для upload policy, virtual
  collections, structured procedure и admin detail view.
- Проверить accessibility: клавиатурная навигация, focus states, screen-reader
  labels, читаемые статусы и ошибки.
- Проверить responsive layout для таблиц, карточек knowledge и procedure view.
- Запустить frontend build после установки зависимостей и исправить все
  TypeScript/lint ошибки.

## Runtime result representation

- Пересмотреть `summary_preview` и текущий лимит 800 символов: разделить
  внутренний результат задачи, bounded trace/progress summary и пользовательский
  ответ; сохранить лимит только там, где он служит конкретному bounded contract.

## Runtime terminology

- `iteration` — каноническая единица planner decision и её execution wave.
  Не вводить `PlanRevision` или patch как альтернативную модель runtime/UI.
- `planner_iteration` остаётся именем trace invocation; это не task и не
  отдельная версия плана.
