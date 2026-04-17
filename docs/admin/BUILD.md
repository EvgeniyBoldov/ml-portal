# Build Guide

## Вариант A: стандартная сборка
После настройки `.env`:

```bash
make build
```

Собирает сервисные образы из [docker-compose.yml](../../docker-compose.yml).

## Вариант B: полная пересборка без кеша

```bash
make build-no-cache
```

## Вариант C: пересобрать базовые образы (редко)
Нужно только при изменении базовых зависимостей в `infra/docker/base/*`:

```bash
make build-base
make build
```

## Проверка результатов

```bash
docker compose images
docker compose ps
```

## Типичные проблемы
- Нет `.env`: выполните `make env`.
- Ошибки скачивания npm/pip внутри контейнеров: проверьте сеть/прокси.
- Конфликт образов после больших изменений: `make clean-images` и повторная сборка.
