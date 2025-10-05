# Замечания по DevOps/Nginx - проблемы с конфигурацией

## Проблемы с nginx конфигурацией

### 1. Несоответствие путей API между dev и prod
- **Dev конфиг** (`infra/nginx/dev.conf:60`): `location /api/` → `proxy_pass http://api:8000`
- **Prod конфиг** (`infra/nginx/prod.conf:22`): `location /api/v1/` → `proxy_pass http://api:8000`
- **Проблема**: Разные пути для API в dev и prod окружениях

**Решение**: Унифицировать пути API в обоих конфигурациях

### 2. Проблема с CORS в prod
- **Dev конфиг**: `Access-Control-Allow-Origin "*"` (разрешает все)
- **Prod конфиг**: `Access-Control-Allow-Origin "$http_origin"` (только текущий origin)
- **Проблема**: В prod может блокироваться доступ с фронтенда

**Решение**: Проверить, что фронтенд и API находятся на одном домене в prod

### 3. Отсутствие поддержки WebSocket в prod
- **Dev конфиг**: Есть поддержка WebSocket для Vite HMR
- **Prod конфиг**: Отсутствует поддержка WebSocket
- **Проблема**: Если фронтенд использует WebSocket в prod, соединения будут падать

### 4. Разные настройки проксирования
- **Dev конфиг**: Детальные настройки проксирования с таймаутами
- **Prod конфиг**: Минимальные настройки проксирования
- **Проблема**: Возможны проблемы с долгими запросами в prod

### 5. Отсутствие health checks в prod
- **Dev конфиг**: Есть `/readyz`, `/health`, `/healthz`
- **Prod конфиг**: Отсутствуют health checks
- **Проблема**: Нет возможности мониторить состояние API в prod

## Рекомендации по исправлению

### Приоритет 1 (Критический)
1. **Унифицировать пути API** - использовать одинаковые пути в dev и prod
2. **Проверить CORS настройки** - убедиться, что фронтенд может обращаться к API
3. **Добавить health checks в prod** - для мониторинга

### Приоритет 2 (Высокий)
1. **Добавить поддержку WebSocket в prod** (если необходимо)
2. **Унифицировать настройки проксирования** - использовать одинаковые таймауты и настройки
3. **Добавить логирование** - для отладки проблем

### Приоритет 3 (Средний)
1. **Добавить rate limiting** - для защиты от DDoS
2. **Настроить SSL/TLS** - для HTTPS в prod
3. **Добавить мониторинг** - метрики nginx

## Технические замечания

### Конфигурация API путей
```nginx
# Рекомендуемая конфигурация для обоих окружений
location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Таймауты для долгих запросов
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 60s;
}
```

### Health checks
```nginx
# Добавить в prod конфиг
location /health {
    proxy_pass http://api:8000/health;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location /readyz {
    proxy_pass http://api:8000/readyz;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

### CORS настройки
```nginx
# Для prod - более строгие настройки
add_header Access-Control-Allow-Origin "https://yourdomain.com" always;
add_header Access-Control-Allow-Credentials true always;
```

## Дополнительные рекомендации

### Безопасность
- Настроить SSL/TLS сертификаты
- Добавить rate limiting
- Настроить firewall правила
- Использовать HTTPS в prod

### Мониторинг
- Настроить логирование nginx
- Добавить метрики Prometheus
- Настроить алерты
- Мониторить производительность

### Производительность
- Настроить кэширование статических файлов
- Оптимизировать настройки проксирования
- Настроить сжатие gzip
- Оптимизировать размеры буферов
