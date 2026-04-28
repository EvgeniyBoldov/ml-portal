# Build Guide

Документ фиксирует текущий процесс сборки после унификации на один base-образ `ml-portal-base-ml`.

## 1. Dev сборка

### 1.1 Подготовка

```bash
make env
# отредактировать .env
```

### 1.2 Базовый образ (общие тяжелые зависимости, включая torch)

```bash
make build-base
```

Что делает:
- собирает `infra/docker/base/Dockerfile.ml`
- ставит 2 тега одновременно:
  - `ml-portal-base-ml:latest` (dev)
  - `ml-portal-base-ml:v1` (базовый prod-тег по умолчанию)

### 1.3 Сервисные dev-образы

```bash
make build-dev
# или make build
```

Dev Dockerfile'ы используют `ml-portal-base-ml:latest`:
- `api`
- `worker`
- `emb`
- `rerank`

## 2. Prod сборка

Prod-образы собираются отдельно командой `make build-prod`.

```bash
make build-prod
```

По умолчанию:
- `BASE_IMAGE_PROD=ml-portal-base-ml:v1`
- `PROD_IMAGE_TAG=v1`
- префикс образов `PROD_IMAGE_PREFIX=ml-portal`

Будут собраны:
- `ml-portal-api:v1`
- `ml-portal-worker:v1`
- `ml-portal-emb:v1`
- `ml-portal-rerank:v1`
- `ml-portal-frontend:v1`
- `ml-portal-nginx:v1`

## 3. Рекомендуемая схема версионирования

Для релиза задавай один и тот же тег base и сервисов:

```bash
make build-base BASE_IMAGE_PROD=ml-portal-base-ml:v3
make build-prod BASE_IMAGE_PROD=ml-portal-base-ml:v3 PROD_IMAGE_TAG=v3
```

Если base хранится в registry:

```bash
make build-prod \
  BASE_IMAGE_PROD=registry.example.com/ml-portal/base-ml:v3 \
  PROD_IMAGE_TAG=v3 \
  PROD_IMAGE_PREFIX=registry.example.com/ml-portal
```

## 4. Offline/air-gapped поставка

Если на проде нет интернета:

1. На connected-машине собрать образы.
2. Сохранить в tar:

```bash
docker save \
  ml-portal-base-ml:v3 \
  ml-portal-api:v3 \
  ml-portal-worker:v3 \
  ml-portal-emb:v3 \
  ml-portal-rerank:v3 \
  ml-portal-frontend:v3 \
  ml-portal-nginx:v3 \
  -o ml-portal-v3-images.tar
```

3. Перенести tar в прод-контур.
4. Загрузить:

```bash
docker load -i ml-portal-v3-images.tar
```

## 5. Быстрые проверки

```bash
docker image ls | rg 'ml-portal'
docker compose images
```

## 6. Частые проблемы

- `pull access denied for ml-portal-base-ml`:
  - не собран base (`make build-base`) или неверный `BASE_IMAGE_PROD`.
- длительная сборка:
  - пересобирай base только при изменении `infra/docker/base/requirements.ml.txt`.
- рассинхрон dev/prod:
  - фиксируй `BASE_IMAGE_PROD` и релизный `PROD_IMAGE_TAG`, не используй `latest` в prod.
