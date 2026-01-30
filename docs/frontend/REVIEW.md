# Frontend Review List

Список того, что требует рефакторинга или удаления.

## 🔴 Критично

### console.log в production коде

- [ ] `shared/api/http.ts` — убрать console.log
- [ ] `shared/ui/DataTable/DataTable.tsx` — убрать console.log

### Использование `any` (146 мест в 53 файлах)

Топ файлов с `any`:
- [ ] `shared/ui/DataTable/DataTable.tsx` — 12 мест
- [ ] `domains/admin/pages/TenantEditorPage.tsx` — 7 мест
- [ ] `domains/chat/contexts/ChatContext.tsx` — 7 мест
- [ ] `domains/admin/pages/AgentEditorPage.tsx` — 6 мест
- [ ] `domains/admin/pages/PromptEditorPage.tsx` — 6 мест
- [ ] `shared/api/tools.ts` — 6 мест
- [ ] `shared/api/prompts.ts` — 5 мест

### Мусор и дубликаты

- [ ] `shared/components/` — содержит CredentialSetsEditor и PermissionsEditor, возможно дублируют shared/ui
- [ ] `domains/rag/components/StatusModalNew.tsx` — похоже на дубликат StatusModal.tsx
- [ ] Удалить неиспользуемые компоненты
- [ ] Удалить закомментированный код

### Несоответствие паттернам

- [ ] Hardcoded query keys — заменить на `qk.*`
- [ ] Inline styles — перенести в CSS modules
- [ ] Серверные данные в Zustand — перенести в React Query

## 🟡 Важно

### Структура

- [ ] Большие компоненты (>250 строк) — разбить:
  - `domains/admin/pages/AgentEditorPage.tsx`
  - `domains/rag/components/StatusModal.tsx`
  - `domains/chat/components/ChatWindow.tsx`

### Типизация

- [ ] Заменить `any` на конкретные типы
- [ ] Добавить типы для всех props
- [ ] Использовать `unknown` вместо `any` где возможно

### CSS

- [ ] Унифицировать spacing (использовать CSS variables)
- [ ] Удалить дублирующиеся стили
- [ ] Проверить responsive breakpoints

## 🟢 Улучшения

### Accessibility

- [ ] Добавить `aria-*` атрибуты к интерактивным элементам
- [ ] Проверить keyboard navigation
- [ ] Добавить focus indicators

### Performance

- [ ] Добавить `React.memo` для тяжёлых компонентов
- [ ] Проверить лишние re-renders
- [ ] Оптимизировать query invalidation

### Тесты

- [ ] Добавить unit тесты для shared/ui
- [ ] Добавить тесты для hooks
- [ ] Добавить E2E тесты

## Файлы для проверки

| Директория | Проблема |
|------------|----------|
| `shared/components/` | Возможные дубликаты с shared/ui |
| `domains/admin/pages/` | Большие файлы, нужен рефакторинг |
| `app/store/` | Проверить на серверные данные |

## Deprecated код

- [ ] Проверить использование старых API endpoints
- [ ] Удалить неиспользуемые hooks
- [ ] Удалить legacy компоненты

## Конфигурация

- [ ] Удалить `console.log` из production кода
- [ ] Проверить environment variables
- [ ] Обновить ESLint правила

## API Layer

- [ ] Унифицировать error handling
- [ ] Добавить retry логику
- [ ] Проверить типы ответов API
