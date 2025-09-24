# План действий по тестированию ML Portal

## 🎯 Цель

Этот документ содержит конкретный план действий для достижения полного покрытия тестами ML Portal. Используйте этот план как пошаговое руководство.

## 📊 Текущее состояние

- ✅ **288 unit тестов проходят** (79% успешности)
- ❌ **73 теста требуют исправлений** (21% неудач)
- ⏭️ **4 теста пропускаются**
- 📈 **Цель**: 95%+ успешность, 90%+ покрытие кода

## 🚀 План действий

### Этап 1: Исправление существующих тестов (Приоритет: ВЫСОКИЙ)

#### 1.1 Admin Router (14 тестов)
**Файл**: `apps/api/tests/unit/api/test_admin_router.py`
**Проблемы**: Моки возвращают Mock объекты вместо реальных данных
**Решение**:
```python
# Исправить моки для возврата словарей вместо Mock объектов
mock_user = {
    "id": "user123",
    "login": "testuser", 
    "email": "test@example.com",
    "role": "reader"
}
```

#### 1.2 Chats Router (12 тестов)
**Файл**: `apps/api/tests/unit/api/test_chats_router.py`
**Проблемы**: Аналогичные проблемы с моками
**Решение**: Настроить моки аналогично Admin Router

#### 1.3 Base Repository (10 тестов)
**Файл**: `apps/api/tests/unit/repositories/test_base_repository.py`
**Проблемы**: Моки не настроены правильно
**Решение**: Добавить правильные specs для моков

### Этап 2: Создание новых API Router тестов (Приоритет: ВЫСОКИЙ)

#### 2.1 Auth Router
**Файл**: `apps/api/tests/unit/api/test_auth_router.py`
**Endpoints для тестирования**:
- `POST /auth/login` - вход в систему
- `POST /auth/logout` - выход из системы
- `POST /auth/refresh` - обновление токена
- `GET /auth/me` - информация о пользователе

**Тестовые случаи** (8 тестов):
```python
def test_login_success(self):
def test_login_invalid_credentials(self):
def test_login_user_not_found(self):
def test_logout_success(self):
def test_refresh_token_success(self):
def test_refresh_token_invalid(self):
def test_get_me_success(self):
def test_get_me_unauthorized(self):
```

#### 2.2 Users Router
**Файл**: `apps/api/tests/unit/api/test_users_router.py`
**Endpoints для тестирования**:
- `GET /users/` - список пользователей
- `GET /users/{user_id}` - информация о пользователе
- `PUT /users/{user_id}` - обновление пользователя
- `DELETE /users/{user_id}` - удаление пользователя

**Тестовые случаи** (8 тестов):
```python
def test_get_users_success(self):
def test_get_users_pagination(self):
def test_get_user_success(self):
def test_get_user_not_found(self):
def test_update_user_success(self):
def test_update_user_not_found(self):
def test_delete_user_success(self):
def test_delete_user_not_found(self):
```

#### 2.3 Health Router
**Файл**: `apps/api/tests/unit/api/test_health_router.py`
**Endpoints для тестирования**:
- `GET /health` - проверка здоровья системы
- `GET /health/db` - проверка БД
- `GET /health/redis` - проверка Redis
- `GET /health/s3` - проверка S3

**Тестовые случаи** (8 тестов):
```python
def test_health_all_services_up(self):
def test_health_db_down(self):
def test_health_redis_down(self):
def test_health_s3_down(self):
def test_health_db_check_success(self):
def test_health_redis_check_success(self):
def test_health_s3_check_success(self):
def test_health_multiple_services_down(self):
```

### Этап 3: Создание Service тестов (Приоритет: СРЕДНИЙ)

#### 3.1 Auth Service
**Файл**: `apps/api/tests/unit/services/test_auth_service.py`
**Методы для тестирования**:
- `authenticate_user(login, password)`
- `create_access_token(user_id)`
- `verify_token(token)`
- `refresh_token(refresh_token)`

**Тестовые случаи** (8 тестов):
```python
def test_authenticate_user_success(self):
def test_authenticate_user_invalid_password(self):
def test_authenticate_user_not_found(self):
def test_create_access_token_success(self):
def test_verify_token_success(self):
def test_verify_token_invalid(self):
def test_refresh_token_success(self):
def test_refresh_token_invalid(self):
```

#### 3.2 Admin Service
**Файл**: `apps/api/tests/unit/services/test_admin_service.py`
**Методы для тестирования**:
- `create_user(user_data)`
- `update_user(user_id, user_data)`
- `delete_user(user_id)`
- `get_user_stats(user_id)`
- `search_users(query)`

**Тестовые случаи** (10 тестов):
```python
def test_create_user_success(self):
def test_create_user_validation_error(self):
def test_update_user_success(self):
def test_update_user_not_found(self):
def test_delete_user_success(self):
def test_delete_user_not_found(self):
def test_get_user_stats_success(self):
def test_get_user_stats_not_found(self):
def test_search_users_success(self):
def test_search_users_empty_result(self):
```

#### 3.3 Chats Service
**Файл**: `apps/api/tests/unit/services/test_chats_service.py`
**Методы для тестирования**:
- `create_chat(chat_data)`
- `get_chat(chat_id)`
- `update_chat(chat_id, chat_data)`
- `delete_chat(chat_id)`
- `add_message(chat_id, message_data)`
- `get_messages(chat_id, limit, offset)`

**Тестовые случаи** (12 тестов):
```python
def test_create_chat_success(self):
def test_get_chat_success(self):
def test_get_chat_not_found(self):
def test_update_chat_success(self):
def test_update_chat_not_found(self):
def test_delete_chat_success(self):
def test_delete_chat_not_found(self):
def test_add_message_success(self):
def test_add_message_chat_not_found(self):
def test_get_messages_success(self):
def test_get_messages_pagination(self):
def test_get_messages_chat_not_found(self):
```

#### 3.4 Analyze Service
**Файл**: `apps/api/tests/unit/services/test_analyze_service.py`
**Методы для тестирования**:
- `upload_document(file_data)`
- `process_document(document_id)`
- `get_document(document_id)`
- `delete_document(document_id)`
- `search_documents(query)`

**Тестовые случаи** (10 тестов):
```python
def test_upload_document_success(self):
def test_upload_document_invalid_format(self):
def test_process_document_success(self):
def test_process_document_not_found(self):
def test_get_document_success(self):
def test_get_document_not_found(self):
def test_delete_document_success(self):
def test_delete_document_not_found(self):
def test_search_documents_success(self):
def test_search_documents_empty_result(self):
```

#### 3.5 Clients
**Файл**: `apps/api/tests/unit/services/test_clients.py`
**Методы для тестирования**:
- `qdrant_search(query, filters)`
- `s3_upload(file_data, bucket, key)`
- `s3_download(bucket, key)`
- `s3_delete(bucket, key)`

**Тестовые случаи** (8 тестов):
```python
def test_qdrant_search_success(self):
def test_qdrant_search_no_results(self):
def test_s3_upload_success(self):
def test_s3_upload_error(self):
def test_s3_download_success(self):
def test_s3_download_not_found(self):
def test_s3_delete_success(self):
def test_s3_delete_not_found(self):
```

### Этап 4: Создание Repository тестов (Приоритет: СРЕДНИЙ)

#### 4.1 Users Repository
**Файл**: `apps/api/tests/unit/repositories/test_users_repo.py`
**Методы для тестирования**:
- `create(user_data)`
- `get_by_id(user_id)`
- `get_by_login(login)`
- `get_by_email(email)`
- `update(user_id, user_data)`
- `delete(user_id)`
- `search(query)`

**Тестовые случаи** (14 тестов):
```python
def test_create_success(self):
def test_create_duplicate_login(self):
def test_get_by_id_success(self):
def test_get_by_id_not_found(self):
def test_get_by_login_success(self):
def test_get_by_login_not_found(self):
def test_get_by_email_success(self):
def test_get_by_email_not_found(self):
def test_update_success(self):
def test_update_not_found(self):
def test_delete_success(self):
def test_delete_not_found(self):
def test_search_success(self):
def test_search_empty_result(self):
```

#### 4.2 Chats Repository
**Файл**: `apps/api/tests/unit/repositories/test_chats_repo.py`
**Методы для тестирования**:
- `create_chat(chat_data)`
- `get_chat(chat_id)`
- `update_chat(chat_id, chat_data)`
- `delete_chat(chat_id)`
- `add_message(chat_id, message_data)`
- `get_messages(chat_id, limit, offset)`

**Тестовые случаи** (12 тестов):
```python
def test_create_chat_success(self):
def test_get_chat_success(self):
def test_get_chat_not_found(self):
def test_update_chat_success(self):
def test_update_chat_not_found(self):
def test_delete_chat_success(self):
def test_delete_chat_not_found(self):
def test_add_message_success(self):
def test_add_message_chat_not_found(self):
def test_get_messages_success(self):
def test_get_messages_pagination(self):
def test_get_messages_chat_not_found(self):
```

#### 4.3 RAG Repository
**Файл**: `apps/api/tests/unit/repositories/test_rag_repo.py`
**Методы для тестирования**:
- `create_document(document_data)`
- `get_document(document_id)`
- `update_document(document_id, document_data)`
- `delete_document(document_id)`
- `search_documents(query, filters)`

**Тестовые случаи** (10 тестов):
```python
def test_create_document_success(self):
def test_get_document_success(self):
def test_get_document_not_found(self):
def test_update_document_success(self):
def test_update_document_not_found(self):
def test_delete_document_success(self):
def test_delete_document_not_found(self):
def test_search_documents_success(self):
def test_search_documents_with_filters(self):
def test_search_documents_empty_result(self):
```

### Этап 5: Создание Model тестов (Приоритет: НИЗКИЙ)

#### 5.1 User Models
**Файл**: `apps/api/tests/unit/models/test_user_models.py`
**Модели для тестирования**:
- `User` - основная модель пользователя
- `UserCreate` - схема создания
- `UserUpdate` - схема обновления
- `UserResponse` - схема ответа

**Тестовые случаи** (12 тестов):
```python
def test_user_creation_success(self):
def test_user_validation_error(self):
def test_user_create_schema(self):
def test_user_create_validation_error(self):
def test_user_update_schema(self):
def test_user_update_validation_error(self):
def test_user_response_schema(self):
def test_user_email_validation(self):
def test_user_password_validation(self):
def test_user_role_validation(self):
def test_user_serialization(self):
def test_user_deserialization(self):
```

#### 5.2 Chat Models
**Файл**: `apps/api/tests/unit/models/test_chat_models.py`
**Модели для тестирования**:
- `Chat` - основная модель чата
- `Message` - модель сообщения
- `ChatCreate` - схема создания чата
- `MessageCreate` - схема создания сообщения

**Тестовые случаи** (10 тестов):
```python
def test_chat_creation_success(self):
def test_chat_validation_error(self):
def test_message_creation_success(self):
def test_message_validation_error(self):
def test_chat_create_schema(self):
def test_message_create_schema(self):
def test_chat_serialization(self):
def test_message_serialization(self):
def test_chat_message_relationship(self):
def test_message_type_validation(self):
```

### Этап 6: Создание Core тестов (Приоритет: НИЗКИЙ)

#### 6.1 Config
**Файл**: `apps/api/tests/unit/core/test_config.py`
**Компоненты для тестирования**:
- `Settings` - основные настройки
- `DatabaseSettings` - настройки БД
- `RedisSettings` - настройки Redis
- `S3Settings` - настройки S3

**Тестовые случаи** (8 тестов):
```python
def test_settings_creation_success(self):
def test_settings_validation_error(self):
def test_database_settings_success(self):
def test_redis_settings_success(self):
def test_s3_settings_success(self):
def test_settings_default_values(self):
def test_settings_environment_override(self):
def test_settings_validation_rules(self):
```

#### 6.2 Database
**Файл**: `apps/api/tests/unit/core/test_database.py`
**Компоненты для тестирования**:
- `get_db()` - получение сессии БД
- `init_db()` - инициализация БД
- `close_db()` - закрытие соединения

**Тестовые случаи** (6 тестов):
```python
def test_get_db_success(self):
def test_get_db_connection_error(self):
def test_init_db_success(self):
def test_init_db_error(self):
def test_close_db_success(self):
def test_close_db_error(self):
```

## 📊 Ожидаемые результаты

### После Этапа 1 (Исправление существующих)
- ✅ **300+ unit тестов проходят** (85%+ успешности)
- ❌ **~40 тестов требуют исправлений**
- 📈 **Улучшение**: +12 тестов, +6% успешности

### После Этапа 2 (Новые API Router тесты)
- ✅ **350+ unit тестов проходят** (90%+ успешности)
- 📈 **Добавлено**: 50+ новых тестов

### После Этапа 3 (Service тесты)
- ✅ **450+ unit тестов проходят** (95%+ успешности)
- 📈 **Добавлено**: 100+ новых тестов

### После Этапа 4 (Repository тесты)
- ✅ **550+ unit тестов проходят** (98%+ успешности)
- 📈 **Добавлено**: 100+ новых тестов

### После Этапа 5-6 (Model и Core тесты)
- ✅ **600+ unit тестов проходят** (99%+ успешности)
- 📈 **Добавлено**: 50+ новых тестов
- 🎯 **Цель достигнута**: 90%+ покрытие кода

## 🚀 Команды для выполнения

```bash
# Этап 1: Исправление существующих тестов
cd /Users/evgeniyboldov/Git/ml-portal
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/api/test_admin_router.py -v
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/api/test_chats_router.py -v
docker-compose -f docker-compose.test.yml run --rm backend-test pytest tests/unit/repositories/test_base_repository.py -v

# Этап 2: Создание новых API Router тестов
# Создать файлы:
# - tests/unit/api/test_auth_router.py
# - tests/unit/api/test_users_router.py  
# - tests/unit/api/test_health_router.py

# Этап 3: Создание Service тестов
# Создать файлы:
# - tests/unit/services/test_auth_service.py
# - tests/unit/services/test_admin_service.py
# - tests/unit/services/test_chats_service.py
# - tests/unit/services/test_analyze_service.py
# - tests/unit/services/test_clients.py

# Проверка покрытия
docker-compose -f docker-compose.test.yml run --rm backend-test pytest --cov=app tests/unit/ --cov-report=html
```

## 📋 Чек-лист выполнения

### Для каждого этапа:
- [ ] Изучить код компонента
- [ ] Создать тест файл по шаблону
- [ ] Написать тесты для всех методов/endpoints
- [ ] Запустить тесты
- [ ] Исправить ошибки
- [ ] Проверить покрытие
- [ ] Документировать результаты

### Критерии готовности:
- [ ] Все тесты проходят
- [ ] Покрытие кода > 80%
- [ ] Время выполнения < 30 секунд
- [ ] Тесты изолированы и детерминированы
- [ ] Документация обновлена

---

**Последнее обновление**: 2024-01-15
**Статус**: Готов к выполнению
**Ответственный**: AI Assistant
