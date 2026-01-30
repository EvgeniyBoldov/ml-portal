# SSL/TLS Сертификаты

## Let's Encrypt (рекомендуется)

### Установка Certbot

```bash
sudo apt update
sudo apt install certbot
```

### Получение сертификата

```bash
# Standalone (требует остановки nginx)
sudo certbot certonly --standalone -d your-domain.com

# Webroot (nginx работает)
sudo certbot certonly --webroot -w /var/www/html -d your-domain.com
```

### Копирование в проект

```bash
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infra/nginx/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem infra/nginx/certs/
sudo chown $USER:$USER infra/nginx/certs/*.pem
```

### Автообновление

```bash
# Проверка
sudo certbot renew --dry-run

# Cron job (добавляется автоматически)
# 0 0,12 * * * root certbot renew --quiet
```

### Hook для перезапуска nginx

```bash
# /etc/letsencrypt/renewal-hooks/deploy/restart-nginx.sh
#!/bin/bash
cd /path/to/ml-portal
docker compose restart nginx
```

```bash
chmod +x /etc/letsencrypt/renewal-hooks/deploy/restart-nginx.sh
```

## Самоподписанный сертификат (dev)

```bash
# Создание
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infra/nginx/certs/privkey.pem \
  -out infra/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
```

## Nginx конфигурация

```nginx
# infra/nginx/nginx.conf
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    
    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;
    
    # API
    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # SSE
    location /api/v1/sse {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
    
    # Frontend
    location / {
        proxy_pass http://web:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Cookie настройки

### httpOnly Refresh Token

```python
# apps/api/src/app/api/v1/auth.py
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=True,  # Только HTTPS
    samesite="lax",
    max_age=60 * 60 * 24 * 7,  # 7 дней
    path="/api/v1/auth/refresh"
)
```

### TTL настройки

```bash
# .env
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Проверка

### SSL Labs

https://www.ssllabs.com/ssltest/analyze.html?d=your-domain.com

### OpenSSL

```bash
# Проверка сертификата
openssl s_client -connect your-domain.com:443 -servername your-domain.com

# Проверка срока действия
echo | openssl s_client -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates
```

### Curl

```bash
curl -I https://your-domain.com
```

## Troubleshooting

### Сертификат не найден

```bash
# Проверить наличие файлов
ls -la infra/nginx/certs/

# Проверить права
chmod 644 infra/nginx/certs/fullchain.pem
chmod 600 infra/nginx/certs/privkey.pem
```

### Mixed Content

Убедиться, что все ресурсы загружаются по HTTPS:
- `VITE_API_URL=https://your-domain.com`
- Все внешние скрипты/стили по HTTPS

### CORS ошибки

```nginx
# Добавить в nginx.conf
location /api {
    add_header Access-Control-Allow-Origin $http_origin always;
    add_header Access-Control-Allow-Credentials true always;
    add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    
    if ($request_method = OPTIONS) {
        return 204;
    }
    
    proxy_pass http://api:8000;
}
```
