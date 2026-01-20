# Kubernetes Deployment Infrastructure

## Архитектура

Проект разворачивается в **4 кластера**:

1. **Main Cluster** (`clusters/main/`) - основные приложения (frontend, API, workers, embedding)
2. **GPU Cluster** (`clusters/gpu/`) - ML inference с GPU (LLM, rerank)
3. **Observability Cluster** (`clusters/observability/`) - мониторинг и логирование
4. **Managed Services** (внешние) - stateful данные (PostgreSQL, Redis, Qdrant, MinIO)

## Структура директорий

```
infra/k8s/
├── README.md                          # Этот файл
├── DEPLOYMENT_GUIDE.md                # Пошаговая инструкция по деплою
├── ARCHITECTURE.md                    # Детальная архитектура
│
├── clusters/                          # Helm charts для каждого кластера
│   ├── main/                          # Main Kubernetes Cluster
│   │   ├── Chart.yaml
│   │   ├── values.yaml                # Дефолтные значения
│   │   ├── values-dev.yaml            # Dev окружение
│   │   ├── values-staging.yaml        # Staging окружение
│   │   ├── values-prod.yaml           # Production окружение
│   │   └── templates/                 # K8s манифесты
│   │       ├── frontend/
│   │       ├── api/
│   │       ├── workers/
│   │       ├── embedding/
│   │       ├── ingress/
│   │       └── _helpers.tpl
│   │
│   ├── gpu/                           # GPU Cluster
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   ├── values-prod.yaml
│   │   └── templates/
│   │       ├── llm/
│   │       └── rerank/
│   │
│   └── observability/                 # Observability Cluster
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-prod.yaml
│       └── templates/
│           ├── prometheus/
│           ├── grafana/
│           ├── loki/
│           └── alertmanager/
│
├── base/                              # Базовые компоненты (переиспользуемые)
│   ├── ingress-nginx/                 # Ingress controller setup
│   ├── cert-manager/                  # TLS certificates
│   └── secrets/                       # Примеры секретов (НЕ коммитим реальные!)
│
├── external-services/                 # Документация по внешним сервисам
│   ├── postgresql.md                  # Настройка PostgreSQL
│   ├── redis.md                       # Настройка Redis
│   ├── qdrant.md                      # Настройка Qdrant
│   └── minio.md                       # Настройка MinIO/S3
│
└── scripts/                           # Утилиты для деплоя
    ├── deploy-main.sh                 # Деплой main кластера
    ├── deploy-gpu.sh                  # Деплой GPU кластера
    ├── deploy-observability.sh        # Деплой observability
    ├── create-secrets.sh              # Генерация секретов
    └── validate-manifests.sh          # Валидация манифестов
```

## Быстрый старт

### Предварительные требования

- Kubernetes 1.28+
- Helm 3.12+
- kubectl
- Docker registry (для образов)
- Managed БД (PostgreSQL, Redis, Qdrant, MinIO) или готовность развернуть их

### 1. Подготовка секретов

```bash
cd infra/k8s/scripts
./create-secrets.sh prod
```

### 2. Деплой Observability кластера

```bash
./deploy-observability.sh prod
```

### 3. Деплой Main кластера

```bash
./deploy-main.sh prod
```

### 4. Деплой GPU кластера

```bash
./deploy-gpu.sh prod
```

## Окружения

- **dev** - локальная разработка (minikube/kind)
- **staging** - тестовое окружение
- **prod** - production

## Документация

- [ARCHITECTURE.md](./ARCHITECTURE.md) - детальная архитектура
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - пошаговая инструкция
- [external-services/](./external-services/) - настройка внешних сервисов

## Мониторинг

После деплоя доступны:

- **Grafana**: https://grafana.your-domain.com
- **Prometheus**: https://prometheus.your-domain.com
- **Alertmanager**: https://alertmanager.your-domain.com

## Поддержка

Для вопросов и проблем создавайте issue в репозитории.
