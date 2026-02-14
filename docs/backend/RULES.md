# Правила разработки Backend

## 1) Базовые принципы

1. Только async/await (sync-слой не добавляем).
2. Полная типизация (`type hints` в сигнатурах и возвращаемых типах).
3. Никаких хардкодов: константы/пороговые значения через config/enum.
4. Multi-tenant изоляция обязательна во всех чтениях/мутациях.
5. Scope-приоритеты:
   - permissions: `User > Tenant > Default`
   - credentials: `User > Tenant > Default`

## 2) Архитектурные границы

- `api/` — валидация, маппинг HTTP-ошибок, зависимости.
- `services/` — бизнес-логика, orchestration, commit policy.
- `repositories/` — только доступ к данным (CRUD/query), без бизнес-логики.

Запрещено:

- бизнес-логика в роутерах;
- commit в репозитории;
- обход service-слоя в API для мутирующих сценариев.

## 3) Транзакции (обязательно)

1. В репозиториях: только `flush()`, без `commit()`.
2. В API-эндпойнтах с `db_session`: после мутации делать `await session.commit()`.
3. В сценариях с `db_uow`: commit делает dependency, руками не дублировать.
4. В воркерах: использовать транзакционный context manager (`worker_transaction`/эквивалент).

## 4) Модели и данные

### Базовые поля модели

Каждая сущность должна иметь:

- `id` (UUID PK)
- `created_at` (UTC)
- `updated_at` (UTC + onupdate)

### Scope-модели

Для scope-сущностей (`permissions/credentials/...`) обязательны:

- `scope` (`default | tenant | user`)
- `tenant_id` (nullable)
- `user_id` (nullable)

## 5) API и зависимости

1. Роуты принимают `AsyncSession` через dependency.
2. Аутентификация и RBAC — только через dependencies (`get_current_user`, admin-guards).
3. Для публичных контрактов использовать Pydantic schema (`response_model`).
4. Ошибки домена переводить в корректные HTTP-коды на уровне API.

## 6) Безопасность

1. Всегда проверять `tenant_id` при доступе к tenant-данным.
2. Credentials храним только в шифрованном виде (CryptoService).
3. В не-local окружениях запрещены «молчаливые» dev-defaults для критичных сценариев.
4. Секреты/ключи никогда не хардкодим в коде.

## 7) Логирование и наблюдаемость

1. Логирование структурированное.
2. Для ключевых операций логируем минимум: `entity/id`, `tenant_id`, `user_id`, `status`, `duration_ms`.
3. Ошибки логируем с контекстом операции.
4. Correlation/request id должен проходить через весь request flow.

## 8) Миграции

1. Уникальные revision id, линейная история без конфликтов.
2. Нельзя резко вводить NOT NULL на существующие данные: сначала nullable + backfill + alter.
3. Изменение типа — через безопасный промежуточный шаг.
4. Удаления полей/таблиц — только после периода deprecation.

## 9) Тестирование

1. Для новой бизнес-логики — unit tests.
2. Для критичных flow (routing, permissions, credentials, rag lifecycle) — integration tests.
3. Багфикс сначала подтверждаем тестом (regression-first), потом чиним.

## 10) Чеклист PR

1. Асинхронность и типизация соблюдены.
2. Слои не смешаны (API/Service/Repository).
3. Транзакционная политика соблюдена (`flush` vs `commit`).
4. Tenant isolation и scope resolution соблюдены.
5. Добавлены/обновлены тесты.
6. Документация обновлена при изменении поведения.
