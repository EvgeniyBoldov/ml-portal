# Changelog E2E Tests

## 2025-11-06 - Исправления и полное покрытие админки

### Исправленные проблемы API

1. **Импорт LLMClientProtocol**
   - Проблема: Неправильный путь импорта в `chat_stream_service.py`
   - Решение: Изменен путь с `app.adapters.interfaces.llm` на `app.core.http.clients`

2. **IdempotencyManager**
   - Проблема: Класс не существовал
   - Решение: Создан класс `IdempotencyManager` в `app.core.idempotency.py`

3. **Обновление пользователя (500 Error)**
   - Проблема: `onupdate="now()"` передавал строку вместо datetime
   - Решение: Заменено на `onupdate=func.now()` в модели `Users`

4. **Логин пользователя (401 Unauthorized)**
   - Проблема: Несовместимость хеширования - создание использовало bcrypt, а проверка argon2
   - Решение: 
     - Изменен `authenticate_user` на использование `bcrypt.checkpw`
     - Обновлен скрипт `create_default_admin.py` на использование bcrypt
     - Обновлен пароль существующего админа в БД

### Обновленные тесты

1. **Пути эндпоинтов**
   - `/users` → `/admin/users`
   - Метод обновления тенанта: `PATCH` → `PUT`

2. **Структура ответов API**
   - Создание пользователя возвращает `{"user": {...}}`
   - Список пользователей возвращает `{"users": [...]}`
   - Обязательное поле `login` при создании пользователя

3. **Поля данных**
   - `is_admin` → `role` (значения: "reader", "admin")
   - Добавлено поле `login` для авторизации

### Результаты

✅ **11/11 тестов админки прошли успешно**

**Тенанты (5 тестов):**
- ✅ Создание тенанта
- ✅ Список тенантов
- ✅ Получение тенанта по ID
- ✅ Обновление тенанта
- ✅ Удаление тенанта

**Пользователи (6 тестов):**
- ✅ Создание пользователя
- ✅ Список пользователей
- ✅ Получение пользователя по ID
- ✅ Обновление пользователя (роль)
- ✅ Удаление пользователя
- ✅ Логин пользователя

### Файлы изменены

**Backend:**
- `apps/api/src/app/models/user.py` - исправлен onupdate
- `apps/api/src/app/services/users_service.py` - bcrypt для аутентификации
- `apps/api/src/app/services/chat_stream_service.py` - исправлен импорт
- `apps/api/src/app/core/idempotency.py` - добавлен IdempotencyManager
- `infra/scripts/create_default_admin.py` - bcrypt вместо argon2

**Tests:**
- `tests/e2e/conftest.py` - обновлены пути и структура ответов
- `tests/e2e/test_admin_crud.py` - исправлены все тесты под реальное API

### Следующие шаги

- [ ] Тесты чатов (test_chat_flow.py)
- [ ] Тесты RAG (test_rag_flow.py)
- [ ] CI/CD интеграция
