# Деплой

## Требования

### Сервер
- Ubuntu 22.04+ / Debian 12+
- Docker 24+
- Docker Compose v2
- 16GB RAM минимум
- GPU (опционально, для локальных моделей)

### Домен
- SSL сертификат (Let's Encrypt или свой)
- DNS записи настроены

## Процесс деплоя

### 1. Подготовка сервера

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose
sudo apt install docker-compose-plugin

# Перелогиниться для применения групп
exit
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/your-org/ml-portal.git
cd ml-portal
```

### 3. Конфигурация

```bash
# Копирование примера
cp .env.example .env

# Редактирование
nano .env
```

**Обязательные переменные:**
```bash
# Database
POSTGRES_USER=mlportal
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=mlportal

# Security
JWT_SECRET=<random-64-chars>
CREDENTIALS_MASTER_KEY=<fernet-key>

# MinIO
MINIO_ROOT_USER=<username>
MINIO_ROOT_PASSWORD=<strong-password>

# LLM (если внешний)
LLM_API_KEY=<api-key>
LLM_BASE_URL=https://api.groq.com/openai/v1
```

### 4. SSL сертификаты

```bash
# Let's Encrypt
sudo apt install certbot
sudo certbot certonly --standalone -d your-domain.com

# Копирование в проект
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infra/nginx/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem infra/nginx/certs/
```

### 5. Запуск

```bash
# Production compose
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Проверка
docker compose ps
docker compose logs -f
```

### 6. Миграции

```bash
docker compose exec api alembic upgrade head
```

### 7. Суперюзер

```bash
docker compose exec api python -m app.scripts.create_superuser
```

## Production Compose

```yaml
# docker-compose.prod.yml
services:
  api:
    restart: always
    environment:
      - DEBUG=false
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
  
  web:
    restart: always
    environment:
      - NODE_ENV=production
  
  worker:
    restart: always
    deploy:
      replicas: 2
  
  postgres:
    restart: always
  
  redis:
    restart: always
  
  qdrant:
    restart: always
  
  minio:
    restart: always
  
  nginx:
    restart: always
```

## Обновление

```bash
# Получение изменений
git pull origin main

# Пересборка образов
docker compose build

# Применение миграций
docker compose exec api alembic upgrade head

# Перезапуск с zero-downtime
docker compose up -d --no-deps api
docker compose up -d --no-deps worker
docker compose up -d --no-deps web
```

## Rollback

```bash
# Откат к предыдущему коммиту
git checkout HEAD~1

# Пересборка
docker compose build

# Откат миграций (если нужно)
docker compose exec api alembic downgrade -1

# Перезапуск
docker compose up -d
```

## Health Checks

### API
```bash
curl http://localhost:8000/health
```

### Nginx
```bash
curl -I https://your-domain.com
```

### Все сервисы
```bash
docker compose ps
```

## Логи

```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f api

# Последние N строк
docker compose logs --tail=100 api

# С timestamps
docker compose logs -f -t api
```

## Мониторинг

### Prometheus (опционально)

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3001:3000"
```

### Метрики API
```bash
curl http://localhost:8000/metrics
```

## Troubleshooting

### Сервис не запускается

```bash
# Проверить логи
docker compose logs <service>

# Проверить ресурсы
docker stats

# Проверить сеть
docker network ls
docker network inspect ml-portal_default
```

### Нет доступа к API

```bash
# Проверить nginx
docker compose logs nginx

# Проверить firewall
sudo ufw status

# Проверить порты
sudo netstat -tlnp | grep -E '80|443|8000'
```

### База данных недоступна

```bash
# Проверить статус
docker compose ps postgres

# Проверить подключение
docker compose exec api python -c "from app.core.database import engine; print('OK')"
```
