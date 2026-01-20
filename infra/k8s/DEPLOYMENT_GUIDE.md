# ML Portal Kubernetes Deployment Guide

## Обзор

Пошаговая инструкция по развертыванию ML Portal в production Kubernetes кластере.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    4 Кластера                                │
├─────────────────────────────────────────────────────────────┤
│ 1. Main Cluster      - Frontend, API, Workers, Embedding    │
│ 2. GPU Cluster       - LLM, Rerank (GPU inference)          │
│ 3. Observability     - Prometheus, Grafana, Loki            │
│ 4. Managed Services  - PostgreSQL, Redis, Qdrant, MinIO     │
└─────────────────────────────────────────────────────────────┘
```

## Предварительные требования

### Инструменты

```bash
# Установите необходимые инструменты
brew install kubectl helm

# Проверьте версии
kubectl version --client  # >= 1.28
helm version             # >= 3.12
```

### Kubernetes Кластеры

- **Main Cluster**: 3+ nodes (4 CPU, 16GB RAM each)
- **GPU Cluster**: 1+ GPU nodes (NVIDIA T4/A10/A100)
- **Observability Cluster**: 2+ nodes (4 CPU, 16GB RAM each)

### Managed Services

Подготовьте:
- PostgreSQL (4 vCPU, 16GB RAM, 100GB storage)
- Redis (2GB RAM)
- Qdrant (3 nodes, 8GB RAM each)
- MinIO/S3 (500GB+ storage)

См. документацию в `external-services/`

## Шаг 1: Подготовка Managed Services

### 1.1 PostgreSQL

```bash
# Следуйте инструкциям в external-services/postgresql.md
# Создайте БД и пользователя
# Запишите connection string
```

### 1.2 Redis

```bash
# Следуйте инструкциям в external-services/redis.md
# Запишите Redis URL
```

### 1.3 Qdrant

```bash
# Следуйте инструкциям в external-services/qdrant.md
# Создайте коллекции для RAG
```

### 1.4 MinIO/S3

```bash
# Следуйте инструкциям в external-services/minio.md
# Создайте buckets: rag, artifacts, loki-logs
```

## Шаг 2: Подготовка Docker Images

### 2.1 Build Production Images

```bash
cd /path/to/ml-portal

# Build API
docker build -f infra/docker/api/Dockerfile.prod -t registry.example.com/ml-portal-api:1.0.0 .

# Build Worker
docker build -f infra/docker/worker/Dockerfile.prod -t registry.example.com/ml-portal-worker:1.0.0 .

# Build Embedding
docker build -f infra/docker/emb/Dockerfile.prod -t registry.example.com/ml-portal-embedding:1.0.0 .

# Build Frontend
docker build -f infra/docker/frontend/Dockerfile.prod -t registry.example.com/ml-portal-frontend:1.0.0 .

# Build Rerank
docker build -f infra/docker/rerank/Dockerfile -t registry.example.com/ml-portal-rerank:1.0.0 .
```

### 2.2 Push to Registry

```bash
# Login to registry
docker login registry.example.com

# Push images
docker push registry.example.com/ml-portal-api:1.0.0
docker push registry.example.com/ml-portal-worker:1.0.0
docker push registry.example.com/ml-portal-embedding:1.0.0
docker push registry.example.com/ml-portal-frontend:1.0.0
docker push registry.example.com/ml-portal-rerank:1.0.0
```

## Шаг 3: Настройка Kubernetes

### 3.1 Создайте Registry Secret

```bash
kubectl create secret docker-registry registry-credentials \
  --docker-server=registry.example.com \
  --docker-username=<USERNAME> \
  --docker-password=<PASSWORD> \
  --docker-email=<EMAIL> \
  -n ml-portal-main

# Скопируйте в другие namespaces
kubectl get secret registry-credentials -n ml-portal-main -o yaml | \
  sed 's/namespace: ml-portal-main/namespace: ml-portal-gpu/' | \
  kubectl apply -f -
```

### 3.2 Установите Ingress Controller

```bash
# Установите nginx-ingress
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=LoadBalancer
```

### 3.3 Установите cert-manager (для TLS)

```bash
# Установите cert-manager
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

# Создайте ClusterIssuer для Let's Encrypt
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

## Шаг 4: Деплой Observability Cluster

```bash
cd infra/k8s

# Деплой observability stack
./scripts/deploy-observability.sh

# Получите Grafana credentials
kubectl get secret -n ml-portal-observability ml-portal-observability-grafana \
  -o jsonpath="{.data.admin-password}" | base64 --decode

# Откройте Grafana
kubectl port-forward -n ml-portal-observability svc/ml-portal-observability-grafana 3000:80
# Перейдите на http://localhost:3000
```

## Шаг 5: Создайте Secrets для Main Cluster

```bash
cd infra/k8s

# Интерактивное создание секретов
./scripts/create-secrets.sh prod

# Или создайте вручную
kubectl create secret generic app-secrets \
  --namespace=ml-portal-main \
  --from-literal=DATABASE_URL="postgresql://..." \
  --from-literal=REDIS_URL="redis://..." \
  --from-literal=S3_ACCESS_KEY="..." \
  --from-literal=S3_SECRET_KEY="..." \
  --from-literal=JWT_SECRET="..." \
  --from-literal=LLM_API_KEY="..." \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Шаг 6: Деплой Main Cluster

### 6.1 Обновите values-prod.yaml

```bash
cd clusters/main

# Отредактируйте values-prod.yaml
vim values-prod.yaml

# Обновите:
# - global.domain
# - global.imageRegistry
# - image.tag для всех сервисов
# - configMap.data (URLs внешних сервисов)
```

### 6.2 Деплой

```bash
cd ../..

# Деплой main cluster
./scripts/deploy-main.sh prod

# Проверьте статус
kubectl get pods -n ml-portal-main
kubectl get ingress -n ml-portal-main
```

### 6.3 Проверка

```bash
# Проверьте API health
curl https://portal.example.com/api/v1/healthz

# Проверьте frontend
curl https://portal.example.com/

# Проверьте логи
kubectl logs -n ml-portal-main deployment/ml-portal-main-api --tail=50
```

## Шаг 7: Деплой GPU Cluster

### 7.1 Подготовка GPU Nodes

```bash
# Убедитесь что GPU nodes имеют label
kubectl label nodes <gpu-node-1> gpu=true gpu-type=a10
kubectl label nodes <gpu-node-2> gpu=true gpu-type=t4

# Проверьте GPU
kubectl describe nodes -l gpu=true | grep -A 5 "Allocated resources"
```

### 7.2 Загрузите ML Models

```bash
# Создайте PVC для моделей
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: llm-models-pvc
  namespace: ml-portal-gpu
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 200Gi
EOF

# Загрузите модели (используйте init job или manual copy)
# Для vLLM модели будут загружены автоматически при старте
```

### 7.3 Деплой

```bash
# Деплой GPU cluster
./scripts/deploy-gpu.sh prod

# Проверьте статус
kubectl get pods -n ml-portal-gpu
kubectl logs -n ml-portal-gpu deployment/llm-service --tail=50
```

### 7.4 Проверка

```bash
# Проверьте LLM service
kubectl port-forward -n ml-portal-gpu svc/llm-service 8000:8000

# Тест LLM
curl http://localhost:8000/v1/models

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-70b-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Шаг 8: Настройка Мониторинга

### 8.1 Импортируйте Dashboards в Grafana

```bash
# Откройте Grafana
kubectl port-forward -n ml-portal-observability svc/ml-portal-observability-grafana 3000:80

# Перейдите на http://localhost:3000
# Login: admin / <password from step 4>

# Импортируйте dashboards:
# - Kubernetes Cluster Overview (ID: 7249)
# - API Performance (ID: 12230)
# - GPU Metrics (ID: 12239)
```

### 8.2 Настройте Alerts

```bash
# Проверьте Alertmanager
kubectl port-forward -n ml-portal-observability svc/ml-portal-observability-kube-prometheus-alertmanager 9093:9093

# Настройте notification channels в values.yaml
# Обновите deployment
helm upgrade ml-portal-observability clusters/observability \
  --namespace ml-portal-observability \
  --values clusters/observability/values.yaml
```

## Шаг 9: Smoke Tests

### 9.1 API Tests

```bash
# Health check
curl https://portal.example.com/api/v1/healthz

# Create user
curl -X POST https://portal.example.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test123456"}'

# Login
curl -X POST https://portal.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test123456"}'
```

### 9.2 RAG Tests

```bash
# Upload document
curl -X POST https://portal.example.com/api/v1/rag/documents \
  -H "Authorization: Bearer <TOKEN>" \
  -F "file=@test.pdf"

# Check status
curl https://portal.example.com/api/v1/rag/documents/<DOC_ID> \
  -H "Authorization: Bearer <TOKEN>"

# Search
curl -X POST https://portal.example.com/api/v1/rag/search \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'
```

### 9.3 Chat Tests

```bash
# Create chat
curl -X POST https://portal.example.com/api/v1/chats \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Chat"}'

# Send message
curl -X POST https://portal.example.com/api/v1/chats/<CHAT_ID>/messages \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello, how are you?"}'
```

## Шаг 10: Production Checklist

### Security

- [ ] Все secrets созданы через external-secrets или sealed-secrets
- [ ] TLS сертификаты настроены (Let's Encrypt)
- [ ] Network policies включены
- [ ] RBAC настроен
- [ ] Pod security contexts применены
- [ ] Ingress rate limiting настроен

### High Availability

- [ ] API replicas >= 3
- [ ] Workers replicas >= 2
- [ ] PostgreSQL с репликацией
- [ ] Redis с репликацией
- [ ] Qdrant кластер (3 nodes)
- [ ] PodDisruptionBudgets настроены

### Monitoring

- [ ] Prometheus собирает метрики
- [ ] Grafana dashboards импортированы
- [ ] Alerts настроены
- [ ] Loki собирает логи
- [ ] ServiceMonitors созданы

### Backups

- [ ] PostgreSQL автобэкапы (7 days)
- [ ] Qdrant snapshots (каждые 6 часов)
- [ ] MinIO versioning включен
- [ ] Kubernetes manifests в Git

### Performance

- [ ] HPA настроен для API и Workers
- [ ] Resource limits установлены
- [ ] GPU nodes правильно labeled
- [ ] Connection pooling (PgBouncer) настроен

## Troubleshooting

### Pods не стартуют

```bash
# Проверьте events
kubectl get events -n ml-portal-main --sort-by='.lastTimestamp'

# Проверьте describe
kubectl describe pod <POD_NAME> -n ml-portal-main

# Проверьте логи
kubectl logs <POD_NAME> -n ml-portal-main --previous
```

### Database connection issues

```bash
# Проверьте secret
kubectl get secret app-secrets -n ml-portal-main -o yaml

# Проверьте network connectivity
kubectl run -it --rm debug --image=postgres:15 --restart=Never -- \
  psql postgresql://user:pass@host:5432/db
```

### GPU не доступны

```bash
# Проверьте GPU nodes
kubectl get nodes -l gpu=true

# Проверьте NVIDIA device plugin
kubectl get pods -n kube-system | grep nvidia

# Проверьте GPU allocation
kubectl describe nodes -l gpu=true | grep -A 5 "Allocated resources"
```

### High latency

```bash
# Проверьте метрики в Grafana
# Проверьте HPA
kubectl get hpa -n ml-portal-main

# Проверьте resource usage
kubectl top pods -n ml-portal-main
kubectl top nodes
```

## Rollback

### Откат деплоя

```bash
# Откат к предыдущей версии
helm rollback ml-portal-main -n ml-portal-main

# Откат к конкретной ревизии
helm rollback ml-portal-main 3 -n ml-portal-main

# Проверьте историю
helm history ml-portal-main -n ml-portal-main
```

## Обновление

### Rolling Update

```bash
# Обновите image tag в values-prod.yaml
vim clusters/main/values-prod.yaml

# Деплой новой версии
./scripts/deploy-main.sh prod

# Следите за rollout
kubectl rollout status deployment/ml-portal-main-api -n ml-portal-main
```

### Blue-Green Deployment

```bash
# Создайте новый namespace для green
kubectl create namespace ml-portal-main-green

# Деплой в green
helm install ml-portal-main-green clusters/main \
  --namespace ml-portal-main-green \
  --values clusters/main/values-prod.yaml

# Переключите Ingress на green
# Удалите blue после проверки
```

## Масштабирование

### Horizontal Scaling

```bash
# Увеличьте replicas
kubectl scale deployment ml-portal-main-api --replicas=10 -n ml-portal-main

# Или обновите HPA
kubectl edit hpa ml-portal-main-api -n ml-portal-main
```

### Vertical Scaling

```bash
# Обновите resources в values-prod.yaml
# Деплой изменений
./scripts/deploy-main.sh prod
```

## Поддержка

Для вопросов и проблем:
- Создайте issue в репозитории
- Проверьте документацию в `docs/`
- Проверьте логи в Grafana/Loki
