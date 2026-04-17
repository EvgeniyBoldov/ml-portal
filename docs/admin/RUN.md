# Run Guide

## 1. Запуск стека

```bash
make up
```

Команда запускает `docker compose up -d` для всех сервисов.

## 2. Проверка статуса

```bash
make ps
docker compose logs --tail=200 api
```

## 3. Доступные endpoint'ы (dev)
- API: `http://localhost:8000`
- API health: `http://localhost:8000/api/v1/healthz`
- Frontend: `http://localhost:5173`
- MinIO console: `http://localhost:9001`
- Qdrant: `http://localhost:6333`

## 4. Миграции
Если нужно применить вручную:

```bash
make migrate
```

## 5. Перезапуск и остановка

```bash
make restart
make down
```

## 6. Полезные команды эксплуатации

```bash
make logs
docker compose logs --tail=200 worker
docker compose logs --tail=200 frontend
```

## 7. Первый вход в админку
Логин/пароль администратора берутся из `.env`:

- `DEFAULT_ADMIN_LOGIN`
- `DEFAULT_ADMIN_PASSWORD`

## 8. Быстрый smoke-check после запуска
1. `healthz` API отвечает 200.
2. В админке открываются разделы users/agents/tools/collections.
3. Создается тестовая коллекция.
4. В логах `api` и `worker` нет повторяющихся ошибок миграции/коннекта к БД/Redis.
