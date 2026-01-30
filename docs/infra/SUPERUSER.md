# Создание суперюзера

## Первый запуск

После применения миграций необходимо создать первого администратора.

## Способ 1: Скрипт

```bash
docker compose exec api python -m app.scripts.create_superuser
```

Скрипт запросит:
- Email
- Пароль
- Имя (опционально)

## Способ 2: Интерактивный

```bash
docker compose exec -it api python
```

```python
import asyncio
from app.core.database import async_session_maker
from app.models import User, Tenant
from app.core.security import get_password_hash
import uuid

async def create_superuser():
    async with async_session_maker() as session:
        # Создаём тенант
        tenant = Tenant(
            id=uuid.uuid4(),
            name="System",
            slug="system",
            is_active=True
        )
        session.add(tenant)
        await session.flush()
        
        # Создаём пользователя
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            hashed_password=get_password_hash("your-password"),
            name="Admin",
            role="admin",
            tenant_id=tenant.id,
            is_active=True
        )
        session.add(user)
        await session.commit()
        
        print(f"Created user: {user.email}")

asyncio.run(create_superuser())
```

## Способ 3: SQL

```bash
docker compose exec postgres psql -U mlportal -d mlportal
```

```sql
-- Создаём тенант
INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'System',
    'system',
    true,
    NOW(),
    NOW()
)
RETURNING id;

-- Используем полученный tenant_id
INSERT INTO users (id, email, hashed_password, name, role, tenant_id, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'admin@example.com',
    '$2b$12$...', -- bcrypt hash пароля
    'Admin',
    'admin',
    '<tenant_id>',
    true,
    NOW(),
    NOW()
);
```

## Генерация bcrypt hash

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hash = pwd_context.hash("your-password")
print(hash)
```

## Роли

| Роль | Описание |
|------|----------|
| `admin` | Полный доступ ко всей системе |
| `tenant_admin` | Управление своим тенантом |
| `editor` | Редактирование данных |
| `reader` | Только просмотр |

## После создания

1. Войти в систему с созданными credentials
2. Создать дополнительные тенанты через админку
3. Создать пользователей для тенантов
4. Настроить default permissions

## Сброс пароля

```bash
docker compose exec api python
```

```python
import asyncio
from app.core.database import async_session_maker
from app.models import User
from app.core.security import get_password_hash
from sqlalchemy import select

async def reset_password(email: str, new_password: str):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User {email} not found")
            return
        
        user.hashed_password = get_password_hash(new_password)
        await session.commit()
        print(f"Password reset for {email}")

asyncio.run(reset_password("admin@example.com", "new-password"))
```
