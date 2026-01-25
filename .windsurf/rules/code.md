---
trigger: always_on
---

# Code Quality Rules

## Общие принципы

1. **Чистота кода**: Не оставляй мусор в виде легаси компонентов и пустых файлов
2. **Ветвление**: Рефакторинг не делаем в main ветке, создаем ветку, меняем код, мержим в main по завершению и удаляем ветку
3. **Документация**: Обновляй документацию при изменении архитектуры
4. **Тестирование**: Пиши тесты для новой функциональности

## Git Workflow

### Naming Branches
- `feature/description` — новая функциональность
- `refactor/description` — рефакторинг
- `fix/description` — исправление бага
- `docs/description` — обновление документации

### Commit Messages
```
type(scope): short description

Longer description if needed

Fixes #123
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

## Code Review Checklist

### Backend
- [ ] Все методы асинхронные
- [ ] Полная типизация
- [ ] Нет hardcoded значений
- [ ] Scope isolation соблюден
- [ ] Тесты написаны
- [ ] Миграция создана (если нужно)
- [ ] Документация обновлена

### Frontend
- [ ] Используется DataTable для таблиц
- [ ] Query keys через factory
- [ ] CSS Modules (не inline styles)
- [ ] Компоненты из shared/ui
- [ ] Accessibility (aria-*, keyboard)
- [ ] Тесты написаны
- [ ] Responsive design

## Performance

### Backend
- Используй `select_related` для FK
- Добавляй индексы на часто используемые колонки
- Кэшируй тяжелые запросы (Redis)
- Используй `asyncio.gather` для параллельных запросов

### Frontend
- Lazy load страниц
- Memo для тяжелых компонентов
- Virtual scrolling для больших списков
- Debounce для поиска

## Security

### Backend
- Всегда проверяй tenant_id
- Шифруй креды через CryptoService
- Валидируй input через Pydantic
- Логируй все admin actions

### Frontend
- Access token в памяти (не localStorage)
- Refresh token в httpOnly cookie
- Валидация на клиенте + сервере
- Sanitize user input

## Deprecation Policy

### Удаление функциональности
1. Пометить как deprecated в коде
2. Добавить warning в логи
3. Обновить документацию
4. Удалить через 2 релиза

### Изменение API
1. Создать новую версию endpoint
2. Deprecated старую версию
3. Обновить клиентов
4. Удалить старую версию через 3 релиза

## Documentation

### Обязательные документы
- `PRODUCT_VISION.md` — видение продукта
- `DATA_MODEL.md` — модели данных
- `BACKEND_ARCHITECTURE.md` — архитектура бэкенда
- `FRONTEND_ARCHITECTURE.md` — архитектура фронтенда
- `ADMIN_STRUCTURE.md` — структура админки
- `TODO.md` — roadmap и задачи

### Обновление документации
При изменении:
- Моделей → обновить `DATA_MODEL.md`
- API → обновить OpenAPI spec
- UI → обновить `ADMIN_STRUCTURE.md`
- Архитектуры → обновить соответствующий doc

## Monitoring

### Metrics
- Количество запросов к агентам
- Latency LLM/Tool calls
- Ошибки по типам
- Health status инстансов

### Logging
- Structured logging (JSON)
- Correlation ID для трейсинга
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Alerting
- Health check failures
- High error rate (>5%)
- High latency (p95 > 5s)
- Disk space < 10%