# Kubernetes Deployment Architecture

## Обзор

ML Portal разворачивается в распределённой архитектуре с разделением ответственности между кластерами:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet / Users                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Cloud LoadBalancer (L7)                         │
│                  - TLS Termination                               │
│                  - DDoS Protection                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MAIN KUBERNETES CLUSTER                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Ingress Controller (nginx-ingress)                       │  │
│  │  - portal.example.com → frontend                          │  │
│  │  - portal.example.com/api → api                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Frontend    │  │     API      │  │   Workers    │          │
│  │  (nginx)     │  │  (FastAPI)   │  │   (Celery)   │          │
│  │  Replicas: 3 │  │  Replicas: 5 │  │  Replicas: 4 │          │
│  │  CPU: 100m   │  │  CPU: 500m   │  │  CPU: 1000m  │          │
│  │  RAM: 128Mi  │  │  RAM: 512Mi  │  │  RAM: 1Gi    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Embedding Service (CPU-based)                    │   │
│  │         Replicas: 3                                      │   │
│  │         CPU: 2000m, RAM: 4Gi                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────┬──────────────────┬──────────────────┬──────────────────┘
         │                  │                  │
         │ (HTTP)           │ (HTTP)           │ (PostgreSQL/Redis)
         ▼                  ▼                  ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  GPU CLUSTER     │  │ OBSERVABILITY│  │  MANAGED SERVICES    │
│                  │  │   CLUSTER    │  │                      │
│  ┌────────────┐  │  │              │  │  ┌────────────────┐  │
│  │    LLM     │  │  │ ┌──────────┐ │  │  │  PostgreSQL    │  │
│  │  (vLLM)    │  │  │ │Prometheus│ │  │  │  (RDS/Managed) │  │
│  │  GPU: 1xA10│  │  │ └──────────┘ │  │  └────────────────┘  │
│  │  CPU: 8    │  │  │              │  │                      │
│  │  RAM: 32Gi │  │  │ ┌──────────┐ │  │  ┌────────────────┐  │
│  └────────────┘  │  │ │ Grafana  │ │  │  │     Redis      │  │
│                  │  │ └──────────┘ │  │  │  (ElastiCache) │  │
│  ┌────────────┐  │  │              │  │  └────────────────┘  │
│  │  Rerank    │  │  │ ┌──────────┐ │  │                      │
│  │  GPU: 1xT4 │  │  │ │   Loki   │ │  │  ┌────────────────┐  │
│  │  CPU: 4    │  │  │ └──────────┘ │  │  │    Qdrant      │  │
│  │  RAM: 16Gi │  │  │              │  │  │  (Managed/VM)  │  │
│  └────────────┘  │  │ ┌──────────┐ │  │  └────────────────┘  │
│                  │  │ │AlertMgr  │ │  │                      │
│                  │  │ └──────────┘ │  │  ┌────────────────┐  │
│                  │  │              │  │  │   MinIO/S3     │  │
│                  │  └──────────────┘  │  │  (Object Store)│  │
│                  │                    │  └────────────────┘  │
└──────────────────┘                    └──────────────────────┘
```

## Cluster 1: Main Kubernetes Cluster

### Назначение
Основные stateless приложения и бизнес-логика.

### Компоненты

#### 1. Frontend (nginx + React SPA)
- **Образ**: `ml-portal-frontend:latest`
- **Replicas**: 3 (prod), 2 (staging), 1 (dev)
- **Resources**:
  - CPU: 100m request, 200m limit
  - Memory: 128Mi request, 256Mi limit
- **Порт**: 3000
- **Health checks**: `/` (HTTP 200)
- **Deployment strategy**: RollingUpdate (maxSurge: 1, maxUnavailable: 0)

#### 2. API (FastAPI)
- **Образ**: `ml-portal-api:latest`
- **Replicas**: 5 (prod), 3 (staging), 2 (dev)
- **Resources**:
  - CPU: 500m request, 1000m limit
  - Memory: 512Mi request, 1Gi limit
- **Порт**: 8000
- **Health checks**:
  - Liveness: `/api/v1/healthz`
  - Readiness: `/api/v1/ready`
- **HPA**: CPU 70%, Memory 80%, min 3, max 10
- **Environment**:
  - DATABASE_URL (from secret)
  - REDIS_URL (from secret)
  - S3_ENDPOINT (from configmap)
  - QDRANT_URL (from configmap)
  - LLM_BASE_URL (from configmap) → GPU cluster
  - EMB_BASE_URL (from service) → embedding-service:8001

#### 3. Workers (Celery)
- **Образ**: `ml-portal-worker:latest`
- **Replicas**: 4 (prod), 2 (staging), 1 (dev)
- **Resources**:
  - CPU: 1000m request, 2000m limit
  - Memory: 1Gi request, 2Gi limit
- **HPA**: Celery queue length (target: 10 tasks/worker)
- **Environment**: то же что API + CELERY_BROKER_URL

#### 4. Embedding Service
- **Образ**: `ml-portal-embedding:latest`
- **Replicas**: 3 (prod), 2 (staging), 1 (dev)
- **Resources**:
  - CPU: 2000m request, 4000m limit
  - Memory: 4Gi request, 8Gi limit
- **Порт**: 8001
- **Models**: sentence-transformers (CPU-based)
- **Volume**: emptyDir для кеша моделей (или PVC если нужно)

#### 5. Ingress (nginx-ingress)
- **Controller**: nginx-ingress-controller
- **TLS**: cert-manager (Let's Encrypt)
- **Routes**:
  - `portal.example.com/` → frontend-service:3000
  - `portal.example.com/api` → api-service:8000
- **Rate limiting**: 100 req/sec per IP
- **Client max body size**: 100M

### Networking
- **Service type**: ClusterIP (internal)
- **Ingress**: LoadBalancer (external)
- **Network policies**:
  - Frontend → API only
  - API → PostgreSQL, Redis, Qdrant, S3, Embedding, GPU cluster
  - Workers → PostgreSQL, Redis, Qdrant, S3, Embedding, GPU cluster
  - Deny all other traffic

### Storage
- **ConfigMaps**: app-config, service-endpoints
- **Secrets**: db-credentials, s3-credentials, jwt-secret, llm-api-key
- **PersistentVolumes**: нет (stateless)

---

## Cluster 2: GPU Cluster

### Назначение
ML inference с GPU для тяжелых моделей.

### Компоненты

#### 1. LLM Service (vLLM)
- **Образ**: `vllm/vllm-openai:latest` или custom
- **Replicas**: 1-2 (зависит от GPU availability)
- **Resources**:
  - GPU: 1x NVIDIA A10/A100
  - CPU: 8 cores
  - Memory: 32Gi
- **Порт**: 8000
- **API**: OpenAI-compatible `/v1/chat/completions`
- **Models**: llama-3.1-70b или другие
- **Volume**: PVC для моделей (100Gi SSD)

#### 2. Rerank Service
- **Образ**: `ml-portal-rerank:latest`
- **Replicas**: 1-2
- **Resources**:
  - GPU: 1x NVIDIA T4
  - CPU: 4 cores
  - Memory: 16Gi
- **Порт**: 8002
- **Models**: cross-encoder/ms-marco-MiniLM-L-6-v2

### GPU Configuration
```yaml
nodeSelector:
  gpu: "true"
  gpu-type: "a10"  # или a100, t4

tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule

resources:
  limits:
    nvidia.com/gpu: 1
```

### Networking
- **Service type**: ClusterIP
- **Ingress**: нет (внутренний доступ)
- **Доступ**: только из main cluster (API, Workers)
- **Network policies**: allow from main cluster only

---

## Cluster 3: Observability Cluster

### Назначение
Централизованный мониторинг, логирование, алертинг.

### Компоненты

#### 1. Prometheus
- **Helm chart**: kube-prometheus-stack
- **Retention**: 15 days
- **Storage**: 100Gi PVC (SSD)
- **Scrape targets**:
  - Main cluster (federation/remote-write)
  - GPU cluster (federation/remote-write)
  - External services (exporters)
- **Exporters**:
  - postgres-exporter
  - redis-exporter
  - qdrant metrics
  - minio metrics

#### 2. Grafana
- **Datasources**:
  - Prometheus (metrics)
  - Loki (logs)
  - Tempo (traces, опционально)
- **Dashboards**:
  - Kubernetes cluster overview
  - API performance
  - GPU utilization
  - Database metrics
  - Business metrics (RAG, chat)
- **Auth**: OAuth2/SSO

#### 3. Loki
- **Retention**: 30 days
- **Storage**: S3-compatible (MinIO)
- **Log sources**:
  - Main cluster (promtail/fluent-bit)
  - GPU cluster (promtail/fluent-bit)
  - External services

#### 4. Alertmanager
- **Routes**:
  - Critical → PagerDuty/Telegram
  - Warning → Slack
  - Info → Email
- **Alerts**:
  - High error rate (5xx > 1%)
  - High latency (p95 > 2s)
  - GPU OOM
  - Database connection pool exhausted
  - Disk usage > 80%

### Agents в других кластерах
```yaml
# Main cluster
- prometheus-agent (remote-write to observability)
- fluent-bit (forward to Loki)

# GPU cluster
- prometheus-agent
- fluent-bit
- dcgm-exporter (NVIDIA GPU metrics)
```

---

## External Services (Managed)

### PostgreSQL
- **Provider**: AWS RDS / Yandex Managed PostgreSQL
- **Instance**: db.r6g.xlarge (4 vCPU, 16GB RAM)
- **Storage**: 100GB gp3 SSD (auto-scaling до 500GB)
- **Backups**: ежедневные, retention 7 days
- **Replicas**: 1 read replica
- **Connection pooling**: PgBouncer (100 connections)
- **Monitoring**: postgres-exporter → Prometheus

### Redis
- **Provider**: AWS ElastiCache / Yandex Managed Redis
- **Instance**: cache.r6g.large (2 vCPU, 13GB RAM)
- **Persistence**: AOF enabled
- **Replicas**: 1 replica
- **Monitoring**: redis-exporter → Prometheus

### Qdrant
- **Option 1**: Qdrant Cloud (managed)
- **Option 2**: Self-hosted cluster (3 nodes, 8GB RAM each)
- **Replication**: factor 2
- **Storage**: SSD
- **Monitoring**: встроенные метрики → Prometheus

### MinIO / S3
- **Provider**: AWS S3 / Yandex Object Storage / Self-hosted MinIO
- **Buckets**:
  - `rag` - документы RAG
  - `artifacts` - артефакты моделей
  - `loki-logs` - логи Loki
- **Lifecycle**: автоудаление старых файлов (90 days)
- **Monitoring**: minio-exporter → Prometheus

---

## Security

### Network Security
- **Network Policies**: deny all by default, allow only необходимое
- **Service Mesh**: опционально (Istio/Linkerd) для mTLS
- **Egress control**: whitelist внешних API (NetBox, Jira)

### Secrets Management
- **Kubernetes Secrets**: для credentials
- **External Secrets Operator**: опционально (AWS Secrets Manager, Vault)
- **Rotation**: автоматическая ротация паролей (90 days)

### Pod Security
- **SecurityContext**:
  - runAsNonRoot: true
  - runAsUser: 1000
  - readOnlyRootFilesystem: true (где возможно)
  - allowPrivilegeEscalation: false
  - capabilities: drop ALL

### RBAC
- **ServiceAccounts**: отдельные для каждого компонента
- **Roles**: минимальные права (least privilege)
- **ClusterRoles**: только для системных компонентов

---

## Disaster Recovery

### Backups
- **PostgreSQL**: ежедневные автобэкапы (7 days retention)
- **Qdrant**: snapshot каждые 6 часов
- **MinIO**: versioning enabled
- **Kubernetes manifests**: GitOps (ArgoCD/FluxCD)

### Recovery Time Objective (RTO)
- **Main cluster**: < 15 minutes
- **GPU cluster**: < 30 minutes
- **Observability**: < 1 hour
- **Databases**: < 1 hour (restore from backup)

### Recovery Point Objective (RPO)
- **PostgreSQL**: < 5 minutes (PITR)
- **Qdrant**: < 6 hours
- **MinIO**: 0 (versioning)

---

## Scaling Strategy

### Horizontal Scaling (HPA)
- **API**: CPU/Memory based
- **Workers**: Celery queue length based
- **Frontend**: CPU based (обычно не нужно)

### Vertical Scaling
- **Embedding**: увеличение CPU/RAM при росте нагрузки
- **GPU**: переход на более мощные GPU (T4 → A10 → A100)

### Cluster Autoscaling
- **Node autoscaling**: включено (min 3, max 20 nodes)
- **GPU nodes**: отдельный node pool (min 1, max 5)

---

## Cost Optimization

### Compute
- **Spot instances**: для non-critical workers (50% экономия)
- **Reserved instances**: для stable workloads (API, DB)
- **Autoscaling**: scale down в нерабочее время

### Storage
- **S3 Intelligent Tiering**: автоматический переход в холодное хранилище
- **Log retention**: 30 days (не больше)
- **Snapshot cleanup**: автоудаление старых снапшотов

### GPU
- **Shared GPU**: MIG (Multi-Instance GPU) для A100
- **Preemptible GPU**: для dev/staging
- **Scheduled scaling**: выключение GPU в нерабочее время (dev/staging)

---

## Deployment Workflow

1. **Build**: CI/CD собирает Docker images
2. **Push**: образы в registry (ECR/GCR/Harbor)
3. **Deploy Observability**: первым (чтобы видеть что происходит)
4. **Deploy Main**: API, Workers, Frontend, Embedding
5. **Deploy GPU**: LLM, Rerank
6. **Smoke tests**: автоматические тесты после деплоя
7. **Rollback**: автоматический при провале health checks

---

## Monitoring Dashboards

### Main Cluster
- Kubernetes cluster overview
- API latency/throughput
- Worker queue length
- Error rates

### GPU Cluster
- GPU utilization
- GPU memory usage
- Inference latency
- Model throughput

### Databases
- Connection pool usage
- Query latency
- Replication lag
- Disk usage

### Business Metrics
- RAG documents ingested
- Chat messages sent
- Active users
- API usage by tenant
