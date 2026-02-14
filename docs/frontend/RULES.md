# Правила разработки Frontend

## 1) Базовые принципы

1. TypeScript strict: без `any` в новом коде.
2. CSS Modules only: без Tailwind/styled-components.
3. Переиспользование важнее нового кода: сначала проверяем `src/shared/ui`.
4. Server state — TanStack Query, UI state — Zustand.
5. Для admin detail/create/edit страниц целевой стандарт: `EntityPageV2` + `Tab`.

## 2) Нейминг и структура файлов

- Список сущностей: `<Entity>ListPage.tsx`
- Одна сущность: `<Entity>Page.tsx`
- Страница версии: `<Entity>VersionPage.tsx`
- `*EditorPage.tsx` — legacy, не использовать в новом коде.
- Компоненты: `PascalCase.tsx`
- Стили компонента: `PascalCase.module.css`
- CSS-классы: `kebab-case`
- Хендлеры: `handle*`
- Булевы переменные: `is*`, `has*`, `can*`, `should*`

## 3) Правила компонентов

1. Если аналог уже есть в `shared/ui` — используем его.
2. Новый компонент создаем только если переиспользуемого блока реально нет.
3. Один компонент = одна ответственность.
4. Если компонент >250 строк, выносим части в subcomponents/hooks.
5. Для админки собираем страницу как конструктор из готовых блоков (`EntityInfoBlock`, `ShortEntityBlock`, `VersionsBlock`, `DataTable`, и т.д.).

## 4) Стилизация

1. Только `*.module.css`.
2. Inline styles — только для динамических значений, которые нельзя выразить классом.
3. Использовать токены из `shared/ui/tokens.css` (`--sp-*`, `--radius-*`, `--font-size-*`).
4. Для новых/обновляемых компонентов использовать переменные:
   - `--bg-primary`
   - `--text-primary`
   - `--border-color`
5. У каждой admin page — свой CSS module. Нельзя импортировать стили другой страницы.

## 5) Data fetching и состояние

### TanStack Query

- Query key только через `qk` (`shared/api/keys.ts`).
- Не хардкодить `['x', 'y']` в компонентах.
- Инвалидация и обновление кэша — через `queryClient` + `qk`.
- Базовые query options:
  - `staleTime: 30_000`
  - `gcTime: 5 * 60_000`
  - `retry: 1`

### Zustand

- Только UI state (drawer, локальные фильтры, selected items).
- Никаких серверных сущностей в store.

### API клиент

- Один HTTP-клиент: `shared/api/http.ts`.
- Access token хранится в памяти.
- Refresh идет через httpOnly cookie.
- Для мутаций использовать idempotency key через клиент.

## 6) Admin pages

Для новых страниц и рефакторинга:

- Использовать `EntityPageV2` и декларативные `Tab`.
- Выбирать layout по задаче:
  - `grid` — обзорные блоки
  - `full` — таблицы/большие списки
  - `single` — формы
  - `custom` — нетипичные случаи

Legacy-страницы на `EntityTabsPage` пока допустимы, но не копируются в новый код.

## 7) Формы и UX

1. Использовать `Input`, `Textarea`, `Select`, `Checkbox`, `Button` из `shared/ui`.
2. Формы — controlled, с полевой и общей валидацией.
3. Большие формы не размещать в modal/drawer: только page-level форма.

## 8) Accessibility

- Icon-only кнопки: обязательный `aria-label`.
- Modal/Drawer/Popover: `Esc` закрывает, фокус возвращается.
- Поля формы: `label` связан с `id`.
- Навигация с клавиатуры должна работать без мыши.

## 9) Порядок импортов

1. React
2. Third-party
3. Shared (`@/shared/*`)
4. Domain (`@/domains/*`)
5. Local (`./*.module.css`)

## 10) Чеклист PR

1. Использованы готовые блоки из `shared/ui`.
2. Нет лишнего кастомного UI при наличии готового компонента.
3. Нет magic numbers в стилях там, где есть токены.
4. Query keys через `qk`; server data не в Zustand.
5. Для новых admin страниц применен `EntityPageV2`.
6. Нейминг файлов/компонентов соответствует правилам.
