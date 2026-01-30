# RBAC система

## Обзор

Система контроля доступа на основе ролей и scope-based permissions.

## Роли пользователей

| Роль | Описание | Права |
|------|----------|-------|
| `reader` | Только просмотр | Чтение данных своего тенанта |
| `editor` | Редактор | Чтение + редактирование данных |
| `admin` | Администратор | Полный доступ к системе |
| `tenant_admin` | Админ тенанта | Управление своим тенантом |

## Scope-based Permissions

### Иерархия
```
Default (глобальные) → Tenant (департамент) → User (индивидуальные)
```

### Приоритет резолва
```
User > Tenant > Default
```

Если на уровне User есть явное значение — используется оно.
Иначе проверяется Tenant, затем Default.

### PermissionSet

Хранит права доступа к инструментам и агентам.

```python
class PermissionSet:
    id: UUID
    scope: str  # 'default' | 'tenant' | 'user'
    tenant_id: UUID | None  # для scope='tenant'
    user_id: UUID | None    # для scope='user'
    instance_permissions: dict[str, str]  # slug → 'allowed'|'denied'|'undefined'
    agent_permissions: dict[str, str]     # slug → 'allowed'|'denied'|'undefined'
```

### Значения permissions

| Значение | Описание | Доступно в scope |
|----------|----------|------------------|
| `allowed` | Явно разрешено | default, tenant, user |
| `denied` | Явно запрещено | default, tenant, user |
| `undefined` | Наследуется от родителя | tenant, user |

**Важно**: в Default scope не может быть `undefined` — это финальный fallback.

## Credential Resolution

### CredentialSet

Хранит зашифрованные учётные данные для Tool Instance.

```python
class CredentialSet:
    id: UUID
    scope: str  # 'default' | 'tenant' | 'user'
    tenant_id: UUID | None
    user_id: UUID | None
    tool_instance_id: UUID
    encrypted_payload: str  # AES-256 encrypted JSON
    is_default: bool  # default credentials for this scope
```

### Стратегии резолва

| Стратегия | Порядок поиска |
|-----------|----------------|
| `user_only` | Только User scope |
| `tenant_only` | Только Tenant scope |
| `default_only` | Только Default scope |
| `prefer_user` | User → Tenant → Default |
| `prefer_tenant` | Tenant → User → Default |
| `any` | User → Tenant → Default (первый найденный) |

## Автоматическое добавление

### Новые агенты
При создании агента автоматически добавляется в Default PermissionSet как `denied`.

### Новые коллекции
При создании коллекции:
1. Создаётся Tool Instance (type=local)
2. Добавляется в Default PermissionSet как `denied`

## API Endpoints

### Permissions
- `GET /admin/permissions` — список PermissionSet
- `GET /admin/permissions/{id}` — детали
- `POST /admin/permissions` — создание
- `PUT /admin/permissions/{id}` — обновление
- `DELETE /admin/permissions/{id}` — удаление
- `GET /admin/permissions/effective` — эффективные права для user/tenant

### Credentials
- `GET /admin/credentials` — список CredentialSet
- `POST /admin/credentials` — создание
- `PUT /admin/credentials/{id}` — обновление
- `DELETE /admin/credentials/{id}` — удаление

## Примеры использования

### Проверка доступа к инструменту

```python
async def check_instance_permission(
    self,
    instance_slug: str,
    user_id: UUID,
    tenant_id: UUID
) -> bool:
    effective = await self.resolve_permissions(user_id, tenant_id)
    return effective.instance_permissions.get(instance_slug, False)
```

### Резолв credentials

```python
async def resolve_credentials(
    self,
    instance_id: UUID,
    user_id: UUID,
    tenant_id: UUID,
    strategy: str = 'any'
) -> CredentialSet | None:
    if strategy == 'user_only':
        return await self.repo.get_by_scope(instance_id, 'user', user_id=user_id)
    
    if strategy == 'prefer_user':
        creds = await self.repo.get_by_scope(instance_id, 'user', user_id=user_id)
        if creds:
            return creds
        creds = await self.repo.get_by_scope(instance_id, 'tenant', tenant_id=tenant_id)
        if creds:
            return creds
        return await self.repo.get_by_scope(instance_id, 'default')
    
    # ... other strategies
```

## UI компоненты

### RbacRulesEditor
Переиспользуемый компонент для редактирования прав.

- Табы: Агенты / Инстансы
- Поиск и фильтрация
- Переключение статуса кликом
- Поддержка всех scope

### Интеграция
- `DefaultsPage` — редактирование default permissions
- `UserEditorPage` — индивидуальные права пользователя
- `TenantEditorPage` — права тенанта
