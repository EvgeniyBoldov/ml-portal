# Runtime Refactor E2E Tests

Комплексные E2E тесты для валидации рефакторинга Agent Runtime.

## Структура тестов

### Backend тесты
- `test_runtime_refactor.py` — Основные тесты нового planner-driven runtime
- `test_runtime_performance.py` — Тесты производительности и масштабируемости
- `test_runtime_regression.py` — Regression тесты и проверка удаления legacy кода

### Frontend тесты
- `runtime-refactor.spec.ts` — E2E тесты UI через Playwright

### Фикстуры
- `runtime_fixtures.py` — Backend фикстуры для тестовых данных
- `fixtures.ts` — Frontend хелперы и тестовые данные

## Запуск тестов

### Все тесты (Docker - Рекомендуется)
```bash
# Запуск всех runtime тестов в Docker контейнерах
make test-runtime

# Или напрямую
python tests/e2e/run_runtime_tests.py
```

### Только backend (в Docker)
```bash
# Запуск backend тестов в контейнере
docker-compose -f docker-compose.test.yml exec api-test python -m pytest tests/e2e/test_runtime_refactor.py -v
docker-compose -f docker-compose.test.yml exec api-test python -m pytest tests/e2e/test_runtime_performance.py -v
docker-compose -f docker-compose.test.yml exec api-test python -m pytest tests/e2e/test_runtime_regression.py -v
```

### Только frontend (в Docker)
```bash
# Запуск frontend тестов в контейнере
docker-compose -f docker-compose.test.yml exec frontend-test npx playwright test e2e-tests/runtime-refactor.spec.ts
```

### Локальный запуск (без Docker)
```bash
# Backend тесты (требует запущенные сервисы)
cd apps/api
python -m pytest tests/e2e/test_runtime_refactor.py -v
python -m pytest tests/e2e/test_runtime_performance.py -v
python -m pytest tests/e2e/test_runtime_regression.py -v

# Frontend тесты
cd apps/web
npx playwright test e2e-tests/runtime-refactor.spec.ts
```

### Coverage отчет
```bash
# В Docker контейнере
docker-compose -f docker-compose.test.yml exec api-test python -m pytest tests/e2e/test_runtime_refactor.py --cov=app.agents --cov-report=html

# Локально
cd apps/api
python -m pytest tests/e2e/test_runtime_refactor.py --cov=app.agents --cov-report=html
```

## Что тестируется

### Core Runtime Functionality
- ✅ Planner loop execution
- ✅ Tool call handling
- ✅ Policy limits enforcement
- ✅ Error handling and recovery
- ✅ Event streaming

### New Features
- ✅ Conversation summaries integration
- ✅ Planner context with conversation history
- ✅ RunSession helper functionality

### Legacy Removal
- ✅ No `run()` method
- ✅ No `run_with_request()` method
- ✅ No `AgentProfile` class
- ✅ No `RunContext`/`RunStep` classes
- ✅ Sandbox uses `run_with_planner`

### Performance
- ✅ Response time benchmarks
- ✅ Memory usage stability
- ✅ Concurrent execution
- ✅ Large message handling

### UI/UX
- ✅ Chat interface responsiveness
- ✅ Tool execution indicators
- ✅ Loading states
- ✅ Error messaging

## Тестовые сценарии

### Simple Chat
```python
messages = [{"role": "user", "content": "Hello"}]
# Ожидаемый результат: прямой ответ без tools
```

### Tool Execution
```python
messages = [{"role": "user", "content": "Search for AI"}]
# Ожидаемый результат: tool call + result
```

### Error Handling
```python
messages = [{"role": "user", "content": "This should cause error"}]
# Ожидаемый результат: graceful error handling
```

## Performance Benchmarks

- Simple chat: < 1s
- Tool execution: < 2s
- Concurrent requests: linear scaling
- Memory increase: < 50MB for 20 requests

## Troubleshooting

### Backend тесты
```bash
# Установка зависимостей
pip install pytest pytest-asyncio pytest-mock

# Проблемы с импортами
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
```

### Frontend тесты
```bash
# Установка Playwright
cd apps/web
npm install
npx playwright install

# TypeScript ошибки
npm run type-check
```

### Docker окружение
```bash
# Запуск тестов в контейнере
docker-compose -f docker-compose.test.yml up --build
docker-compose exec api pytest tests/e2e/
```

## Результаты

После успешного прохождения всех тестов:

1. ✅ Runtime рефакторинг корректно работает
2. ✅ Legacy код полностью удален
3. ✅ Производительность не ухудшилась
4. ✅ UI функциональность сохранена
5. ✅ Новые фичи работают как ожидалось

## CI/CD Integration

```yaml
# .github/workflows/runtime-tests.yml
name: Runtime E2E Tests
on: [push, pull_request]
jobs:
  runtime-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Backend Tests
        run: |
          cd apps/api
          python tests/e2e/run_runtime_tests.py
      - name: Run Frontend Tests
        run: |
          cd apps/web
          npx playwright test e2e-tests/runtime-refactor.spec.ts
```

## Следующие шаги

1. Добавить тесты в CI/CD pipeline
2. Настроить автоматические performance бенчмарки
3. Добавить мониторинг production метрик
4. Расширить тесты для edge cases
