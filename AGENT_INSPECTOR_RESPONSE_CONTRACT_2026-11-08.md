# Контракт результата агента для Inspector

Дата: 08.11.2026. Это inventory существующего контракта для проектирования agent inspector; не новый runtime-протокол. Планер вне scope.

Источники: `apps/api/src/app/runtime/orchestrator_contracts.py`, `task_result_reducer.py`, `agent_executor.py`, `orchestrator.py`, `events.py`, `plan_store.py`; `docs/architecture/AGENT_RUNTIME.md`, `docs/architecture/RUNTIME_TRACE_SPEC.md`.

## Две формы terminal-данных

| Сценарий | Журнал | Значение для inspector |
| --- | --- | --- |
| Нормальный orchestrated task | `agent_end.status="completed"`; `agent_end.outcome` равен бизнес-исходу; `agent_end.result` содержит `TaskResult.model_dump(mode="json")`. Данные получены через `TaskAttemptResultReducer` из `TaskCompletionDeclaration` + runtime `verified`. | `status` означает, что запуск агента терминально завершился. `outcome` — результат задачи. Содержимое для UI брать из `result`, а не показывать весь объект envelope. |
| Попытка завершилась технической ошибкой/отменой | `agent_end.status="failed"` или `"cancelled"`, outcome/error события; `result` не обязателен. Повтор и статус логической задачи живут на уровне orchestrator. | Показать lifecycle/error summary, если они есть; partial receipts остаются отдельными подтверждёнными фактами. Нельзя маркировать как успешный общий запуск на основании LLM declaration. |
| Standalone/shadow и другие агенты без `TaskResult` | Может быть только lifecycle `agent_end`; terminal model response/answer записывается агентским journal event. | Это отдельная legacy/runtime форма. Искомый final должен быть явно привязан к выбранному `agent_execution`; промежуточный `llm_response` не является результатом. Нельзя приписывать событию чужого или соседнего агента по порядку/времени. |
| Уточнение или подтверждение пользователя | `waiting_input` / `confirmation_required`; orchestration может закрыть попытку как paused и сохранить interaction checkpoint. | Это состояние ожидания и отдельный вопрос пользователю, а не обычный terminal answer. Использовать каноническую pause/interactions проекцию. |

Для обычного orchestrated агента успешное исполнение протокола может завершиться `agent_end.status="completed"` при `outcome="needs_dependency"` или `"unfulfillable"`. Это не ошибка самого процесса, но и не удовлетворённая задача. В модели допустимы три разных статуса: lifecycle выбранной попытки, бизнес-outcome результата и lifecycle логической задачи в `PlanStore`. Они не взаимозаменяемы.

Минимальная операторская локализация outcome: `completed` → «Поручение выполнено»; `needs_dependency` → «Нужно продолжить»; `unfulfillable` → «Не удалось выполнить»; lifecycle `failed` → «Ошибка выполнения»; `cancelled` → «Выполнение отменено»; `paused/waiting_input` → «Ожидает вашего ответа». В основном agent inspector показывать один общий badge lifecycle и одну outcome фразу в Result; не печатать одинаковую строку «Готово» в шапке, задаче и результате.

## Поля TaskCompletionDeclaration и TaskResult

| Сущность | Фактическое поле/тип | Кто задаёт | Правило показа |
| --- | --- | --- | --- |
| Completion | `completion`: enum `fulfilled`, `needs`, `unfulfillable`, `interaction` | Agent declaration; reducer переносит в `TaskResult.completion` | Короткий итог/claim агента. Для interaction основным является отдельная пауза/вопрос, reducer обычно не получает этот claim. Не путать с lifecycle. |
| Interaction | `interaction` contains `question` (1–4000 chars), `response_type=text\|boolean` (default text) | Agent declaration; runtime validates requester/policy and converts it to paused interaction state | Не часть обычного TaskResult viewer. Показывать активный вопрос в отдельном waiting/interaction view. `RuntimeInteraction.public()` включает id, question, `response_schema`, requester; скрывает checkpoint и operation. Не показывать private checkpoint или operation JSON. |
| Текст | `answer?: str \| null`; `TaskResult.description: str` (обязательное), создаётся через `declaration.report` = `answer or completion` | Agent и reducer | Отдельный текстовый блок, только когда содержателен. `description` обычно совпадает с answer или строкой enum, поэтому не показывать оба; legacy adapter может превратить report в answer. |
| Структурированные данные | `structured_response: Any = None` | Agent declaration; reducer переносит без схемной нормализации | Может быть любым JSON, включая `false`, `0`, `null`, `{}`, `[]`. Не проверяется на «правильность» общей схемой. Сохранять представленные значения; отличать отсутствие от явного `null` по legacy `outputs`/presence metadata. |
| Legacy values | declaration `outputs: Dict[str, OutputSlot]` (не входит в provider JSON schema, исключено из сериализации declaration); reducer раскладывает `kind=value` в structured data | Исторический declaration/adaptation | Value-slots сохраняются. `evidence`/`artifact` slots — это ссылки, а не содержимое данных; не выводить IDs как ответ. Adapter может сконструировать пустой structured response, если outputs есть, но value-slots нет — это важно учитывать при нормализации. |
| Needs | `needs: list[DiscoveredNeed]`; поля `ref`, `key`, `kind=data\|artifact\|decision`, `description`, `schema`, `required`, `context` | Agent declaration; reducer переносит | Отдельный список «Чтобы продолжить, нужно…» только при непустом списке. Человеку показывать описание, kind и required; ref/key/schema/context оставить для связей/RAW, пока нет отдельного typed UI. Жизненный статус need устанавливает runtime, агент его не задаёт. |
| Attachments/files | `TaskResult.attachments: list[dict]`, извлекаются из runtime verified artifacts; удалённые исключаются, artifact id обязателен, dedupe по id. Общая safe attachment reference shape в `runtime.contracts.AttachmentRef`: `artifact_id`, `file_name`, optional `file_ext`, `content_type`, `size_bytes`, `status`, `description`, `origin`, `data_indexes`. Но TaskResult attachment dict может быть artifact passport шире этого ref. | Runtime operations / artifact registry, не произвольный ответ модели | Отдельные file карточки по безопасным file name/description, типу/размеру/разрешённой download route. IDs и storage refs не показывать как описание. Сам факт упоминания файла в answer не является зарегистрированным файлом. Поля `origin`/`data_indexes` — metadata, не отображать целиком. |
| Sources | `TaskResult.sources: list[dict]`, копия `verified.sources`, полученных из observation/retrieval/tool events | Runtime и операции-источники | Отдельные citations/materials только если есть распознаваемые display label/title/source URL по существующему безопасному контракту. Пустой список скрыть. Источники цитирования — не список всех вызванных инструментов. |
| Runtime receipts | `verified` включает `status=observed`, `fresh_retrieval`, `receipts`, `evidence`, `artifacts`, `sources`; receipt содержит success, result_ref/call_id, operation, canonical_operation, fingerprint, preview, retrieval, result_id, completeness facts и иногда result.analyze coverage facts | Runtime tool ledger; только записи successful calls попадают в verified receipts | Не копировать сырой объект в основной результат. Могут поддержать отдельный компактный список «Выполненные действия» с именем операции, исходом и bounded completeness; fingerprint/hash и IDs оставить RAW. Receipt не доказывает, что конкретный вывод следует из ответа инструмента. |
| Diagnostics | `TaskResult.diagnostics: list[dict]`, в основном предупреждения о несовпадении advisory schemas | Reducer/schema diagnostics | Отдельный блок «Замечания к формату» только при непустом списке; ограниченные локализованные code/message, без общего раскрытия объектных ключей. Это не ошибка выполнения и само по себе не меняет outcome. |
| Output state | `output_states: Dict[key, {status, fulfillment, ...}]`; statuses `available`, `missing`, `fulfilled`; required output/artifact matching определяется request contract | Reducer проверяет ожидаемые slots/файлы | Показывать только когда task contract определяет ожидаемые outputs. Названия через output descriptions; «готово/не предоставлено». Это контракт доставки, не автоматическая истинность или полнота arbitrary data. |
| Limitation | Internal `TaskCompletionDeclaration.limitation?: {code, message, action}`; action: `reconfigure_credentials`, `grant_access`, `provide_input`, `retry_later`, `none` | Поле исключено из provider JSON Schema наряду с legacy outputs/coverage; может быть принято парсером в compatibility declaration, либо runtime reducer выставляет limitation (например `required_artifact_missing`). Не считать field гарантированным v2 ответом агента. | Человекоориентированный текст + действие, если безопасно и действие определено. Код — только в RAW/diagnostic section. Не дублировать то же предложение из `needs`/safe error. |
| Reason | `reason_code?: str`; reducer выставляет, например, `required_artifact_missing` при заявленном completed без обязательного artifact | Runtime reducer | Safe label через registry, только если есть известное соответствие. Не отображать код напрямую. |
| Outcome | `TaskResult.outcome`: `completed`, `needs_dependency`, `unfulfillable`; reducer выводит из completion, затем может превратить completed в unfulfillable при отсутствующем обязательном файле | Runtime reducer | Отдельное краткое значение «Выполнено», «Нужно продолжить», «Не удалось выполнить» внутри результата, согласованное с lifecycle header. Это бизнес-исход. |
| Verified selections/coverage | `evidence_selections`, `artifact_selections` typed runtime records; declaration coverage type существует, но поле исключено из `TaskResult` и не участвует в текущем reducer | Runtime compatibility/internal model | Не показывать как универсальную полноту. Для подтверждения coverage требуются реальные валидированные refs/result IDs, а не declaration claim. |
| Diagnostics internals | `protocol_version`, `verified`, fingerprints, `output_states` reason/errors/normalized_from, schema paths | Runtime | RAW или dedicated typed detail only where meaningful. Не показывать в общем JSON tree. |

### Политика значения / отсутствия

- Completion enum обязателен в declaration; `answer` и `structured_response` optional/null-able.
- В Pydantic declaration `structured_response` по умолчанию `None`. `model_fields_set` различает field omitted и explicit null на этапе declaration. Reducer переносит `data` в `TaskResult.structured_response` и делает `outputs`: dict если data dict, иначе `{structured_response: data}`, если поле присутствовало. Если поле пропущено, `outputs` остаётся `{}`. Поэтому эта пара сохраняет presence information для `null`, даже если serialized `structured_response` сам выглядит одинаково.
- `false`, `0`, `null`, пустые object/list валидны и не должны удаляться frontend-проекцией через truthiness. Для объекта и списка пустая структура означает настоящий пустой ответ, если поле присутствовало.
- Модель `TaskResult` сериализует defaults: lists/maps будут `[]`/`{}` даже когда фактического содержимого нет. Viewers должны проверять содержимое, а не только наличие ключа.
- `answer` может быть absent, null или empty string. Legacy `report` копируется в `answer`, только если answer отсутствовал. `description` строится из truthy answer иначе из enum; не отображать `answer`, `description`, `summary` и `structured_response` как четыре равноправных блока.
- `attachments`, `sources`, `needs`, `diagnostics`, selections empty by default: соответствующие блоки скрывать, если длина 0. `outputs`, `output_states`, `verified` пусты по умолчанию: скрывать, если после typed extraction не осталось содержимого.
- Отсутствующий runtime terminal result означает «результат не записан», а не пустой объект; explicit empty value означает непустой факт результата.

## Ошибка и частичный результат

Ошибки исполнения могут находиться в `error` event с `safe_message`/user-safe fields, а task attempt details — в orchestrator event/plan state. Orchestrator failure не обязана иметь `TaskResult`, поэтому UI собирает сообщение только из специально проецируемого safe error; raw exception/provider details не должны попадать в semantic result.

Если runtime записал tool receipts до более поздней ошибки, эти действия могли иметь внешние side effects. Их можно показать как «Выполненные действия» и отдельно показать итоговую неудачу. Они не делают ответ completed. Частичные outputs, если они реально записаны, остаются доступными; ошибки не должны скрывать подтверждённые файлы/данные.

`AgentExecutionCompletion.UNFULFILLABLE` переводится в `TaskOutcome.UNFULFILLABLE` при успешном завершении agent process. Это пользовательский/domain outcome, не technical error. `NEEDS` переводится в `needs_dependency`. `INTERACTION` проходит через отдельный WAITING_INPUT/pause путь и обычно не доходит до `TaskAttemptResultReducer`.

## Файлы и источники: валидность ссылки

- Runtime artifact reference должен возникнуть в verified artifact registry/операции, не быть удалённым, и быть доступным выбранному пользователю в рамках действующего file authorization flow. Для display не требуются artifact UUID или private object storage URI.
- Artifact links, созданные tool result, дополнительно проходят `artifact_visibility`/available ids; не доверять URL из structured_response. Перед отображением ссылки нужно установить, что существующая frontend/API file route принимает registry artifact id и проверяет доступ.
- Source entry приходит как dict от runtime/tool result; он не является единым typed `Source` contract. Не выводить arbitrary url или ключи объекта в кликабельный элемент. До нормализации разрешены текстовые label/title/name и известные безопасные reference fields, иначе source показывается простым текстом без ссылки либо скрывается.
- Наличие `url`/`download_url` внутри source/artifact dict не делает его доверенным. URL для перехода строить из проверенного artifact id через существующую API file route; внешние citation links требуют схемной allowlist/нормализации и корректного HTML escaping.
- `verified.receipts` содержат tool-result refs, не user-facing citations. `sources=[]` совместим с непустыми receipts: source data и execution provenance — разные списки.
- `evidence` в verified keyed by call ID и fingerprint; это provenance metadata, не доказательство semantic entailment.

## Legacy adapter и lifecycle приоритет

`TaskCompletionDeclaration.adapt_legacy`:

1. переносит `report` в `answer`, только если `answer` отсутствует;
2. если `structured_response` отсутствует и есть dict `outputs`, строит structured data только из value slots;
3. normalizes absent `limitation` в null и absent `needs`/`coverage`/`outputs` в default collections;
4. schema extra-forbid сохраняется; legacy поля `outputs`, `coverage`, `limitation` объявлены в модели, хотя отсутствуют в provider schema.

Runtime lifecycle authoritative over model claim. Для orchestrated agent `status=completed` означает process emitted/validated terminal declaration; `outcome` выбирается по claim и may be transformed by required-file gate. `agent_end.status=failed/cancelled/paused` и authoritative error/pause не должны пересекаться успешным `completion`/`answer`. У `needs_dependency` task `agent_end.status` всё ещё completed, status сущности может проектироваться из outcome — UI обязан понимать, к чему относится label.

## Текущая frontend-нормализация Sandbox/admin

Общая `traceProjection` предпочитает `agent_end.result` (`TaskResult`), затем
обрабатывает legacy final, связанный с точным `agent_execution`, и только затем
использует поддерживаемые curated lifecycle-поля. Legacy JSON распознаётся как
completion declaration только при валидном `completion` и строгом наборе
разрешённых полей/типов, соответствующем extra-forbid declaration contract.
JSON без completion или с дополнительными domain keys (например,
`{answer: 42, device_id: ...}`) остаётся произвольными structured data; даже
валидный completion вместе с дополнительным domain key не принимается за
declaration. Новый runtime protocol или параллельная schema не вводились.

Для ordinary agent projection нормализует статус, согласуя result, info и
entity: declaration `fulfilled` проецируется как `completed`, `needs` как
`waiting`, а `unfulfillable` остаётся неуспешным бизнес-исходом. Авторитетный
lifecycle `failed`, `cancelled`, `paused` или `waiting` имеет приоритет над
claim. Текущая ветка также отображает completion `interaction` как `waiting`;
это значение следует отличать от отдельного runtime interaction/pause
lifecycle, если он записан. Успешное завершение coroutine само по себе не
означает успешный outcome задачи.

У legacy `final` источники могут находиться в sidecar `payload.sources` рядом
с `payload.content`; projection переносит их в citation DTO и не требует
встраивать в declaration content. Final присваивается только при совпадении
owner links с выбранным execution; соседние final events не используются.

## Предложенная группировка отдельных viewer компонентов

Показывать component только если typed projection вернул содержательные данные:

1. **Ответ** — answer/description text; не показывать enum token как обычное предложение без локализованного outcome.
2. **Структурированные данные** — arbitrary JSON viewer с typed text/scalar/list/table/object presenters, сохраняющий false/0/null/empty object/list.
3. **Файлы** — доступные runtime attachments, карточки/ссылки.
4. **Источники** — распознанные citations/materials, безопасные ссылки только при валидированном route.
5. **Что нужно для продолжения** — non-empty needs и pause/interaction question отдельным lifecycle path.
6. **Ограничение** — limitation/reason mapped to safe label/action, без повторения error/needs сообщения.
7. **Проверенные действия** — bounded linked receipts/tool calls с текстом операции и результатом; не показывать fingerprints.
8. **Замечания** — non-empty schema diagnostics/output states; локализованные advisory/missing file states.

Порядок: текстовый ответ → structured data → файлы → источники → needs/limitation → проверенные действия → замечания. В ~320px это вертикальные compact sections; блоки пустых списков не рендерятся. Technical receipt envelope остаётся в RAW. Shared typed model используется Sandbox и admin, Viewers не читают journal events самостоятельно.
