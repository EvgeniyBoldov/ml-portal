# ContractAwareEditor — План реализации

## Концепция

Универсальный расширенный текстовый редактор, который отображает рядом с textarea
"легенду контракта" — структурированное описание полей ответа и/или входных данных.
Позволяет инженеру писать правила/промпты, видя в реальном времени какие поля контракта
уже описаны, а какие — нет.

---

## 1. Компоненты

### 1.1 `ContractAwareEditor` (главный компонент)

**Расположение:** `apps/web/src/shared/ui/ContractAwareEditor/ContractAwareEditor.tsx`

**Props:**

| Prop | Тип | Обязательный | Описание |
|------|-----|:---:|----------|
| `value` | `string` | ✓ | Текущее значение поля |
| `onChange` | `(value: string) => void` | ✓ | Callback при изменении |
| `outputContract` | `ResponseContract \| null` | — | Контракт выходных данных (response schema) |
| `inputContract` | `Record<string, unknown> \| null` | — | JSON Schema входных данных |
| `fieldLabel` | `string` | — | Заголовок модалки (default: "Редактор") |
| `disabled` | `boolean` | — | Заблокирован ли редактор |

**Поведение:**
- Рендерит обычный textarea (или переиспользует существующий Textarea компонент)
- Справа от textarea показывает кнопку-иконку `⌘` (или `↗`) для открытия модалки
- Кнопка видна **только когда `disabled=false`** (edit mode)
- При клике открывает fullscreen/modal split-pane редактор

**Критерии приёмки:**
- [ ] Без контрактов работает как обычный fullscreen textarea
- [ ] С контрактами показывает split-pane layout
- [ ] Кнопка открытия не видна в readonly режиме
- [ ] Значение синхронизируется: изменения в модалке отражаются через onChange
- [ ] ESC / кнопка "Закрыть" закрывает без потери данных (данные уже применены через onChange)

---

### 1.2 `ContractLegend` (правая панель)

**Расположение:** `apps/web/src/shared/ui/ContractAwareEditor/ContractLegend.tsx`

**Props:**

| Prop | Тип | Обязательный | Описание |
|------|-----|:---:|----------|
| `outputContract` | `ResponseContract \| null` | — | Контракт ответа |
| `inputContract` | `Record<string, unknown> \| null` | — | Schema входных данных |
| `coverageMap` | `Map<string, boolean>` | ✓ | Карта покрытия полей |
| `onFieldClick` | `(fieldName: string) => void` | — | Клик по полю → вставка в textarea |

**Секции (сверху вниз):**

1. **Варианты ответа (oneOf)** — если schema содержит `oneOf`
   - Каждый вариант — collapsible блок
   - Заголовок: `variant.title` + badge `kind=value`
   - Внутри: список required полей для этого варианта
   
2. **Поля ответа (output)** — tree-рендер properties из outputContract.schema
   - Каждое поле: `name` + `type` badge + coverage indicator (✓/⚠)
   - Required поля отмечены `*`
   - Conditional поля показывают `when condition` badge
   - Hover/click раскрывает description + enum values
   
3. **Входные данные (input)** — tree-рендер properties из inputContract
   - Аналогично полям ответа, но с заголовком "Что приходит на вход"
   - Coverage не считается (это информационная секция)

4. **Покрытие (summary footer)** — sticky внизу
   - `✓ N/M required полей описано`
   - Список непокрытых полей

**Критерии приёмки:**
- [ ] Корректно рендерит JSON контракт (с variants, fields, nested objects)
- [ ] Корректно рендерит plain_text контракт (criteria/forbidden как чеклист)
- [ ] Рендерит вложенные объекты (nested properties) с отступами
- [ ] Рендерит массивы объектов (`items.properties`) с `[]` suffix
- [ ] Variants (oneOf) сворачиваемые, первый раскрыт по умолчанию
- [ ] Coverage индикаторы обновляются в реальном времени
- [ ] Клик по полю вызывает `onFieldClick`
- [ ] При отсутствии контракта секция не рендерится

---

### 1.3 `useLiveCoverage` (хук)

**Расположение:** `apps/web/src/shared/ui/ContractAwareEditor/useLiveCoverage.ts`

**Сигнатура:**
```ts
function useLiveCoverage(
  text: string,
  outputContract: ResponseContract | null,
): {
  coverageMap: Map<string, boolean>;
  coveredCount: number;
  totalRequired: number;
  uncoveredFields: string[];
}
```

**Логика:**
1. Извлекает ВСЕ property names из schema
2. Фильтрует до "trackable" полей:
   - required поля (из schema.required + oneOf[].required)
   - conditional поля (имеющие x_when)
   - НЕ отслеживает: type-only поля без semantic значения
3. Для каждого trackable поля проверяет `text.toLowerCase().includes(field.toLowerCase())`
4. Возвращает Map + счётчики

**Критерии приёмки:**
- [ ] Debounce 150ms на пересчёт при вводе текста
- [ ] Учитывает только required + conditional поля
- [ ] Case-insensitive matching
- [ ] Корректно работает с пустым текстом (все uncovered)
- [ ] Корректно работает без контракта (пустой Map, 0/0)

---

### 1.4 `SchemaTreeRenderer` (вспомогательный)

**Расположение:** `apps/web/src/shared/ui/ContractAwareEditor/SchemaTreeRenderer.tsx`

**Назначение:** Рекурсивный рендер JSON Schema properties в виде дерева.

**Props:**

| Prop | Тип | Описание |
|------|-----|----------|
| `schema` | `Record<string, unknown>` | JSON Schema (или sub-schema) |
| `coverageMap` | `Map<string, boolean>` | Карта покрытия |
| `basePath` | `string` | Текущий путь (для nested: "facts[].scope") |
| `depth` | `number` | Глубина вложенности (для отступов) |
| `onFieldClick` | `(field: string) => void` | Callback клика |

**Рендер одного поля:**
```
[indent] name* ─── type [enum: a | b | c]  [when condition]  ✓/⚠
              └─ description (tooltip or inline)
```

**Критерии приёмки:**
- [ ] Рекурсивно обходит nested objects (schema.properties → sub.properties)
- [ ] Рендерит array items (schema.items.properties) с `[]` suffix
- [ ] Показывает enum values inline (до 5 значений, иначе tooltip)
- [ ] Показывает x_when как badge
- [ ] Max depth = 4 (защита от бесконечной рекурсии)
- [ ] Clickable field names

---

## 2. Стили

**Расположение:** `apps/web/src/shared/ui/ContractAwareEditor/ContractAwareEditor.module.css`

### Layout модалки:
```
.overlay        — fullscreen overlay (z-index: 1000, backdrop blur)
.modal          — centered container (max-width: 1200px, max-height: 90vh)
.header         — заголовок + кнопка закрытия
.body           — flex row, split-pane
.editorPane     — left, flex: 1, min-width: 400px
.legendPane     — right, width: 360px, border-left, overflow-y: auto
.footer         — sticky bottom, coverage summary + кнопки
```

### Критерии к стилям:
- [ ] Использует CSS variables из существующей темы (--bg-primary, --border-color, etc.)
- [ ] Responsive: на экранах < 900px легенда уходит в tab/drawer снизу
- [ ] Textarea занимает всю высоту editorPane
- [ ] legendPane скроллится независимо от editorPane
- [ ] Анимация открытия/закрытия (opacity + scale, 150ms)

---

## 3. Интеграция (будет отдельно)

### 3.1 Кнопка-триггер

В существующем компоненте `Textarea` (или рядом с Block field type=textarea):
- Добавляется иконка-кнопка справа-сверху от textarea
- Видна только в edit mode
- При клике: открывает `ContractAwareEditor` модалку

### 3.2 Передача контрактов

Компоненты-потребители (OrchestrationPage, AgentVersionPage, etc.) передают:
- `outputContract` — из `role.response_contract`
- `inputContract` — из бэкенда (TODO: endpoint или static schema)

### 3.3 Места подключения (примеры)

| Страница | Поле | outputContract | inputContract |
|----------|------|----------------|---------------|
| OrchestrationPage / Planner | rules | planner contract | PlannerInput schema |
| OrchestrationPage / Planner | safety | planner contract | null |
| OrchestrationPage / Synthesizer | rules | synthesizer contract | SynthesizerInput schema |
| OrchestrationPage / FactExtractor | rules | fact_extractor contract | null |
| AgentVersionPage | system_prompt | agent contract (if any) | null |

---

## 4. Порядок реализации

| # | Задача | Зависимости |
|---|--------|-------------|
| 1 | `useLiveCoverage` хук | — |
| 2 | `SchemaTreeRenderer` компонент | — |
| 3 | `ContractLegend` компонент | 1, 2 |
| 4 | `ContractAwareEditor` модалка | 3 |
| 5 | CSS модуль | 4 |
| 6 | Barrel export + index.ts | 4, 5 |
| 7 | Подключение в OrchestrationPage | 6 |

---

## 5. Ограничения и edge cases

- **Нет контрактов** → модалка открывается как fullscreen textarea без правой панели
- **plain_text контракт** → легенда показывает criteria как чеклист, forbidden как warnings
- **Очень большая schema (>30 полей)** → виртуализация не нужна, достаточно scroll
- **inputContract** — опциональная информационная секция, не влияет на coverage
- **Nested arrays/objects** → дерево с отступами, max depth 4
- **Пустые rules** → все trackable поля показаны как ⚠ uncovered

---

## 6. Файловая структура

```
apps/web/src/shared/ui/ContractAwareEditor/
├── index.ts                        — barrel export
├── ContractAwareEditor.tsx         — главный компонент (модалка + trigger button)
├── ContractAwareEditor.module.css  — стили
├── ContractLegend.tsx              — правая панель с секциями
├── SchemaTreeRenderer.tsx          — рекурсивный рендер schema
└── useLiveCoverage.ts              — хук real-time coverage
```
