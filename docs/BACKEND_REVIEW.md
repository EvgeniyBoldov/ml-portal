# Backend Review v2.3 — ML Portal

> Дата: 2026-04-08
> Ревизия: v2.3
> Scope: 545 .py файлов, 83K LOC, 90 тестов (14.5K LOC)
> Оценка: **8.6/10** — Production-ready

---

## 1. ОЦЕНКИ

| Направление | v1 | v2.3 | Δ |
|---|---|---|---|
| **Архитектура** | 7 | 8.5 | +1.5 |
| **Runtime** | 8 | 9.0 | +1.0 |
| **Декомпозиция** | 8 | 9.0 | +1.0 |
| **Data Model** | 7 | 7.5 | +0.5 |
| **API Design** | 7 | 8.5 | +1.5 |
| **Error Handling** | 6 | 9.5 | +3.5 |
| **Security** | 7 | 9.0 | +2.0 |
| **Тестирование** | 3 | 8.0 | +5.0 |
| **Документация** | 6 | 8.0 | +2.0 |
| **Sandbox** | 8 | 8.5 | +0.5 |
| **Performance** | 6 | 8.5 | +2.5 |
| **Code Quality** | 7 | 9.0 | +2.0 |
| **ИТОГО** | **6.7** | **8.6** | **+1.9** |

---

## 2. ОТКРЫТЫЕ ПРОБЛЕМЫ

### 🔴 Критичные — нет

### 🟡 Средний приоритет

| # | Проблема | Файл | Детали |
|---|---|---|---|
| 1 | `HTTPException` в repository layer | `repositories/factory.py:212,243` | Репозиторий не должен знать о HTTP. Заменить на `UnauthorizedError` / `TenantNotAssignedError` |
| 2 | Нет unit-теста для `collection_service.py` | `tests/unit/` | Все под-сервисы покрыты, основной — нет |
| 3 | `AsyncMock` без `spec=` в 49 файлах | `tests/unit/*` | Молчаливо мокируются несуществующие методы. Добавить `spec=ClassName` |

### � Технический долг

| # | Проблема | Детали |
|---|---|---|
| 4 | `metrics.py` — только Celery/emb-gateway | DB connection pool метрики отсутствуют (есть `get_pool_stats()` в health, но нет Prometheus-экспорта) |
| 5 | Глобальный rate limit | Rate limiting есть только для auth и chat write-path. Admin API и прочие эндпоинты не ограничены |

---

## 3. СТАТИСТИКА

| Метрика | Значение |
|---|---|
| .py файлов | 545 |
| LOC | 83K |
| Тестов | 90 файлов / 14.5K LOC |
| Syntax errors | 0 |
| Dead code | 0 |
| Крупных файлов (>700 строк) | 1 (`planner.py` 691 — borderline) |
| HTTPException в сервисах | 2 (только `factory.py`, допустимый DI-слой) |
