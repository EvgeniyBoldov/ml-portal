# Улучшения безопасности ML Portal

## Обзор

Данный документ описывает реализованные улучшения безопасности для ML Portal, включая валидацию паролей, rate limiting, PAT scope validation, и другие меры безопасности.

## 🔐 Валидация паролей

### Политика паролей
- **Минимальная длина**: 12 символов (настраивается через `PASSWORD_MIN_LENGTH`)
- **Обязательные требования**:
  - Заглавные буквы (`PASSWORD_REQUIRE_UPPERCASE=true`)
  - Строчные буквы (`PASSWORD_REQUIRE_LOWERCASE=true`)
  - Цифры (`PASSWORD_REQUIRE_DIGITS=true`)
  - Специальные символы (`PASSWORD_REQUIRE_SPECIAL=true`)

### Хеширование паролей
- **Алгоритм**: Argon2id (через библиотеку `argon2-cffi`)
- **Pepper**: Дополнительная защита через `PASSWORD_PEPPER` (32-символьный случайный ключ)
- **Соль**: Автоматически генерируется для каждого пароля

### Использование
```python
from app.core.security import validate_password_strength, hash_password, verify_password

# Валидация пароля
is_valid, error_msg = validate_password_strength("MyPassword123!")
if not is_valid:
    print(f"Ошибка: {error_msg}")

# Хеширование
password_hash = hash_password("MyPassword123!")

# Проверка
is_correct = verify_password("MyPassword123!", password_hash)
```

## 🎫 PAT (Personal Access Token) Scope Validation

### Поддерживаемые scopes
- **API**: `api:read`, `api:write`, `api:admin`
- **RAG**: `rag:read`, `rag:write`, `rag:admin`
- **Chat**: `chat:read`, `chat:write`, `chat:admin`
- **Users**: `users:read`, `users:write`, `users:admin`

### Иерархия scopes
Высокоуровневые scopes автоматически включают низкоуровневые:
- `api:admin` → `api:read`, `api:write`
- `rag:admin` → `rag:read`, `rag:write`
- `chat:admin` → `chat:read`, `chat:write`
- `users:admin` → `users:read`, `users:write`

### Использование
```python
from app.core.pat_validation import validate_scopes, check_scope_permission

# Валидация scopes
scopes = ["api:admin", "rag:read"]
validated_scopes = validate_scopes(scopes)
# Результат: ["api:admin", "api:read", "api:write", "rag:read"]

# Проверка разрешений
user_scopes = ["api:admin"]
has_permission = check_scope_permission(user_scopes, "api:read")  # True
has_permission = check_scope_permission(user_scopes, "chat:read")  # False
```

## ⏱️ Rate Limiting

### Настроенные лимиты
- **Login**: 10 попыток в минуту (`RATE_LIMIT_LOGIN_ATTEMPTS=10`, `RATE_LIMIT_LOGIN_WINDOW=60`)
- **Password Reset Request**: 5 попыток в 5 минут
- **Password Reset Confirm**: 10 попыток в 5 минут

### Реализация
- Использует Redis для хранения счетчиков
- Учитывает `X-Forwarded-For` заголовок для определения IP клиента
- Автоматически очищает истекшие записи

### Ответ при превышении лимита
```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Try again in 60 seconds.",
  "retry_after": 60
}
```

## 🌐 CORS Configuration

### Настройки
- **Включение**: `CORS_ENABLED=true`
- **Origins**: `CORS_ORIGINS=*` (или список разрешенных доменов)
- **Credentials**: `CORS_ALLOW_CREDENTIALS=false` (по умолчанию)

### Режимы работы
1. **Development**: Разрешены все origins без credentials
2. **Production**: Только указанные origins с credentials

## 💓 SSE Heartbeat

### Функциональность
- Автоматические heartbeat сообщения каждые 30 секунд
- Поддержка настраиваемого интервала
- Обработка ошибок и отключений клиентов

### Формат heartbeat
```json
{
  "type": "heartbeat",
  "timestamp": "2025-01-15T10:30:00.000Z"
}
```

### Использование
```python
from app.api.sse import sse_response, sse_heartbeat_response

# SSE с heartbeat
response = sse_response(data_generator, heartbeat_interval=30)

# Только heartbeat
response = sse_heartbeat_response(heartbeat_interval=30)
```

## 🔑 Password Reset Security

### Безопасность
- **Всегда 200**: Всегда возвращает HTTP 200 для предотвращения enumeration атак
- **TTL токенов**: 60 минут (настраивается)
- **Одноразовые токены**: Токены помечаются как использованные
- **Отзыв refresh токенов**: Все refresh токены отзываются при сбросе пароля

### Rate Limiting
- **Запрос сброса**: 5 попыток в 5 минут
- **Подтверждение сброса**: 10 попыток в 5 минут

## 📝 Audit Logging

### Логируемые действия
- **Пользователи**: создание, обновление, удаление, смена роли
- **Токены**: создание, отзыв PAT токенов
- **Аутентификация**: вход, выход, сброс пароля
- **Административные**: все действия администраторов

### Структура лога
```json
{
  "id": "uuid",
  "ts": "2025-01-15T10:30:00.000Z",
  "actor_user_id": "uuid",
  "action": "USER_CREATED",
  "object_type": "user",
  "object_id": "uuid",
  "meta": {...},
  "ip": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "request_id": "uuid"
}
```

## 🧪 Тестирование

### Запуск тестов безопасности
```bash
# Через Makefile
make test-security

# Напрямую
python backend/scripts/test_security_improvements.py

# Unit тесты
pytest backend/tests/test_security_improvements.py
```

### Покрываемые тесты
- ✅ Валидация паролей (сильные/слабые пароли)
- ✅ Хеширование с pepper
- ✅ PAT scope validation
- ✅ Rate limiting (login, password reset)
- ✅ CORS конфигурация
- ✅ SSE heartbeat
- ✅ Password reset security
- ✅ Audit logging

## ⚙️ Конфигурация

### Переменные окружения
```bash
# Пароли
PASSWORD_PEPPER=your-super-secret-password-pepper
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGITS=true
PASSWORD_REQUIRE_SPECIAL=true

# Rate Limiting
RATE_LIMIT_LOGIN_ATTEMPTS=10
RATE_LIMIT_LOGIN_WINDOW=60

# CORS
CORS_ENABLED=true
CORS_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false

# JWT
JWT_SECRET=your-super-secret-jwt-key
ACCESS_TTL_SECONDS=900
REFRESH_TTL_DAYS=7
REFRESH_ROTATING=true

# Email (опционально)
EMAIL_ENABLED=false
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true
FROM_EMAIL=noreply@ml-portal.local
```

## 🚀 Развертывание

### 1. Обновление миграций
```bash
make run-migrations
```

### 2. Создание суперпользователя
```bash
make create-superuser
```

### 3. Тестирование
```bash
make test-security
```

### 4. Проверка RBAC
```bash
make test-rbac
```

## 🔍 Мониторинг

### Метрики безопасности
- Количество неудачных попыток входа
- Количество заблокированных IP (rate limiting)
- Количество созданных/отозванных PAT токенов
- Количество сбросов паролей

### Логи
- Все административные действия логируются
- Ошибки аутентификации логируются
- Rate limiting события логируются

## 🛡️ Рекомендации по безопасности

### Production
1. **Обязательно установите** `JWT_SECRET` и `PASSWORD_PEPPER`
2. **Настройте CORS** для конкретных доменов
3. **Включите email** для password reset
4. **Настройте мониторинг** rate limiting
5. **Регулярно ротируйте** JWT secrets

### Development
1. Используйте `EMAIL_ENABLED=false` для локальной разработки
2. Rate limiting отключен в тестовом режиме
3. CORS настроен на разрешение всех origins

## 📚 Дополнительные ресурсы

- [OWASP Password Guidelines](https://owasp.org/www-project-authentication-cheat-sheet/)
- [Argon2 Specification](https://github.com/P-H-C/phc-winner-argon2)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Rate Limiting Best Practices](https://cloud.google.com/architecture/rate-limiting-strategies-techniques)
