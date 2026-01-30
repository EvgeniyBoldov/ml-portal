# Docker Compose

## Обзор сервисов

```yaml
services:
  # Application
  api           # FastAPI backend
  web           # React frontend (Vite)
  worker        # Celery worker
  
  # Databases
  postgres      # PostgreSQL 15
  redis         # Redis 7
  qdrant        # Qdrant vector DB
  
  # Storage
  minio         # S3-compatible storage
  
  # AI Services
  llm           # LLM inference (vLLM/Ollama)
  emb           # Embedding service
  
  # Proxy
  nginx         # Reverse proxy
```

## Сервисы

### API

```yaml
api:
  build:
    context: ./apps/api
    dockerfile: Dockerfile
  environment:
    - DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/mlportal
    - REDIS_URL=redis://redis:6379/0
    - QDRANT_URL=http://qdrant:6333
    - MINIO_ENDPOINT=minio:9000
    - LLM_BASE_URL=http://llm:8000/v1
    - EMB_BASE_URL=http://emb:8001
  depends_on:
    - postgres
    - redis
    - qdrant
    - minio
  volumes:
    - ./apps/api/src:/app/src  # Dev only
  ports:
    - "8000:8000"
```

### Web

```yaml
web:
  build:
    context: ./apps/web
    dockerfile: Dockerfile
  environment:
    - VITE_API_URL=http://localhost:8000
  ports:
    - "3000:3000"
```

### Worker

```yaml
worker:
  build:
    context: ./apps/api
    dockerfile: Dockerfile
  command: celery -A app.celery_app worker -l info
  environment:
    - DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/mlportal
    - REDIS_URL=redis://redis:6379/0
    - QDRANT_URL=http://qdrant:6333
    - MINIO_ENDPOINT=minio:9000
    - EMB_BASE_URL=http://emb:8001
  depends_on:
    - postgres
    - redis
    - qdrant
    - minio
```

### PostgreSQL

```yaml
postgres:
  image: postgres:15-alpine
  environment:
    - POSTGRES_USER=mlportal
    - POSTGRES_PASSWORD=mlportal
    - POSTGRES_DB=mlportal
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports:
    - "5432:5432"
```

### Redis

```yaml
redis:
  image: redis:7-alpine
  volumes:
    - redis_data:/data
  ports:
    - "6379:6379"
```

### Qdrant

```yaml
qdrant:
  image: qdrant/qdrant:latest
  volumes:
    - qdrant_data:/qdrant/storage
  ports:
    - "6333:6333"
```

### MinIO

```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  environment:
    - MINIO_ROOT_USER=minioadmin
    - MINIO_ROOT_PASSWORD=minioadmin
  volumes:
    - minio_data:/data
  ports:
    - "9000:9000"
    - "9001:9001"  # Console
```

### LLM Service

```yaml
llm:
  image: vllm/vllm-openai:latest
  environment:
    - MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
  volumes:
    - llm_models:/root/.cache/huggingface
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  ports:
    - "8001:8000"
```

### Embedding Service

```yaml
emb:
  image: ghcr.io/huggingface/text-embeddings-inference:latest
  environment:
    - MODEL_ID=intfloat/multilingual-e5-small
  volumes:
    - emb_models:/data
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  ports:
    - "8002:80"
```

### Nginx

```yaml
nginx:
  image: nginx:alpine
  volumes:
    - ./infra/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./infra/nginx/certs:/etc/nginx/certs:ro
  ports:
    - "80:80"
    - "443:443"
  depends_on:
    - api
    - web
```

## Volumes

```yaml
volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  minio_data:
  llm_models:
  emb_models:
```

## Networks

```yaml
networks:
  default:
    driver: bridge
```

## Команды

### Запуск

```bash
# Development
docker compose up -d

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Логи

```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f api
```

### Перезапуск

```bash
# Один сервис
docker compose restart api

# Все
docker compose restart
```

### Остановка

```bash
docker compose down

# С удалением volumes
docker compose down -v
```

## Profiles

```yaml
# docker-compose.yml
services:
  llm:
    profiles: ["gpu"]
  
  emb:
    profiles: ["gpu"]
```

```bash
# Запуск с GPU сервисами
docker compose --profile gpu up -d

# Без GPU
docker compose up -d
```

## Environment Files

```bash
# .env
POSTGRES_USER=mlportal
POSTGRES_PASSWORD=secret
POSTGRES_DB=mlportal

REDIS_URL=redis://redis:6379/0

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

LLM_API_KEY=your-api-key
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

EMB_MODEL=intfloat/multilingual-e5-small

JWT_SECRET=your-jwt-secret
CREDENTIALS_MASTER_KEY=your-master-key
```
