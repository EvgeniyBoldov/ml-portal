#!/usr/bin/env python3
"""
Генератор кода и документации для ML Portal
"""
import os
import sys
import argparse
from pathlib import Path

def generate_backend_code():
    """Генерирует код бэкенда в back.txt"""
    backend_dir = Path("backend")
    if not backend_dir.exists():
        print("❌ Директория backend не найдена")
        return
    
    code_content = []
    
    # Сканируем все Python файлы
    for py_file in backend_dir.rglob("*.py"):
        if py_file.name == "__pycache__":
            continue
            
        relative_path = py_file.relative_to(backend_dir)
        code_content.append(f"\n# ===== {relative_path} =====\n")
        
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                code_content.append(content)
        except Exception as e:
            code_content.append(f"# Ошибка чтения файла: {e}")
    
    # Записываем в back.txt
    with open("back.txt", "w", encoding="utf-8") as f:
        f.write("".join(code_content))
    
    print("✅ Код бэкенда сгенерирован в back.txt")

def generate_frontend_code():
    """Генерирует код фронтенда в front.txt"""
    frontend_dir = Path("frontend/src")
    if not frontend_dir.exists():
        print("❌ Директория frontend/src не найдена")
        return
    
    code_content = []
    
    # Сканируем все TypeScript/JavaScript файлы
    for ext in ["*.ts", "*.tsx", "*.js", "*.jsx"]:
        for file_path in frontend_dir.rglob(ext):
            relative_path = file_path.relative_to(frontend_dir)
            code_content.append(f"\n// ===== {relative_path} =====\n")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    code_content.append(content)
            except Exception as e:
                code_content.append(f"// Ошибка чтения файла: {e}")
    
    # Записываем в front.txt
    with open("front.txt", "w", encoding="utf-8") as f:
        f.write("".join(code_content))
    
    print("✅ Код фронтенда сгенерирован в front.txt")

def generate_devops_code():
    """Генерирует DevOps код (Dockerfile'ы и docker-compose)"""
    devops_content = []
    
    # Dockerfile'ы
    devops_content.append("# ===== Dockerfile'ы =====\n\n")
    
    # API Dockerfile
    devops_content.append("## API Dockerfile\n\n")
    api_dockerfile = """FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование requirements
COPY docker/api/requirements-api.txt ./requirements.txt

# Установка Python зависимостей
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Копирование кода приложения
COPY backend/app/ ./app/
COPY backend/alembic.ini ./
COPY backend/scripts/ ./scripts/

# Создание пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

USER appuser

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
    devops_content.append(api_dockerfile)
    devops_content.append("\n\n")
    
    # Worker Dockerfile
    devops_content.append("## Worker Dockerfile\n\n")
    worker_dockerfile = """FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    libffi-dev \\
    libssl-dev \\
    libxml2-dev \\
    libxslt1-dev \\
    zlib1g-dev \\
    libjpeg-dev \\
    libpng-dev \\
    tesseract-ocr \\
    tesseract-ocr-rus \\
    poppler-utils \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование requirements
COPY docker/worker/requirements-worker.txt ./requirements.txt

# Установка Python зависимостей
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Копирование кода приложения
COPY backend/app/ ./app/
COPY backend/alembic.ini ./
COPY backend/scripts/ ./scripts/

# Создание пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

USER appuser

# Запуск worker
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
"""
    devops_content.append(worker_dockerfile)
    devops_content.append("\n\n")
    
    # Embedding Dockerfile
    devops_content.append("## Embedding Dockerfile\n\n")
    embedding_dockerfile = """FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование requirements
COPY docker/emb/requirements-emb.txt ./requirements.txt

# Установка Python зависимостей
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Копирование кода приложения
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/

# Создание пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

USER appuser

# Запуск embedding сервиса
CMD ["python", "scripts/run_embedding_service.py"]
"""
    devops_content.append(embedding_dockerfile)
    devops_content.append("\n\n")
    
    # LLM Dockerfile
    devops_content.append("## LLM Dockerfile\n\n")
    llm_dockerfile = """FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование requirements
COPY docker/llm/requirements-llm.txt ./requirements.txt

# Установка Python зависимостей
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Копирование кода приложения
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/

# Создание пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

USER appuser

# Запуск LLM сервиса
CMD ["python", "scripts/run_llm_service.py"]
"""
    devops_content.append(llm_dockerfile)
    devops_content.append("\n\n")
    
    # Frontend Dockerfile
    devops_content.append("## Frontend Dockerfile\n\n")
    frontend_dockerfile = """FROM node:18-alpine AS builder

WORKDIR /app

# Копирование package.json и package-lock.json
COPY frontend/package*.json ./

# Установка зависимостей
RUN npm ci --only=production

# Копирование исходного кода
COPY frontend/ ./

# Сборка приложения
RUN npm run build

# Production stage
FROM nginx:alpine

# Копирование собранного приложения
COPY --from=builder /app/dist /usr/share/nginx/html

# Копирование конфигурации nginx
COPY docker/frontend/nginx.conf /etc/nginx/nginx.conf

# Создание пользователя
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Запуск nginx
CMD ["nginx", "-g", "daemon off;"]
"""
    devops_content.append(frontend_dockerfile)
    devops_content.append("\n\n")
    
    # Docker Compose файлы
    devops_content.append("# ===== Docker Compose файлы =====\n\n")
    
    # Local compose
    devops_content.append("## docker-compose.local.yml\n\n")
    local_compose = """version: '3.8'

services:
  # База данных
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: ml_portal
      POSTGRES_USER: ml_portal
      POSTGRES_PASSWORD: ml_portal
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_portal"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Qdrant
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  # MinIO
  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # API (легкий)
  api:
    build:
      context: .
      dockerfile: docker/api/Dockerfile.api
    environment:
      - DATABASE_URL=postgresql://ml_portal:ml_portal@postgres:5432/ml_portal
      - DB_URL=postgresql://ml_portal:ml_portal@postgres:5432/ml_portal
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
      - S3_ENDPOINT=http://minio:9000
      - S3_ACCESS_KEY=minioadmin
      - S3_SECRET_KEY=minioadmin
      - S3_BUCKET_RAG=rag
      - S3_BUCKET_ANALYSIS=analysis
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - qdrant
      - minio

  # Worker (полный) - 1 экземпляр для тестирования
  worker:
    build:
      context: .
      dockerfile: docker/worker/Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://ml_portal:ml_portal@postgres:5432/ml_portal
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
      - S3_ENDPOINT=http://minio:9000
      - S3_ACCESS_KEY=minioadmin
      - S3_SECRET_KEY=minioadmin
      - S3_BUCKET_RAG=rag
      - S3_BUCKET_ANALYSIS=analysis
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Embedding сервис
  emb:
    build:
      context: .
      dockerfile: docker/emb/Dockerfile.emb
    environment:
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
    depends_on:
      redis:
        condition: service_healthy

  # LLM сервис
  llm:
    build:
      context: .
      dockerfile: docker/llm/Dockerfile.llm
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      redis:
        condition: service_healthy

  # Frontend
  frontend:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - api

volumes:
  postgres_data:
  qdrant_data:
  minio_data:
"""
    devops_content.append(local_compose)
    devops_content.append("\n\n")
    
    # Production compose
    devops_content.append("## docker-compose.prod.yml\n\n")
    prod_compose = """version: '3.8'

services:
  # База данных
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-ml_portal}
      POSTGRES_USER: ${POSTGRES_USER:-ml_portal}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - ml_portal_network
    deploy:
      placement:
        constraints:
          - node.role == manager
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ml_portal}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis
  redis:
    image: redis:7-alpine
    networks:
      - ml_portal_network
    deploy:
      placement:
        constraints:
          - node.role == manager
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Qdrant
  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - ml_portal_network
    deploy:
      placement:
        constraints:
          - node.role == manager

  # MinIO
  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    networks:
      - ml_portal_network
    deploy:
      placement:
        constraints:
          - node.role == manager
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # API (легкий)
  api:
    image: ml-portal-api:latest
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-ml_portal}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-ml_portal}
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
      - S3_ENDPOINT=http://minio:9000
      - S3_ACCESS_KEY=${MINIO_ROOT_USER:-minioadmin}
      - S3_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - S3_BUCKET_RAG=rag
      - S3_BUCKET_ANALYSIS=analysis
      - JWT_SECRET=${JWT_SECRET}
    networks:
      - ml_portal_network
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          cpus: '1'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
    depends_on:
      - postgres
      - redis
      - qdrant
      - minio

  # Worker-RAG (легкая ВМ)
  worker-rag:
    image: ml-portal-worker:latest
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-ml_portal}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-ml_portal}
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
      - S3_ENDPOINT=http://minio:9000
      - S3_ACCESS_KEY=${MINIO_ROOT_USER:-minioadmin}
      - S3_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - S3_BUCKET_RAG=rag
      - S3_BUCKET_ANALYSIS=analysis
      - CELERY_QUEUES=rag_low,cleanup_low
    networks:
      - ml_portal_network
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.labels.worker_type == light
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Worker-Mixed (тяжелые ВМ)
  worker-mixed:
    image: ml-portal-worker:latest
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-ml_portal}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-ml_portal}
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
      - S3_ENDPOINT=http://minio:9000
      - S3_ACCESS_KEY=${MINIO_ROOT_USER:-minioadmin}
      - S3_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - S3_BUCKET_RAG=rag
      - S3_BUCKET_ANALYSIS=analysis
      - CELERY_QUEUES=chat_critical,upload_high,analyze_medium,ocr_medium
    networks:
      - ml_portal_network
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.labels.worker_type == heavy
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Embedding сервис
  emb:
    image: ml-portal-emb:latest
    environment:
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
    networks:
      - ml_portal_network
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.labels.worker_type == heavy
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    depends_on:
      redis:
        condition: service_healthy

  # LLM сервис
  llm:
    image: ml-portal-llm:latest
    environment:
      - REDIS_URL=redis://redis:6379
    networks:
      - ml_portal_network
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.labels.worker_type == heavy
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
    depends_on:
      redis:
        condition: service_healthy

  # Frontend
  frontend:
    image: ml-portal-frontend:latest
    networks:
      - ml_portal_network
    deploy:
      replicas: 2
      placement:
        constraints:
          - node.role == manager
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
    depends_on:
      - api

volumes:
  postgres_data:
    driver: local
  qdrant_data:
    driver: local
  minio_data:
    driver: local

networks:
  ml_portal_network:
    driver: overlay
    attachable: true
"""
    devops_content.append(prod_compose)
    devops_content.append("\n\n")
    
    # Nginx конфигурация
    devops_content.append("# ===== Nginx конфигурация =====\n\n")
    nginx_config = """events {
    worker_connections 1024;
}

http {
    upstream api_backend {
        server api:8000;
    }
    
    upstream frontend_backend {
        server frontend:80;
    }
    
    server {
        listen 80;
        server_name localhost;
        
        # API прокси
        location /api/ {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Frontend
        location / {
            proxy_pass http://frontend_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
"""
    devops_content.append(nginx_config)
    devops_content.append("\n\n")
    
    # Requirements файлы
    devops_content.append("# ===== Requirements файлы =====\n\n")
    
    # API requirements
    devops_content.append("## docker/api/requirements-api.txt\n\n")
    api_requirements = """fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
alembic==1.12.1
psycopg[binary]==3.1.13
redis==5.0.1
celery==5.3.4
pydantic==2.5.0
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
argon2-cffi==23.1.0
minio==7.2.0
qdrant-client==1.7.0
prometheus-client==0.19.0
structlog==23.2.0
"""
    devops_content.append(api_requirements)
    devops_content.append("\n\n")
    
    # Worker requirements
    devops_content.append("## docker/worker/requirements-worker.txt\n\n")
    worker_requirements = """fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
alembic==1.12.1
psycopg[binary]==3.1.13
redis==5.0.1
celery==5.3.4
pydantic==2.5.0
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
argon2-cffi==23.1.0
minio==7.2.0
qdrant-client==1.7.0
prometheus-client==0.19.0
structlog==23.2.0
# ML и обработка документов
transformers==4.36.0
torch==2.1.0
sentence-transformers==2.2.2
langchain==0.0.350
langchain-community==0.0.10
openai==1.3.7
# OCR и обработка документов
pytesseract==0.3.10
pdfplumber==0.10.3
python-docx==1.1.0
openpyxl==3.1.2
Pillow==10.1.0
# Дополнительные зависимости
numpy==1.24.3
pandas==2.1.4
scikit-learn==1.3.2
"""
    devops_content.append(worker_requirements)
    devops_content.append("\n\n")
    
    # Embedding requirements
    devops_content.append("## docker/emb/requirements-emb.txt\n\n")
    emb_requirements = """fastapi==0.104.1
uvicorn[standard]==0.24.0
redis==5.0.1
qdrant-client==1.7.0
transformers==4.36.0
torch==2.1.0
sentence-transformers==2.2.2
numpy==1.24.3
"""
    devops_content.append(emb_requirements)
    devops_content.append("\n\n")
    
    # LLM requirements
    devops_content.append("## docker/llm/requirements-llm.txt\n\n")
    llm_requirements = """fastapi==0.104.1
uvicorn[standard]==0.24.0
redis==5.0.1
transformers==4.36.0
torch==2.1.0
langchain==0.0.350
langchain-community==0.0.10
openai==1.3.7
"""
    devops_content.append(llm_requirements)
    devops_content.append("\n\n")
    
    # Записываем DevOps код
    with open("devops.txt", "w", encoding="utf-8") as f:
        f.write("".join(devops_content))
    
    print("✅ DevOps код сгенерирован в devops.txt")

def generate_documentation():
    """Генерирует документацию проекта"""
    doc_content = []
    
    doc_content.append("# ML Portal - Архитектура и Логика Работы\n")
    doc_content.append("=" * 60 + "\n\n")
    
    # Общая архитектура
    doc_content.append("## Общая Архитектура\n\n")
    doc_content.append("ML Portal состоит из следующих компонентов:\n\n")
    doc_content.append("### Контейнеры\n")
    doc_content.append("- **API** (легкий) - HTTP API, аутентификация, координация\n")
    doc_content.append("- **Worker** (тяжелый) - обработка документов, ML задачи\n")
    doc_content.append("- **Embedding** - создание эмбеддингов\n")
    doc_content.append("- **LLM** - генерация ответов\n")
    doc_content.append("- **PostgreSQL** - основная БД\n")
    doc_content.append("- **Redis** - кэш и брокер сообщений\n")
    doc_content.append("- **Qdrant** - векторная БД\n")
    doc_content.append("- **MinIO** - файловое хранилище\n\n")
    
    # Система очередей
    doc_content.append("## Система Очередей Celery\n\n")
    doc_content.append("### Очереди по приоритетам\n\n")
    doc_content.append("#### Критический приоритет (priority=10)\n")
    doc_content.append("- **chat_critical** - обработка сообщений чата\n")
    doc_content.append("  - `app.tasks.chat.process_message`\n")
    doc_content.append("  - `app.tasks.chat.generate_response`\n")
    doc_content.append("  - Воркеры: 3-4 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Высокий приоритет (priority=8)\n")
    doc_content.append("- **upload_high** - загрузка и нормализация файлов\n")
    doc_content.append("  - `app.tasks.upload_watch.*`\n")
    doc_content.append("  - `app.tasks.normalize.normalize`\n")
    doc_content.append("  - `app.tasks.chunk.split`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Средний приоритет (priority=5)\n")
    doc_content.append("- **analyze_medium** - анализ документов\n")
    doc_content.append("  - `app.tasks.analyze.*`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    doc_content.append("- **ocr_medium** - OCR и извлечение таблиц\n")
    doc_content.append("  - `app.tasks.ocr_tables.*`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Низкий приоритет (priority=2-1)\n")
    doc_content.append("- **rag_low** - RAG индексация\n")
    doc_content.append("  - `app.tasks.embed.*`\n")
    doc_content.append("  - `app.tasks.index.*`\n")
    doc_content.append("  - Воркеры: 1-2 на легкой ВМ\n\n")
    doc_content.append("- **cleanup_low** - очистка\n")
    doc_content.append("  - `app.tasks.delete.*`\n")
    doc_content.append("  - Воркеры: 1 на легкой ВМ\n\n")
    
    # Распределение по ВМ
    doc_content.append("## Распределение по ВМ\n\n")
    doc_content.append("### Легкая ВМ (6 CPU, 43GB RAM, много HDD)\n")
    doc_content.append("- API (1 контейнер)\n")
    doc_content.append("- PostgreSQL, Redis, Qdrant, MinIO\n")
    doc_content.append("- Worker-RAG (1 воркер) - только RAG задачи\n")
    doc_content.append("- Frontend\n\n")
    
    doc_content.append("### Тяжелые ВМ (12 CPU, 86GB RAM) - 2 ВМ\n")
    doc_content.append("**На каждой ВМ:**\n")
    doc_content.append("- Worker-Mixed (2 воркера) - чат + анализ\n")
    doc_content.append("- Embedding (1 сервис)\n")
    doc_content.append("- LLM (1 сервис)\n\n")
    
    # Потоки данных
    doc_content.append("## Потоки Данных\n\n")
    doc_content.append("### 1. Загрузка документа\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> MinIO\n")
    doc_content.append("API -> upload_watch (upload_high) -> normalize (upload_high)\n")
    doc_content.append("normalize -> chunk (upload_high) -> embed (rag_low)\n")
    doc_content.append("embed -> index (rag_low) -> Qdrant\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### 2. Анализ документа\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> analyze (analyze_medium)\n")
    doc_content.append("analyze -> ocr_tables (ocr_medium) -> результат\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### 3. Чат с RAG\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> process_message (chat_critical)\n")
    doc_content.append("process_message -> RAG search -> generate_response (chat_critical)\n")
    doc_content.append("generate_response -> LLM -> ответ\n")
    doc_content.append("```\n\n")
    
    # Метрики
    doc_content.append("## Метрики и Мониторинг\n\n")
    doc_content.append("### RAG метрики\n")
    doc_content.append("- `rag_ingest_stage_duration_seconds` - время на стадии инжеста\n")
    doc_content.append("- `rag_ingest_errors_total` - ошибки инжеста\n")
    doc_content.append("- `rag_vectors_total` - общее количество векторов\n")
    doc_content.append("- `rag_chunks_total` - общее количество чанков\n")
    doc_content.append("- `rag_search_latency_seconds` - задержка поиска\n")
    doc_content.append("- `rag_quality_mrr` - качество поиска (MRR@K)\n\n")
    
    doc_content.append("### Чат метрики\n")
    doc_content.append("- `chat_rag_usage_total` - использование RAG в чате\n")
    doc_content.append("- `chat_rag_fallback_total` - fallback без RAG\n\n")
    
    # Конфигурация
    doc_content.append("## Конфигурация\n\n")
    doc_content.append("### Переменные окружения\n")
    doc_content.append("- `DATABASE_URL` - подключение к PostgreSQL\n")
    doc_content.append("- `REDIS_URL` - подключение к Redis\n")
    doc_content.append("- `QDRANT_URL` - подключение к Qdrant\n")
    doc_content.append("- `S3_ENDPOINT` - MinIO endpoint\n")
    doc_content.append("- `S3_BUCKET_RAG` - бакет для RAG документов\n")
    doc_content.append("- `S3_BUCKET_ANALYSIS` - бакет для анализа\n\n")
    
    doc_content.append("### Docker Compose файлы\n")
    doc_content.append("- `docker-compose.local.yml` - для локальной разработки\n")
    doc_content.append("- `docker-compose.prod.yml` - для продакшна (Docker Swarm)\n\n")
    
    # Команды управления
    doc_content.append("## Команды Управления\n\n")
    doc_content.append("### Локальная разработка\n")
    doc_content.append("```bash\n")
    doc_content.append("make build-local    # Собрать образы\n")
    doc_content.append("make up-local       # Запустить стек\n")
    doc_content.append("make down-local     # Остановить стек\n")
    doc_content.append("make logs           # Показать логи\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### Продакшн\n")
    doc_content.append("```bash\n")
    doc_content.append("make build-prod     # Собрать образы\n")
    doc_content.append("make up-prod        # Запустить стек\n")
    doc_content.append("make down-prod      # Остановить стек\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### Генерация кода\n")
    doc_content.append("```bash\n")
    doc_content.append("make gen-backend    # Код бэкенда\n")
    doc_content.append("make gen-frontend   # Код фронтенда\n")
    doc_content.append("make gen-all        # Весь код\n")
    doc_content.append("make gen-docs       # Документация\n")
    doc_content.append("```\n\n")
    
    # Записываем документацию
    with open("PROJECT_ARCHITECTURE.md", "w", encoding="utf-8") as f:
        f.write("".join(doc_content))
    
    print("✅ Документация сгенерирована в PROJECT_ARCHITECTURE.md")

def main():
    parser = argparse.ArgumentParser(description="Генератор кода и документации ML Portal")
    parser.add_argument("target", choices=["backend", "frontend", "devops", "all", "docs"], 
                       help="Что генерировать")
    
    args = parser.parse_args()
    
    if args.target == "backend":
        generate_backend_code()
    elif args.target == "frontend":
        generate_frontend_code()
    elif args.target == "devops":
        generate_devops_code()
    elif args.target == "all":
        generate_backend_code()
        generate_frontend_code()
        generate_devops_code()
    elif args.target == "docs":
        generate_documentation()

if __name__ == "__main__":
    main()
