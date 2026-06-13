# План: контракт схемы шаблонов и пайплайн заполнения

Статус: ✅ Все этапы S0-S7 выполнены
Владелец артефакта: backend (template collection)
Дата: 2026-06-12

---

## 0. Цель и принципы

Template-коллекция = библиотека заполняемых документов (Excel / Word / text) с
плейсхолдерами. Агентский флоу: **discover → understand → fill**.

`template_schema` (далее — **контракт**) — первичный артефакт. Из него:
- выводится `fill_input_schema` (JSON-форма, которую генерит LLM при заполнении);
- валидируются входные `values`;
- строится семантическое `description` для дисскавери.

### Принципы контракта
- **Position-independent.** Опора на токены/якоря, не на координаты (поля двигаются).
- **Provenance-aware.** LLM генерит черновик, админ правит; ре-анализ не затирает
  залоченные/админские поля.
- **Два режима таблиц (Both).** Приоритет — marker-loop (шаблон размечен токенами);
  fallback — structural (без разметки, таблицы детектируются по структуре/шапке).
- **Single source of truth.** Контракт = Pydantic-модель; всё остальное (fill,
  валидация, derived schema) опирается только на неё.

---

## 1. Контракт схемы (целевой формат)

```jsonc
{
  "contract_version": "1.0",
  "format": "excel|docx|text",
  "fields": [
    {
      "key": "applicant_name",
      "kind": "scalar",
      "label": "ФИО заявителя",
      "description": "Полное имя заявителя, как в паспорте",
      "type": "string|number|date|bool|enum",
      "required": true,
      "example": "Иванов Иван Иванович",
      "enum": null,
      "format": null,
      "locator": { "token": "{{applicant_name}}" },
      "source": "llm|admin",
      "locked": false
    },
    {
      "key": "items",
      "kind": "table",
      "label": "Позиции заявки",
      "description": "Список запрашиваемых позиций",
      "orientation": "vertical|horizontal",
      "required": true,
      "min_rows": 1,
      "max_rows": null,
      "anchor": {
        "sheet": "Лист1",
        "strategy": "auto",
        "marker": { "loop_tokens": ["{{items.name}}", "{{items.qty}}"] },
        "structural": {
          "header_signature": ["Наименование", "Кол-во", "Цена"],
          "match": "fuzzy",
          "template_row": "first_after_header"
        }
      },
      "columns": [
        { "key": "name",  "label": "Наименование", "type": "string", "required": true,  "locator": { "token": "{{items.name}}" } },
        { "key": "qty",   "label": "Кол-во",        "type": "number", "required": true,  "locator": { "token": "{{items.qty}}" } },
        { "key": "price", "label": "Цена",          "type": "number", "required": false, "locator": { "token": "{{items.price}}" } }
      ],
      "source": "llm",
      "locked": false
    }
  ]
}
```

### Конвенции
- Скаляр: токен `{{key}}`.
- Колонка таблицы: dotted-префикс `{{<table_key>.<column_key>}}`.
- Опц. для docx-блоков: фенсы `{{#items}} … {{/items}}`.
- Типы: `string | number | date | bool | enum`.
- `orientation`: `vertical` — рост вниз (клонируем строки); `horizontal` — рост
  вправо (клонируем колонки).

### Derived `fill_input_schema`
Детерминированно из контракта:
- `scalar` → плоский типизированный ключ;
- `table` → массив объектов из `columns`.

```json
{
  "applicant_name": "string",
  "items": [ { "name": "string", "qty": 0, "price": 0 } ]
}
```

---

## 2. Стадии реализации

Зависимости: S0 — фундамент. S1→S2→S3 — последовательная цепочка (анализ).
S4 (fill) и S5 (tools) зависят только от S0 и идут параллельно цепочке анализа.

### S0. Контракт-модуль (фундамент) — БЛОКЕР

**Deliverables**
- Pydantic-модели: `TemplateContract`, `ScalarField`, `TableField`, `Column`,
  `Anchor`, `MarkerAnchor`, `StructuralAnchor`, enums (`FieldKind`, `FieldType`,
  `Orientation`, `FieldSource`, `AnchorStrategy`).
- `contract.to_fill_input_schema() -> dict` — derived JSON-схема для планнера.
- `contract.validate_values(values) -> ValidationReport` — проверка required,
  типов, неизвестных ключей, min/max_rows.
- `merge_contract(existing, proposed) -> TemplateContract` — provenance-merge
  (locked/admin неприкосновенны).
- Сериализация в/из `template_schema` JSONB (back-compat: старый формат → пустой
  контракт без падений).

**Критерии приёмки**
- Round-trip: `Contract → json → Contract` стабилен.
- `to_fill_input_schema` для scalar+table даёт корректную форму (юнит-тест).
- `validate_values` ловит: missing required, неверный тип, unknown key,
  нарушение min/max_rows (юнит-тесты).
- `merge_contract` сохраняет `locked=true` и `source=admin` поля без изменений,
  добавляет/обновляет/удаляет только `source=llm` (юнит-тесты).
- Старый формат схемы (`{format, sheets, placeholders}`) парсится без ошибок.

### S1. Parser (детерминированный layout) — зависит от S0

**Deliverables**
- `TemplateLayoutParser`: из bytes+filename → `RawLayout`
  (все токены с позициями, листы, таблицы-кандидаты, строки-шапки, карта ячеек,
  обнаруженные marker-токены и фенсы).
- Чистая функция, без LLM, без записи в БД.

**Критерии приёмки**
- Excel: извлекает все `{{...}}` (включая dotted), шапки, строки-кандидаты таблиц.
- Docx: извлекает токены из параграфов и таблиц, фенсы `{{#x}}..{{/x}}`.
- Text: извлекает токены построчно.
- Юнит-тесты на фикстурах (размеченный и неразмеченный xlsx).

### S2. Schema generation (LLM) — зависит от S1

**Deliverables**
- `TemplateSchemaBuilder`: `RawLayout (+ existing contract) → TemplateContract`.
- LLM-проход: группировка токенов в scalar/table, определение orientation, типов,
  label/description, required; распознавание таблиц в неразмеченном файле по
  структуре.
- Вызов `merge_contract` с существующим контрактом (сохранение админ-правок).
- Детерминированный fallback, если LLM недоступен/ошибка: эвристика как минимум
  выделяет scalars и таблицы по header_signature.

**Критерии приёмки**
- Размеченный xlsx → контракт с корректными table-полями и колонками.
- Неразмеченный xlsx с двумя таблицами → два `table`-поля с разными anchor.
- Повторный прогон поверх контракта с `locked` полем не меняет это поле.
- При недоступном LLM — деградация на эвристику, без падения таски.

### S3. Description generation (LLM) — зависит от S2

**Deliverables**
- `TemplateDescriptionBuilder`: `TemplateContract (+ title/контент) → description`
  (семантика: назначение шаблона, когда применять, какие данные нужны).
- Запись в поле `description` (used_in_retrieval / prompt_context).
- Уважение `locked` для описания (если админ правил — не затирать).

**Критерии приёмки**
- Описание ссылается на ключевые поля/таблицы из контракта.
- Админ-правка описания (`description_locked`) сохраняется при ре-анализе.
- Деградация при недоступном LLM (минимальное осмысленное описание из контракта).

### S4. Fill engine (Both: marker → structural) — зависит от S0

**Deliverables**
- `TemplateFillEngine`: `contract + values + file_bytes → filled_bytes + report`.
- Excel/Docx/Text. Скаляры — подстановка по токену (position-independent).
- Таблицы:
  - marker-loop: найти строку/колонку-маркер по `loop_tokens`, клонировать на
    каждую запись (vertical — строки вниз, horizontal — колонки вправо), удалить
    маркер;
  - structural fallback: найти шапку по `header_signature` (fuzzy), взять
    `template_row`, дописать записи.
- regex плейсхолдеров расширить: `[A-Za-z0-9_.\-]+` (поддержка dotted).
- Отчёт: filled/missing/ignored ключи.

**Критерии приёмки**
- Vertical-таблица: N записей (N > числа строк в шаблоне) → N строк в выходе,
  содержимое ниже таблицы корректно сдвинуто.
- Horizontal-таблица: записи добавляются как колонки.
- Скаляр находится при сдвинутой позиции (тест с переставленными ячейками).
- Размеченный → marker; неразмеченный с шапкой → structural (оба теста зелёные).
- `values`, не прошедшие `validate_values`, отклоняются до записи.

### S5. Tools update — зависит от S0/S4

**Deliverables**
- `template.get_schema`: возвращает и контракт, и `fill_input_schema`
  (планнер знает точную форму).
- `template.fill`: вызывает `validate_values` до заполнения; использует
  `TemplateFillEngine`; внятные ошибки по missing/unknown/типам.
- `template.list`: без изменений (проверить).

**Критерии приёмки**
- `get_schema` отдаёт оба представления; при пустом контракте — guidance.
- `fill` с невалидными `values` → fail с перечнем проблем, файл не создаётся.
- `fill` с валидными `values` (scalar+table) → корректный файл, `file_id`.

### S6. Task pipeline refactor (зависимая цепочка) — зависит от S1–S3

**Deliverables**
- Заменить параллельные `generate_template_description` + `generate_template_schema`
  на Celery-chain: `parse → schema → description`.
- Файл из S3 грузится один раз (parse), layout передаётся по цепочке (или
  кэшируется), без двойного парса.
- Единая логика статусов (устранить дубль `_resolve_template_status` /
  `_resolve_next_template_status`): статус выставляется детерминированно в конце
  цепочки, без гонки.
- Узлы прогресса (`parse`/`schema`/`description`) в статус-графе и SSE.

**Критерии приёмки**
- Файл скачивается из S3 один раз на анализ (проверяется логом/метрикой).
- Нет гонки статусов: статус выставляется в одной точке.
- SSE отражает 3 узла; ошибки нод корректно прокидываются.
- Re-analyze (`/templates/analyze`) перезапускает цепочку с сохранением
  админ-правок.

### S7. Admin edit / provenance — сквозная

**Deliverables**
- PATCH контракта/описания помечает поля `source=admin` / `locked=true`.
- UI редактирования контракта (поля, типы, required, описания, таблицы) — отдельная
  задача фронта (вне этого backend-плана, но контракт должен это поддерживать).

**Критерии приёмки**
- После админ-правки и ре-анализа правки сохранены.
- API возвращает `source`/`locked` для каждого поля.

### S8. Тесты и документация

**Deliverables**
- Юнит-тесты по каждой стадии (S0–S6).
- Интеграционный тест: upload → chain → ready → get_schema → fill.
- Обновить `docs/collections/TEMPLATE_COLLECTION.md` (убрать неверное про LLM,
  описать контракт, Both-стратегию, derived schema, pipeline).

**Критерии приёмки**
- Зелёный прогон тестов.
- Документация соответствует реализации (no LLM-вранья).

---

## 3. Порядок работ

1. **S0** (блокер, фундамент).
2. Параллельно после S0:
   - ветка анализа: **S1 → S2 → S3 → S6**;
   - ветка заполнения: **S4 → S5**.
3. **S7** дорабатывается по мере S2/S5.
4. **S8** — по завершении каждой стадии (тесты) + финальная сверка docs.

---

## 4. Открытые вопросы / риски

- Excel merged-cells при клонировании строк/колонок (особенно horizontal).
- Docx-таблицы со сложной структурой (вложенные таблицы).
- Качество/стоимость LLM-прохода на больших файлах (лимит контента в промпт).
- Обратная совместимость существующих шаблонов со старым `template_schema`.
