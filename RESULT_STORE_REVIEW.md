# Ревью: ответ API → Result Store → последующая работа с результатом

Дата: 24 октября 2026. Проверено текущее рабочее дерево поверх commit `0655a842ddba09cef11d11731460a510f6329037`.

В рабочем дереве уже были изменения, в том числе в runtime, checkpoint и ledger. Отчёт относится к фактически прочитанному коду с этими изменениями, а не только к указанному commit. В follow-up по запросу внесены исправления F01–F14 и R01–R05. Все probes и результаты ниже описывают исходное состояние до этих исправлений; они сохранены как воспроизводимая база ревью.

## Результат

Найдено **14 дефектов: 2 × P1, 12 × P2**. Часть касается непосредственного сохранения API-ответа, часть — общих механизмов Result Store, которыми затем пользуются API-наборы. У каждого дефекта ниже указаны условия проявления и способ проверки. Дополнительные риски вынесены отдельно и не включены в это количество.

**До исправлений прошли 80 существующих профильных тестов.** Дополнительные проверки выявили сценарии, которых эти тесты не покрывали. В follow-up тесты не запускались: выполнены только компиляция затронутых Python-модулей и `git diff --check`. Проверки PostgreSQL выполнялись во временных схемах `test_workspace_<uuid>`, с миграциями и удалением схем через существующую тестовую fixture. Реальные внешние API в дополнительных сценариях не вызывались: использованы синтетические ответы и mock executor. Отказ БД проверен инъекцией исключения.

| ID | Приоритет | Дефект | Подтверждение |
| --- | --- | --- | --- |
| F01 | P1 | Повторное сохранение исходного вызова уничтожает дозагруженные записи и оставляет несовместимый журнал страниц | PostgreSQL |
| F02 | P1 | Большой контекст задачи заменяется ссылкой, которую агент без инструментов не может прочитать | Компонентная проверка с PostgreSQL |
| F03 | P2 | Внутренние запросы `result.load` обходят лимит и журнал вызовов инструментов | Runtime + PostgreSQL + mock источника |
| F04 | P2 | Частичный ответ локального `collection.search` получает `source_complete=true` | Реальный формат handler + проверка функции |
| F05 | P2 | Повторное использование возвращает новую ревизию со старой схемой | Runtime + PostgreSQL |
| F06 | P2 | Произвольный `meta` пробивает бюджет ответа модели | PostgreSQL + formatter |
| F07 | P2 | SQL-результаты теряют точность дробных `numeric` | PostgreSQL |
| F08 | P2 | Коллизия скалярной колонки `value` с полем объекта теряет данные в проекциях | PostgreSQL |
| F09 | P2 | Redactor меняет ключи исходного JSON и молча склеивает поля | Компонентная проверка |
| F10 | P2 | Циклическая continuation оставляет набор в состоянии без прогресса | PostgreSQL + анализ load loop |
| F11 | P2 | Ошибка БД при workspace-read выходит исключением из tool facade | Инъекция `OperationalError` |
| F12 | P2 | Широкая схема отключает повторное использование существующего набора | Компонентная проверка ledger |
| F13 | P2 | Unicode-поиск `result.find` не находит точное исходное слово | PostgreSQL |
| F14 | P2 | После pause/resume direct-результат listing/search может переиспользоваться как пустая квитанция | Компонентная проверка checkpoint + reuse |

## Follow-up: исправления применены

- **F01–F05:** replay исходного вызова сохраняет дозагруженные данные и журнал; workspace-only агенты могут читать сохранённые результаты; внутренние source page calls учитываются в общем бюджете и ledger; локальный `collection.search` сохраняет пагинационные метаданные; при reuse схема берётся из свежего descriptor.
- **F06–F09:** ограничены и санитизированы metadata для model context; PostgreSQL JSON numeric разбирается как `Decimal` и сериализуется без float-roundtrip; конфликт корневого scalar с колонкой `value` завершается явной ошибкой; redaction больше не переписывает ключи JSON.
- **F10–F14:** циклические continuation прекращают загрузку с явной ошибкой; ошибки БД возвращаются в границе инструмента; аргументы query ограничены; кешированный ledger entry с `stored_result_id` разрешает reuse; direct collection listing/search очищается при checkpoint resume.
- **R01–R05:** SQL rows/query/parameters проходят redaction; SQL rows читаются streaming с ограничениями строк и байтов; legacy анализ принимает root array через `$`; полнота вложенных Jira records вычисляется рекурсивно; find/aggregate pagination фиксирует входные revisions и использует стабильную сортировку.

В этом follow-up не запускались тесты и PostgreSQL probes. Компиляция перечисленных затронутых модулей и `git diff --check` прошли.

P1 — потеря доступных данных или невозможность выполнить штатный сценарий при указанном условии. P2 — нарушение контракта, неверный результат, обход ограничений либо отказ обработки в определённых сценариях. Приоритеты учитывают последствия, а не только простоту воспроизведения.

## Проверенный путь данных

1. `DirectOperationExecutor` получает ответ local/MCP handler и преобразует его в `ToolResult`.
2. `OperationExecutionFacade` разрешает операцию, нормализует/валидирует аргументы, проверяет повторное использование, запускает executor. Native workspace tools уходят в отдельную ветку.
3. `AgentToolRuntime._execute_single_operation_call` применяет redactor. MCP-ответы проходят `ResultWorkspace.save_source` и явный адаптер `ResultPage`. Остальные stored-ответы сохраняются через `ToolResultStore.save`.
4. В dedicated results DB сохраняются parent payload, записи, схема, sample, метаданные и исходные страницы. Сохраняется стабильный `result_id` по root run и исходному call ID.
5. Модель получает inline-данные или descriptor. `result.read` читает сохранённые записи, `result.load` вызывает источник и дописывает страницы, SQL/wrappers сохраняют производный набор.
6. Ledger хранит квитанции и ссылки; datastore показывает метаданные набора нужным ролям. Большой task context также переносится в Result Store. Checkpoint восстанавливает сообщения и ledger после взаимодействия с пользователем.

Основные контракты сверялись с `docs/architecture/RUNTIME_TOOL_RESULTS.md`, `docs/PLATFORM_OVERVIEW.md`, `docs/architecture/FLOWS.md`, backend rules и кодом вызовов. Frontend-store не является хранилищем этих ResultSet и в этот отчёт не входит.

## Подтверждённые дефекты

### F01 · P1 · Повторное save разрушает набор после append

**Код:** [tool_result_store.py](apps/api/src/app/services/tool_result_store.py), строки 92–107, 136–158; [result_workspace.py](apps/api/src/app/services/result_workspace.py), строки 171–174.

`save` при конфликте `(run_id, call_id)` заменяет payload и dataset metadata, удаляет record rows и вставляет исходные записи заново. При этом ранее сохранённые source pages остаются; начальная страница вставляется через `ON CONFLICT DO NOTHING`.

**Воспроизведение:** сохранить исходную страницу с одной записью → append ещё двух записей → повторно сохранить исходную страницу с прежним call ID → попытаться append уже загруженной страницы.

**Факт:** набор сокращается с трёх записей до одной, revision становится 3. Append отвечает `{"appended": false, "revision": 3}`, поскольку ключ страницы сохранился в журнале. Дозагрузка не восстанавливает потерянные записи. Кроме того, первоначальная page provenance может расходиться с заново записанным payload.

**Условие:** повторное сохранение того же исходного вызова после дозагрузки, например при повторной обработке квитанции. Обычный новый вызов с новым call ID создаёт другой набор и сам по себе этот дефект не вызывает.

**Исправление:** определить идемпотентность initial save: повтор с тем же содержимым должен возвращать уже существующий набор вместе с его текущей ревизией; несовместимое повторное содержимое должно явно отклоняться. Если нужен отдельный reset/replace, он должен атомарно согласовывать records и page journal. Простое удаление журнала страниц устраняет лишь часть проблемы и продолжает терять append.

**Регрессия:** `save → append → same save → read/load`, включая одновременно пришедший duplicate save. Проверять содержимое, revision и согласованность provenance.

### F02 · P1 · Большие inputs/dependencies становятся недоступны агенту без инструментов

**Код:** [agent_executor.py](apps/api/src/app/runtime/agent_executor.py), строки 397 и 910–930; [result_workspace_tools.py](apps/api/src/app/agents/runtime/result_workspace_tools.py), строки 71–73.

`_prepare_task_context` переносит `inputs` и `dependency_outputs` длиннее 8000 символов в Result Store, оставляя только `saved_context`. Наличие инструментов чтения у потребителя не проверяется. `with_workspace_operations([])` возвращает пустой список. В сохранённом контексте дополнительно написано использовать `result.analyze SQL`, хотя SQL capability может отсутствовать и у агента с другими инструментами.

**Воспроизведение:** задача с `inputs={"text": "x" * 9000}`, активным root run и без resolved operations.

**Факт:** после подготовки ключи inputs — только `['saved_context']`; ссылка существует в PostgreSQL; доступных инструментов — 0. Исходного текста у модели больше нет, получить его штатным вызовом она не может. Это пороговое изменение поведения: небольшой контекст работает, большой перестаёт быть доступным.

**Исправление:** согласовать перенос контекста с capability потребителя. Гарантировать разрешённое чтение сохранённого контекста либо выбирать способ доставки, сохраняющий доступность inputs. Инструкции должны соответствовать фактически доступным `result.read`/SQL. Не следует выдавать analysis capability всем агентам только ради чтения контекста.

**Регрессия:** input и dependency output по обе стороны порога; агент без операций; агент только с domain tools; агент с SQL. Проверять доступность исходного содержания, а не наличие UUID.

### F03 · P2 · result.load не учитывает отдельные запросы к источнику

**Код:** [result_workspace_tools.py](apps/api/src/app/agents/runtime/result_workspace_tools.py), строки 128–155; [agent.py](apps/api/src/app/agents/runtime/agent.py), строки 1349–1351 и 1472–1474; [agent_executor.py](apps/api/src/app/runtime/agent_executor.py), строки 471–503.

Load loop вызывает `facade.execute` для каждой страницы, обходя `_execute_single_operation_call`, где проверяется лимит и создаются runtime events. Внешний `result.load` расходует один вызов, внутренние source calls не попадают в тот же учёт/журнал. Page provenance в results DB сохраняется, но это не эквивалент квитанциям и бюджетам runtime.

**Воспроизведение:** `PolicyLimits(max_tool_calls_total=1)`, набор с тремя оставшимися страницами, один `result.load(mode="remaining")` через runtime.

**Факт:** `network_calls=3`, `counted=1`, `events_tool_call=1`. Существующий default допускает до 20 страниц за load, конфигурация — до 100. Отдельные page/time/storage ограничения работают, но общий tool-call бюджет не ограничивает каждый источник.

**Исправление:** учитывать каждый реально исполненный source request через общий механизм бюджетирования и квитанций, проверяя остаток до запроса. Явно определить, считается ли управляющий load отдельной операцией, чтобы не получить случайный двойной расход.

**Регрессия:** remaining load с остатком бюджета 1/2/0, частичным сохранением и отказом на следующем запросе; сверять page calls, ledger, runtime events и task/run counters.

### F04 · P2 · Частичный collection.search объявляется полным

**Код:** [collection_search.py](apps/api/src/app/agents/builtins/collection_search.py), строки 303–310; [agent.py](apps/api/src/app/agents/runtime/agent.py), строки 1453–1460; [tool_result_store.py](apps/api/src/app/services/tool_result_store.py), строки 777–800.

Локальный search возвращает `{rows, total, returned, collection, has_more}`. Для local source runtime вызывает обычный `save`. Его `_source_complete` проверяет несколько известных массивов, но `rows` и `has_more` не учитывает.

**Воспроизведение:** `_source_complete({"rows": [{"id": 1}], "total": 100, "has_more": true})`.

**Факт:** результат `True`. При сохранении envelope становится одной записью, `source_total=100`, а `source_complete=true`. Неверный признак затем наследуют SQL-производные наборы через `all(source_complete)`.

**Исправление:** добавить явный адаптер локального collection search и применять единый протокол к dataset-ответам независимо от MCP/local транспорта. Для произвольного неизвестного payload сохранять неизвестную полноту вместо положительной эвристики. Не расширять угадывание произвольных JSON-путей.

**Регрессия:** partial/empty/full локальный поиск, offset > 0, SQL поверх частичного результата. Проверять количество records и upstream completeness отдельно от успешности запроса.

### F05 · P2 · Refresh descriptor объединяет новую ревизию со старой схемой

**Код:** [agent.py](apps/api/src/app/agents/runtime/agent.py), строки 1432–1439; [result_workspace.py](apps/api/src/app/services/result_workspace.py), строки 60–70; [tools.py](apps/api/src/app/agents/runtime/tools.py), строка 786.

При reuse загружается `describe`, затем shallow merge с прежним descriptor. `describe` удаляет `observed_schema` и отдаёт уже подготовленные `sql_columns`. Formatter заново вычисляет `sql_columns` из старого `observed_schema`, оставшегося после merge. Полученные от describe колонки не становятся источником для этой проекции.

**Воспроизведение:** первоначально колонки `id/name/site`; append страницы, добавляющей `new_column`; повторное использование исходного результата через runtime.

**Факт:** актуальный describe видит `id/name/new_column/site`; модель получает `id/name/site` при revision 2. При checkpoint, сохранившем только receipt без `observed_schema`, аналогичная схема объединения может дать пустую схему.

**Исправление:** обновлять descriptor из актуального канонического состояния, а не из пагинированной модельной проекции. Все schema/cardinality/revision/completeness поля должны относиться к одной версии. Samples также нужно обновлять или явно убирать.

**Регрессия:** append нового поля и изменения типа, reuse до/после pause, проверка реального model message и trace metadata.

### F06 · P2 · Большой meta обходит контекстный бюджет

**Код:** [tool_result_protocol.py](apps/api/src/app/services/tool_result_protocol.py), строка 9; [result_workspace.py](apps/api/src/app/services/result_workspace.py), строки 67–70; [tools.py](apps/api/src/app/agents/runtime/tools.py), строки 718–738.

`ResultMeta` разрешает произвольные дополнительные поля. `describe` переносит их почти полностью в ответ. Бюджет ограничивает схему, но не сам `dataset_meta`. Workspace formatter удаляет schema/sample, затем возвращает всё, что осталось, даже если лимит по-прежнему превышен.

**Воспроизведение:** нормализованный ответ с одной записью и `meta.diagnostics = "x" * 12000`, затем `describe` и штатный formatter.

**Факт:** модельный JSON занимает **13 010 байт** при бюджете **3600 байт**. Запрос другого schema offset ситуацию не исправляет: большой meta повторяется. Аналогично могут разрастаться errors и другое source metadata.

Проверка storage limit в `save` ограничивает нормализованный record payload; raw source page с метаданными сохраняется отдельно без аналогичной проверки размера всего envelope. Это дополнительное следствие отсутствия отдельного лимита metadata/provenance.

**Исправление:** ограниченная allowlist модельной metadata, отдельные лимиты source metadata/raw page, завершающая проверка размера всего ответа. Усечение должно оставлять валидный JSON и явно сообщать об опущенной metadata.

**Регрессия:** большое extra-поле, длинные errors, много source types, многобайтный UTF-8; проверять размер целого final message, а не только `sql_columns`.

### F07 · P2 · PostgreSQL numeric округляется при сохранении SQL-результата

**Код:** [tool_result_store.py](apps/api/src/app/services/tool_result_store.py), строки 275 и 693–702.

`_json_compatible` превращает дробный `Decimal` в Python `float`. Точная величина меняется до сохранения производного dataset и до передачи модели.

**Воспроизведение:** `SELECT 0.123456789012345678901234567890::numeric AS exact_value`.

**Факт:** сохранено/возвращено `0.12345678901234568`. Составление отчётов или дальнейшие SQL-вычисления выполняются уже над округлённым числом. Целые Decimal обрабатываются иначе и в этом примере проблемы не имеют.

**Исправление:** определить точный контракт numeric → JSON и использовать сериализацию без промежуточного binary float. Если выбрана строковая передача decimal, она должна быть явно отражена в типах/SQL-проекции; молча менять numeric на text также нельзя.

**Регрессия:** много значащих цифр, небольшие дроби, большие дробные значения, `SUM/AVG`, повторный SQL над сохранённым результатом.

### F08 · P2 · Скалярный value конфликтует с полем value объекта

**Код:** [result_sql_projection.py](apps/api/src/app/services/result_sql_projection.py), строки 17–32; [tool_result_store.py](apps/api/src/app/services/tool_result_store.py), функция `_profile_rows`.

Протокол допускает неоднородный `list[Any]`. Для скаляра schema использует `$` с пустым путём, а SQL-проекция переименовывает его в `value`. Позднее объектное поле `value` перезаписывает ту же запись в словаре колонок.

**Воспроизведение:** сохранённый payload `[1, {"value": "x"}]`.

**Факт:** полный read сохраняет исходный `1`, но `read(fields=["value"])` и `SELECT value` возвращают `[{"value": null}, {"value": "x"}]`. Это тихая потеря данных в двух поддерживаемых интерфейсах.

**Исправление:** определить явный контракт смешанных records: различимая проекция скаляров без коллизии с source fields либо явный отказ при конфликте. Текущая молчаливая перезапись недопустима.

**Регрессия:** mixed scalar/object, поле `value`, буквальное поле `$`, null и вложенный array record, разный порядок записей.

### F09 · P2 · Redactor склеивает различные ключи исходного JSON

**Код:** [redactor.py](apps/api/src/app/runtime/redactor.py), строки 60–74; вызов до persistence в [agent.py](apps/api/src/app/agents/runtime/agent.py), строка 1447.

Redactor делает `.strip()` для каждого ключа и записывает в результат уже изменённое имя. Это влияет на все source datasets до нормализации и SQL-профилирования.

**Воспроизведение:** `RuntimeRedactor().redact({" a": 1, "a ": 2})`.

**Факт:** `{"a": 2}`. Различные корректные JSON-поля сливаются, одно значение исчезает ещё до store. Это нарушает контракт точных source column names; SQL quoting уже не помогает восстановить потерянный ключ.

**Исправление:** нормализовать отдельную копию имени только для определения secret key; для формирования JSON сохранять оригинальное имя. Конфликты при иных обязательных преобразованиях должны быть явными.

**Регрессия:** leading/trailing whitespace, пары конфликтующих ключей и secret key с пробелами. Проверить одновременно редактирование секретного значения и сохранение имени поля.

### F10 · P2 · Циклическая continuation не останавливается с явной ошибкой

**Код:** [result_workspace.py](apps/api/src/app/services/result_workspace.py), строки 171–189; [result_workspace_tools.py](apps/api/src/app/agents/runtime/result_workspace_tools.py), строки 151–155.

Проверяется только немедленное равенство `next_arguments == arguments`. Цикл A → B → A проходит. При возврате к уже сохранённой странице `append_page` отвечает `appended=false`; load loop игнорирует этот флаг и увеличивает `pages_loaded` как при успешном append.

**Воспроизведение:** начальная страница offset 0 указывает offset 1; offset 1 указывает обратно offset 0. Загрузка offset 0 повторно.

**Факт:** `{"appended": false, "revision": 2}`, а сохранённый next по-прежнему `{"offset": 0}`. Цикл load повторяет источник до page/time budget, объявляя загруженными страницы без добавленных данных. Следующая попытка начинает с того же тупика.

**Условие:** ошибочная continuation опубликованного протокола или цикл аргументов более чем из одной страницы. Простая NetBox continuation с убывающим offset дополнительно проверяется адаптером; это не универсальная защита ResultPage.

**Исправление:** проверять прогресс по сохранённым page keys и ревизии; прекращать load при `appended=false` без изменения state. Если duplicate означает конкурентную загрузку, перечитать состояние и продолжить только после подтверждённого изменения continuation. Явно возвращать cycle/no-progress limitation.

**Регрессия:** A→A, A→B→A, конкурентный duplicate, точный retry уже совершённого append. Проверять фактически добавленные страницы и число source calls.

### F11 · P2 · Ошибка БД при read/describe пробивает границу инструмента

**Код:** [tools.py](apps/api/src/app/agents/runtime/tools.py), строки 145–147; [result_workspace_tools.py](apps/api/src/app/agents/runtime/result_workspace_tools.py), строки 115–118 и 162–163.

Native workspace tools вызываются до общего try/except executor. Их собственный обработчик ловит только `ToolResultStoreError`. `state/read/describe/append` не переводят все SQLAlchemy failures в эту доменную ошибку. SQL-path имеет собственное оборачивание ошибок, read-path — нет.

**Воспроизведение:** инъекция `sqlalchemy.exc.OperationalError` в `ResultWorkspace.state`, вызов `result.read` через настоящий facade.

**Факт:** `OperationalError` выходит из `facade.execute`; модель не получает `ToolResult.fail`, чтобы выбрать repair/partial. Аналогичный риск есть при падении повторного describe внутри обработчика load error. Фактический downstream статус всего run в fault-injection не проверялся.

**Исправление:** переводить ожидаемые storage/connection/timeout ошибки в ограниченный безопасный tool failure на единой границе workspace. Не перехватывать отмену coroutine как обычный успешный partial response. Полный traceback оставлять в серверном журнале.

**Регрессия:** fault injection для state/read/append/describe после частичного load, включая ошибку при сборке error response.

### F12 · P2 · Большая схема лишает reuse сохранённого result_id

**Код:** [tool_ledger.py](apps/api/src/app/runtime/memory/tool_ledger.py), строки 139–140, 180 и 212–216; [tool_reuse_policy.py](apps/api/src/app/agents/runtime/tool_reuse_policy.py), строки 35–59.

Ledger хранит `stored_result_id` независимо от `result_data`, однако поиск успешного результата требует непустого `result_data`. Слишком большой descriptor обнуляется лимитом `MAX_RESULT_CACHE_CHARS=24000`. В runtime safe projection входит вся observed schema, поэтому широкого ответа достаточно для достижения этого лимита даже без больших records в квитанции.

**Воспроизведение:** успешная ledger entry с действующим `result_id` и observed schema из 300 обычных полей; повторный поиск тех же operation/arguments в той же task phase.

**Факт:** `has_result_id=true`, `cached_data=null`, `reuse_found=false`.

**Последствие:** вместо чтения текущего descriptor выполняется новый внешний вызов, появляются новый dataset и лишний расход бюджета. Механизм references не устраняет зависимость reuse от размера схемы.

**Исправление:** разрешить reuse stored result по успешной квитанции и result ID с последующей проверкой доступности в store. Для direct delivery сохранять отдельную политику кэширования: у него нет dataset reference для восстановления body.

**Регрессия:** descriptor выше/ниже 24k, доступный и expired result, direct body выше лимита, schema с сотнями полей.

### F13 · P2 · result.find использует разную Unicode-нормализацию двух сторон

**Код:** [result_workspace.py](apps/api/src/app/services/result_workspace.py), строки 148–150.

Параметр запроса преобразуется Python `casefold()`, а saved record — PostgreSQL `lower()`. Эти операции имеют разные правила. Например, casefold превращает `ß` в `ss`, lower — оставляет `ß`.

**Воспроизведение:** сохранить `[{"name": "Straße"}]`, вызвать `result.find(q="Straße")`.

**Факт:** результат пустой, хотя исходная строка содержит точный query. Это не вопрос поиска другого регистра: не находится даже исходное написание.

**Исправление:** применять согласованное преобразование обеих сторон, например `lower` к bound parameter в том же PostgreSQL выражении. Если нужен именно full Unicode caseless matching, явно выбрать и одинаково реализовать этот контракт.

**Регрессия:** точное совпадение, варианты регистра, `ß`, Unicode sigma, кириллица и literal wildcard characters.

### F14 · P2 · Checkpoint превращает direct listing в успешно переиспользуемую пустую квитанцию

**Код:** [agent.py](apps/api/src/app/agents/runtime/agent.py), строки 449–465 и helper `_checkpoint_receipt`; [tool_reuse_policy.py](apps/api/src/app/agents/runtime/tool_reuse_policy.py), строки 35–59; [tool_ledger.py](apps/api/src/app/runtime/memory/tool_ledger.py), строки 180–186.

Checkpoint распознаёт read-операции по суффиксам `.read/.search/.list/.get/.fetch/.lookup`. `collection.list_documents` и `collection.doc_search` этим суффиксам не соответствуют. Их direct body заменяется `_checkpoint_receipt`, но successful status и direct delivery сохраняются. `_checkpoint_receipt` добавляет `{"_operation_completed": true}` даже когда не извлёк ни одного полезного поля.

**Воспроизведение:** successful direct `collection.list_documents` с documents → применить фактическое преобразование checkpoint → восстановить ToolLedger → повторить те же operation/arguments через reuse policy в той же task.

**Факт:** `classified_read=false`, `reused=true`, `delivery=direct`, `data={"_operation_completed": true}`. Dataset reference для восстановления исходного body отсутствует. Источник не вызывается, документов в результате больше нет.

Проверка выполнена на checkpoint-преобразовании и reuse-компонентах; полный чат с пользовательской паузой в рамках этого сценария не запускался.

**Исправление:** использовать канонические свойства операций/read-only classification вместо эвристики окончания строки. Отдельно определять пригодность checkpoint entry для body reuse. Квитанция о выполнении не должна считаться полным direct-результатом чтения.

**Регрессия:** pause/resume для `collection.list_documents`, `collection.doc_search`, instance-bound aliases и stored MCP datasets; проверить сохранение сведений об исполнении и необходимость повторного авторизованного чтения body.

## Риски и расхождения, требующие отдельного решения

Эти пункты не включены в 14 подтверждённых дефектов: для них нужна отдельная спецификация либо нагрузочное/сквозное воспроизведение.

### R01 · SQL output обходит redactor перед persistence/model presentation

`ToolResultStore.execute_sql` передаёт query rows прямо в `save`; runtime принимает `stored_result` и `workspace_view`, поэтому обычная ветка redaction пропускается. Синтетический `SELECT 'sensitive' AS api_token` сохраняет строку и передаёт её модели, тогда как source response с таким ключом был бы отредактирован.

Это подтверждённое различие путей обработки, но приведённый пример **не доказывает утечку секрета из внешней системы**: литерал был введён самим запросом. Нужно определить, является ли повторная redaction вычисленного SQL output обязательным контрактом, и проверить сценарии реальных источников, trace и SSE. Простое редактирование только model message оставит расхождение с сохранённым набором.

### R02 · SQL byte limit применяется после буферизации DB result

В `execute_sql`, строки 273–278, используется buffered `connection.execute`, затем Python проверяет суммарные байты. Большой SELECT может занять память драйвера до срабатывания лимита. Statement timeout ограничивает время, row cap — число строк, но ни один не равен byte cap уже передаваемого результата.

Исходное наблюдение было до фикса. Теперь запрос исполняется через SQLAlchemy streaming API в рамках repeatable-read транзакции с timeout и ограничениями числа строк/байтов; нагрузочный benchmark после изменения не запускался.

### R03 · Legacy result.analyze v1 имеет отдельную модель payload/path

V1 select/aggregate требует непустой `array_path`, а новый MCP pipeline сохраняет корневой массив records. Старый путь вроде `issues`/`results` уже не существует; универсального пустого root path `_path_segments` не допускает. V1 project/text также продолжают работать с payload paths, а не с column map.

Нужно проверить реально опубликованные/pinned версии `result.analyze` и документировать миграционную совместимость. Без такого инвентаря нельзя утверждать, что проблема проявляется в активных agent bindings. В V2 input schema также осталось описание `JSON values are available in data`, конфликтующее с текущими top-level virtual columns.

### R04 · Полнота вложенных страниц Jira трактуется неодинаково

Старый `_source_complete` учитывает вложенные comments/worklogs; новый Jira search adapter определяет полноту по внешним `issues/startAt/total`. Одна страница всех issues может содержать неполные вложенные comments.

Нужна явная спецификация: означает ли `source_complete` полноту набора issues либо всех вложенных сущностей ответа. Если это только полнота внешнего набора, нужны отдельные признаки вложенной неполноты, когда такие поля используются в расчётах. Автоматически объявлять ошибкой любого такого результата без определения контракта нельзя.

### R05 · Cross-call pagination find/aggregate не фиксирует входную revision

`result.read` принимает revision, SQL фиксирует snapshot одного вызова. У пагинированных wrappers нет revision parameter: две страницы offset могут относиться к разным состояниям после append. У find дополнительно отсутствует явный ORDER BY.

Если wrappers предназначены для последовательного полного перечисления результатов, нужно определить порядок, перенос input revisions и поведение при изменении источника между вызовами. Существующий `page_may_have_more` не подтверждает стабильность pagination. Конкурентное сквозное воспроизведение не выполнялось.

## Что существующие проверки подтверждают

- Initial metadata, record rows и source-page provenance сохраняются одной транзакцией; ошибка page storage откатывает initial dataset.
- Обычный append блокирует parent и проверяет revision/continuation; точный повтор страницы не дублирует записи.
- `result.read` различает loaded/read/source completeness, валидирует fields и позволяет зафиксировать revision.
- Проверки run/user/tenant/TTL присутствуют в workspace access; integration suite проверяет недоступность чужих результатов. Обход этих проверок ревью не продемонстрировало.
- SQL guard отклоняет проверенные physical/foreign tables, schema-qualified/unsupported functions и write statements. Это не формальный аудит всех конструкций PostgreSQL/sqlglot.
- SQL читает metadata и records в repeatable-read transaction и сохраняет input revisions в lineage.
- В PostgreSQL пустой virtual projection допускается: `SELECT count(*)` поверх пустого dataset вернул `0`. Предположение, что пустая схема обязательно ломает SQL, проверено и отклонено.
- Большой успешный SQL output сохраняется целиком при прохождении лимитов; model delivery и storage eligibility в проверенных тестах различаются корректно.
- Обновление datastore после resume покрыто существующими тестами; F05 и F14 относятся к другим механизмам — reuse descriptor и сохранению direct body.

## Предлагаемый порядок исправления

1. **Целостность и доступность данных:** F01, F02. Сначала regression-тесты на потерю append и недоступный task context.
2. **Верность наблюдений модели:** F04, F05, F07, F08, F09, F14. Исправления должны проверять фактический model message и сохранённые records.
3. **Контроль исполнения и отказов:** F03, F06, F10, F11. Проверять partial load, реальные counters и размер целого ответа.
4. **Кэш и поиск:** F12, F13.
5. R01–R05 закрыты в коде follow-up; после изменений нужны профильные тесты и ограниченное нагрузочное исследование streaming SQL.

После изменений обновить `docs/architecture/RUNTIME_TOOL_RESULTS.md` и соответствующие runtime/tool contracts. Особенно важно описать поведение duplicate initial save, доставку большого контекста агентам без SQL, учёт внутренних load requests и восстановление direct results. Добавление новых эвристик JSON-path/названий операций только увеличит число несовместимых путей.

## Проверки и воспроизведение

Команда существующего набора из корня репозитория:

```bash
docker compose exec -T -e TOOL_WORKSPACE_PG=1 api python -m pytest \
  tests/unit/test_result_workspace.py \
  tests/unit/test_result_analyze.py \
  tests/unit/test_tool_result_delivery.py \
  tests/unit/test_datastore_context.py \
  tests/unit/test_tool_ledger.py \
  tests/unit/test_runtime_resume_checkpoint_service.py \
  tests/integration/test_result_workspace_sql.py -q
```

Результат: **80 passed, 3 warnings, 9.52s**. Warnings касаются существующего Pydantic field `schema`, затеняющего атрибут `BaseModel`. В дополнительных probes также появилось существующее предупреждение о dev fallback `CONFIRMATION_SECRET`; оно не использовалось как находка этого ревью.

Ниже включены полные дополнительные probes, чтобы отчёт оставался воспроизводимым без временных файлов текущей сессии. Первый блок сохранить как `/tmp/result_store_review_probes.py`, второй — как `/tmp/result_store_deep_review_probes.py`. Команды запуска из корня репозитория:

```bash
docker compose exec -T api python - < /tmp/result_store_review_probes.py
docker compose exec -T api python - < /tmp/result_store_deep_review_probes.py
```

Скрипты используют существующую integration fixture через `__wrapped__`: создают отдельную схему, применяют четыре миграции и удаляют схему в `finally`. Скрипт direct-resume воспроизводит фактическое преобразование checkpoint на уровне компонентов; не заменяет end-to-end тест паузы. Полный benchmark нагрузки, реальный failover БД и живые внешние API этим отчётом не охвачены.

### Наблюдённые результаты probes

```text
REPLAY: appended=false, revision=3, rows=[первоначальная запись], row_count=1
MIXED_READ: [{"value": null}, {"value": "x"}]
MIXED_SQL:  [{"value": null}, {"value": "x"}]
EMPTY_COUNT: [{"count": 0}]
STALE_REUSE_SCHEMA: actual=[id,name,new_column,site], model=[id,name,site], revision=2
DECIMAL: [{"exact_value": 0.12345678901234568}]
KEY_COLLISION: {"a": 2}
LOCAL_PARTIAL: true
UNBOUNDED_META: actual_bytes=13010, budget=3600
SQL_REDACTION: saved=[{"api_token":"sensitive"}], model_contains_secret=true
BUDGET: network_calls=3, counted=1, events_tool_call=1
CYCLE: appended=false, revision=2, next={"offset":0}
CONTEXT_NO_TOOLS: input_keys=[saved_context], tools=0, reference=true
WIDE_LEDGER: has_result_id=true, cached_data=null, reuse_found=false
UNICODE_FIND: q="Straße", rows=[]
DB_FAILURE: uncaught=OperationalError
DIRECT_AFTER_RESUME: classified_read=false, reused=true, data={"_operation_completed":true}, delivery=direct
```

### Полный код result_store_review_probes.py

```python
import asyncio
import importlib.util
from pathlib import Path
from pytest import MonkeyPatch
from sqlalchemy import text

spec = importlib.util.spec_from_file_location('review_fixture', Path('tests/integration/test_result_workspace_sql.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def main():
    patch = MonkeyPatch()
    fixture = module.workspace_pg.__wrapped__(patch)
    workspace, scope, engine = await anext(fixture)
    try:
        from app.services.tool_result_store import ToolResultStore
        store = ToolResultStore()
        saved, _ = await module.save(workspace, scope)
        ref = {**scope, 'result_id': saved['result_id']}
        state = await workspace.state(**ref)
        args = state['dataset_meta']['next_arguments']
        page = {'count': 3, 'results': [{'id': 2}, {'id': 3}], 'next': None}
        await workspace.append_page(payload=page, source_tool='netbox_get_objects', arguments=args, expected_revision=1, call_id='page2', **ref)
        await module.save(workspace, scope)
        retry = await workspace.append_page(payload=page, source_tool='netbox_get_objects', arguments=args, expected_revision=3, call_id='page2-retry', **ref)
        print('REPLAY', {'append': retry, 'rows': (await workspace.read(**ref))['value'], 'state': (await workspace.describe(**ref))['row_count']})
        mixed = await store.save(payload=[1, {'value': 'x'}], call_id='mixed', operation='api.test', task_id='t', agent_execution_id='a', **scope)
        print('MIXED_READ', (await workspace.read(result_id=mixed['result_id'], fields=['value'], **scope))['value'])
        print('MIXED_SQL', (await store.execute_sql(sql=f"SELECT value FROM {mixed['sql_ref']}", call_id='mixed-sql', task_id='t', agent_execution_id='a', **scope))['rows'])
        empty = await store.save(payload=[], call_id='empty', operation='api.test', task_id='t', agent_execution_id='a', **scope)
        print('EMPTY_COUNT', (await store.execute_sql(sql=f"SELECT count(*) AS count FROM {empty['sql_ref']}", call_id='empty-sql', task_id='t', agent_execution_id='a', **scope))['rows'])
    finally:
        try:
            await anext(fixture)
        except StopAsyncIteration:
            pass
        patch.undo()

asyncio.run(main())
```

### Полный код result_store_deep_review_probes.py

```python
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from pytest import MonkeyPatch
from sqlalchemy import text

spec = importlib.util.spec_from_file_location('review_fixture', Path('tests/integration/test_result_workspace_sql.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

async def main():
    patch = MonkeyPatch()
    fixture = module.workspace_pg.__wrapped__(patch)
    workspace, scope, engine = await anext(fixture)
    from app.services.tool_result_store import ToolResultStore, _source_complete
    from app.agents.context import ToolCall, ToolContext, ToolResult
    from app.agents.runtime.agent import AgentLoopState, AgentToolRuntime
    from app.agents.runtime.policy import PolicyLimits
    from app.agents.runtime.tools import OperationExecutionFacade
    from app.agents.runtime.result_workspace_tools import with_workspace_operations
    from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
    from app.runtime.redactor import RuntimeRedactor
    from app.core.config import get_settings
    store = ToolResultStore()
    async def saved(payload, call, **kw):
        return await store.save(payload=payload, call_id=call, operation='api.test', task_id='t', agent_execution_id='a', **scope, **kw)
    async def query(sql, call):
        return await store.execute_sql(sql=sql, call_id=call, task_id='t', agent_execution_id='a', **scope)
    async def agent_call(runtime, call, ctx, operations, max_calls=10):
        session = SimpleNamespace(run_id=uuid4(), record_event=AsyncMock(), finish=AsyncMock())
        messages, calls = [], [0]
        events = [event async for event in runtime._execute_single_operation_call(
            operation_call=call, agent_slug='reviewer', agent_execution_id='execution', llm_call_id='llm', ctx=ctx,
            available_operations=operations, policy=PolicyLimits(max_tool_calls_total=max_calls), run_session=session,
            all_operation_outputs=[], all_sources=[], loop_state=AgentLoopState(), operation_results_for_context=messages,
            operation_calls_total_ref=calls, remaining_wall_time_ms=60000)]
        return messages, calls, events
    try:
        initial, _ = await module.save(workspace, scope, call='refresh-source')
        await workspace.append_page(payload={'count': 3, 'results': [{'id': 2, 'new_column': 'new'}, {'id': 3}], 'next': None},
            source_tool='netbox_get_objects', arguments=initial['dataset_meta']['next_arguments'], expected_revision=1,
            call_id='refresh-page', result_id=initial['result_id'], **scope)
        current = await workspace.describe(result_id=initial['result_id'], **scope)
        runtime = AgentToolRuntime(Mock())
        runtime.tools.execute = AsyncMock(return_value=(ToolResult.ok({}, reused=True, stored_result=initial), []))
        ctx = ToolContext(user_id=scope['user_id'], tenant_id=scope['tenant_id'], extra={'runtime_root_run_id':scope['run_id']})
        messages, _, _ = await agent_call(runtime, ToolCall(id='reuse', tool_name='netbox_get_objects', arguments={}), ctx, [])
        rendered = json.loads(messages[0][1])['_runtime_result']
        print('STALE_REUSE_SCHEMA', {'actual': list(current['sql_columns']), 'model':list(rendered['sql_columns']), 'revision':rendered['revision']})

        decimal_query = await query('SELECT 0.123456789012345678901234567890::numeric AS exact_value', 'decimal-query')
        print('DECIMAL', decimal_query['rows'])
        print('KEY_COLLISION', RuntimeRedactor().redact({' a': 1, 'a ': 2}))
        print('LOCAL_PARTIAL', _source_complete({'rows':[{'id':1}], 'total':100, 'has_more':True}))

        huge, _ = await workspace.save_source(payload={'value':[{'id':1}], 'meta':{'source':'review','complete':True,'diagnostics':'x'*12000}},
            source_tool='api.normalized', arguments={}, operation='api.normalized', call_id='huge-meta', task_id='t', agent_execution_id='a', **scope)
        view = await workspace.describe(result_id=huge['result_id'], **scope)
        text_view = OperationExecutionFacade.format_result_for_context(ToolResult.ok(view, workspace_view=True))
        print('UNBOUNDED_META', {'actual_bytes':len(text_view.encode()), 'budget':min(4000, get_settings().TOOL_RESULTS_CONTEXT_TOKENS*3)})

        secret_query = await query("SELECT 'sensitive' AS api_token", 'secret-query')
        secret_read = await workspace.read(result_id=secret_query['result_id'], **scope)
        secret_model = OperationExecutionFacade.format_result_for_context(ToolResult.ok(secret_query, stored_result=secret_query['_stored_result'], workspace_view=True), stored_result=secret_query['_stored_result'])
        print('SQL_REDACTION', {'saved':secret_read['value'], 'model_contains_secret':'sensitive' in secret_model})

        source = ResolvedOperation(operation_slug='netbox_get_objects', operation='read', name='Devices', source='mcp', scope='system',
            data_instance_id='netbox', data_instance_slug='netbox', input_schema={'type':'object'},
            target=ProviderExecutionTarget(operation_slug='netbox_get_objects', provider_type='mcp', mcp_tool_name='netbox_get_objects', data_instance_id='netbox', data_instance_slug='netbox'))
        operations = with_workspace_operations([source])
        budget_source, _ = await module.save(workspace, scope, call='budget-source', total=4)
        async def source_page(call, context):
            offset = call.arguments['offset']
            return ToolResult.ok({'count':4, 'results':[{'id':offset+1}], 'next':f'https://netbox/api/?offset={offset+1}&limit=1' if offset<3 else None})
        executor = SimpleNamespace(execute=AsyncMock(side_effect=source_page))
        deps = ctx.get_runtime_deps()
        deps.operation_executor = executor
        ctx.set_runtime_deps(deps)
        runtime = AgentToolRuntime(Mock())
        runtime.tools = OperationExecutionFacade()
        messages, calls, events = await agent_call(runtime, ToolCall(id='budget-load', tool_name='result.load', arguments={'result_id':budget_source['result_id'],'mode':'remaining'}), ctx, operations, max_calls=1)
        print('BUDGET', {'network_calls':executor.execute.await_count, 'counted':calls[0], 'events_tool_call':sum(e.type.value=='tool_call' for e in events)})

        cycle, _ = await workspace.save_source(payload={'value':[{'id':1}], 'meta':{'has_next':True,'next_arguments':{'offset':1}}}, source_tool='api.cycle',
            arguments={'offset':0}, operation='api.cycle', call_id='cycle-source', task_id='t', agent_execution_id='a', **scope)
        await workspace.append_page(payload={'value':[{'id':2}], 'meta':{'has_next':True,'next_arguments':{'offset':0}}}, source_tool='api.cycle',
            arguments={'offset':1}, expected_revision=1, call_id='cycle-page', result_id=cycle['result_id'], **scope)
        no_progress = await workspace.append_page(payload={'value':[{'id':1}], 'meta':{'has_next':True,'next_arguments':{'offset':1}}}, source_tool='api.cycle',
            arguments={'offset':0}, expected_revision=2, call_id='cycle-again', result_id=cycle['result_id'], **scope)
        print('CYCLE', {'append':no_progress, 'next':(await workspace.state(result_id=cycle['result_id'],**scope))['dataset_meta']['next_arguments']})

        from app.runtime.agent_executor import AgentExecutor
        from app.runtime.orchestrator_contracts import TaskRequest
        task = TaskRequest(task_id='no-tools', executor='writer', intent='summarize', instructions='Summarize inputs', inputs={'text':'x'*9000})
        prepared = await AgentExecutor._prepare_task_context(task, ctx, 'review-context')
        print('CONTEXT_NO_TOOLS', {'input_keys':list(prepared.inputs), 'tools':len(with_workspace_operations([])), 'reference':bool(prepared.inputs.get('saved_context'))})

        from app.runtime.memory.tool_ledger import ToolLedger
        ledger = ToolLedger()
        ledger.register_call(operation='api.read', call_id='wide', arguments={}, iteration=1, agent_slug='a', phase_id='t')
        ledger.register_result(call_id='wide', success=True, data={'observed_schema':{'column'+str(i):{'types':['string'],'present':1,'missing':0,'null':0,'path_segments':['column'+str(i)]} for i in range(300)}}, result_id=initial['result_id'])
        print('WIDE_LEDGER', {'has_result_id':bool(ledger.entries[0].stored_result_id), 'cached_data':ledger.entries[0].result_data, 'reuse_found':ledger.find_successful_result(operation='api.read',arguments={},phase_id='t') is not None})

        street = await saved([{'name':'Straße'}], 'find-unicode')
        found = await workspace.standard_query(kind='find', q='Straße', result_id=street['result_id'],call_id='find-unicode-query',task_id='t',agent_execution_id='a',**scope)
        print('UNICODE_FIND', {'q':'Straße','rows':found['rows']})

        from sqlalchemy.exc import OperationalError
        original_state = workspace.__class__.state
        patch.setattr(workspace.__class__, 'state', AsyncMock(side_effect=OperationalError('SELECT',{},Exception('simulated outage'))))
        try:
            reply, _ = await OperationExecutionFacade().execute(ToolCall(id='read-outage',tool_name='result.read',arguments={'result_id':initial['result_id']}),ctx,operations)
            print('DB_FAILURE', {'returned_success':reply.success})
        except OperationalError:
            print('DB_FAILURE', {'uncaught':'OperationalError'})
        finally:
            patch.setattr(workspace.__class__, 'state', original_state)

        from app.agents.runtime.agent import _checkpoint_receipt
        from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
        resumed_ledger = ToolLedger()
        resumed_ledger.register_call(operation='collection.list_documents',call_id='direct-before-pause',arguments={'collection_slug':'docs'},iteration=1,agent_slug='a',phase_id='t')
        resumed_ledger.register_result(call_id='direct-before-pause',success=True,data={'documents':[{'artifact_id':'example-reference'}]},result_delivery='direct')
        checkpoint = resumed_ledger.model_dump(mode='json')
        entry = checkpoint['entries'][0]
        read_operation = entry['operation'].endswith(('.read','.search','.list','.get','.fetch','.lookup'))
        entry['result_data'] = None if read_operation else _checkpoint_receipt(entry['result_data'])
        resume_ctx = ToolContext(user_id=scope['user_id'],tenant_id=scope['tenant_id'],extra={'runtime_tool_ledger':ToolLedger.model_validate(checkpoint),'runtime_task_id':'t'})
        reused, _ = ToolCallReusePolicy().maybe_reuse(operation_slug='collection.list_documents',arguments={'collection_slug':'docs'},ctx=resume_ctx)
        print('DIRECT_AFTER_RESUME', {'classified_read':read_operation,'reused':reused.metadata.get('reused'),'data':reused.data,'delivery':reused.delivery})
    finally:
        try:
            await anext(fixture)
        except StopAsyncIteration:
            pass
        patch.undo()

asyncio.run(main())
```
