# E2E Tests для ML Portal

Комплексные end-to-end тесты, работающие через HTTP API с токенами.

## Структура

- `test_admin_crud.py` — CRUD операции для тенантов и пользователей
- `test_chat_flow.py` — CRUD чатов + полный флоу сообщений
- `test_rag_flow.py` — RAG документы: создание, ингест, скачивание

## Установка

```bash
cd tests/e2e
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate на Windows
pip install -r requirements.txt
```

## Конфигурация

Создайте `.env` файл на основе `.env.example`:

```bash
cp .env.example .env
```

Отредактируйте `.env` под ваше окружение:

```env
API_BASE_URL=http://localhost:8000/api/v1
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
```

## Запуск

### Все тесты

```bash
pytest
```

### Конкретный модуль

```bash
pytest test_admin_crud.py
pytest test_chat_flow.py
pytest test_rag_flow.py
```

### Конкретный тест

```bash
pytest test_chat_flow.py::TestChatCRUD::test_create_chat
```

### С подробным выводом

```bash
pytest -v -s
```

### Только быстрые тесты (без RAG)

```bash
pytest -m "not slow"
```

## Требования

- Сервис должен быть запущен (`docker-compose up`)
- Админ-пользователь должен существовать
- Redis должен быть доступен (для идемпотентности)
- Qdrant должен быть доступен (для RAG-тестов)

## Что тестируется

### Админка
- ✅ Создание, чтение, обновление, удаление тенантов
- ✅ Создание, чтение, обновление, удаление пользователей
- ✅ Логин пользователей

### Чаты
- ✅ Создание, чтение, обновление, удаление чатов
- ✅ Обновление имени и тегов
- ✅ Отправка сообщений (с RAG и без)
- ✅ Идемпотентность запросов
- ✅ Пагинация сообщений (keyset)
- ✅ Выбор LLM-модели
- ✅ Авторизация (нельзя получить доступ к чужому чату)

### RAG
- ✅ Создание, чтение, обновление, удаление документов
- ✅ Запуск ингеста
- ✅ Проверка статусов (pending → downloading → processing → completed)
- ✅ Перезапуск неудачного ингеста
- ✅ Скачивание оригинального документа
- ✅ Скачивание канонического документа
- ✅ Поиск в базе знаний

## Troubleshooting

### Тесты падают с 401 Unauthorized

Проверьте, что миграции применены и API стартовал: дефолтный админ создаётся автоматически
через `0002_seed_defaults` + startup `ensure_default_admin`.

```bash
docker compose exec api alembic current
docker compose logs --tail=100 api
```

### Тесты RAG падают с timeout

Увеличьте timeout в `conftest.py`:

```python
self.client = httpx.Client(timeout=60.0)  # было 30.0
```

### Тесты падают с connection refused

Проверьте, что сервис запущен:

```bash
docker-compose ps
curl http://localhost:8000/api/v1/health
```

## CI/CD

Тесты можно запускать в CI:

```yaml
- name: Run E2E tests
  run: |
    cd tests/e2e
    pip install -r requirements.txt
    pytest -v
  env:
    API_BASE_URL: http://api:8000/api/v1
    ADMIN_EMAIL: admin@example.com
    ADMIN_PASSWORD: ${{ secrets.ADMIN_PASSWORD }}
```
