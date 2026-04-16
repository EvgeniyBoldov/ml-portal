# Integration Tests Suite

Полный набор интеграционных тестов для ML Portal.

## Архитектура

Тесты построены по принципу **полного lifecycle**:
1. Создание сущностей через API
2. Использование (чат с триаджем/планером)
3. Очистка (удаление в обратном порядке)

## Запуск

### Быстрый запуск (в контейнерах)

```bash
# Поднять тестовую инфраструктуру
make test-integration-up

# Запустить тесты
docker-compose -f docker-compose.test.yml exec api-test pytest tests/integration/ -v --tb=short

# Остановить инфраструктуру
make test-integration-down
```

### Локальный запуск (для разработки)

```bash
# Установить тестовые зависимости
cd apps/api
pip install -r requirements-test.txt

# Скопировать и настроить .env.test
cp .env.test .env.test.local
# Отредактировать .env.test.local с вашими токенами

# Запустить тесты
pytest tests/integration/ -v --tb=short
```

## Тестовые сценарии

| # | Файл | Сценарий |
|---|------|----------|
| 01 | `test_01_tenants_and_users.py` | Tenant + User CRUD |
| 02 | `test_02_connectors_and_models.py` | Models + MCP + Data instances |
| 03 | `test_03_collections.py` | SQL + Netbox + RAG collections |
| 04 | `test_04_tools_and_agents.py` | Rescan tools + Agent versions + Bindings |
| 05 | `test_05_orchestration.py` | Triage + Planner + Memory roles |
| 06 | `test_06_rbac.py` | RBAC rules for data access |
| 07 | `test_07_chat_flow.py` | Chat + Message streaming |
| 08 | `test_08_table_collection_with_vectors.py` | Vector-enabled table collection |
| 99 | `test_99_cleanup.py` | Cleanup all entities |

## Конфигурация

### .env.test

Создайте `apps/api/.env.test.local` (не коммитится):

```env
# LLM (Groq)
GROQ_API_KEY=gsk_...

# Netbox (demo.netbox.dev)
NETBOX_API_TOKEN=your_daily_token_here
```

### Токен Netbox

Токен для demo.netbox.dev генерируется каждый день:
1. Зайдите на https://demo.netbox.dev/
2. Admin → API Tokens → Add Token
3. Скопируйте в `.env.test.local`

## Архитектура тестов

### Фикстуры (conftest.py)

- `client` — httpx.AsyncClient с ASGI transport
- `admin_token` — JWT токен админа (admin/admin123)
- `admin_headers` — заголовки с авторизацией
- `test_tenant` — созданный тестовый тенант
- `test_user` — созданный тестовый пользователь
- `resource_tracker` — трекер для cleanup

### Порядок выполнения

Тесты используют `pytest-order` для гарантированного порядка:
- `order(1)` → `order(8)` — создание и тестирование
- `order(99)` — cleanup (всегда последний)

## Добавление новых тестов

```python
"""
Test XX: Description
"""
import pytest

pytestmark = pytest.mark.order(N)  # Укажите порядок

@pytest.mark.asyncio
async def test_something(client, admin_headers):
    """Test description"""
    response = await client.post(...)
    assert response.status_code == 201
```

## Troubleshooting

### Тесты падают с 401
Проверьте что миграция `0144_ensure_default_admin.py` применена и admin существует.

### LLM не отвечает
Проверьте `GROQ_API_KEY` в `.env.test.local`.

### Netbox недоступен
Проверьте `NETBOX_API_TOKEN` — он действует 1 день.

### Ошибки SQL
Убедитесь что миграции применены: `alembic upgrade head`
