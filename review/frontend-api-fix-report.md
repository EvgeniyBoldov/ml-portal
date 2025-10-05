# Отчет о решении проблемы с отправкой сообщений

## 🔍 Проблема
Фронтенд не мог отправить сообщения в чат. В логах nginx было видно:
```
POST /api/v1/chats/550e8400-e29b-41d4-a716-446655440001/messages HTTP/1.1" 404
```

## 🔍 Анализ проблемы
1. **Фронтенд отправлял запросы на неправильный порт**: `localhost:8080` вместо `localhost:80`
2. **API_BASE был настроен неправильно**: `http://localhost:8000/api/v1` вместо `/api/v1`
3. **nginx на порту 8080 не проксировал API запросы**: только фронтенд, без API

## ✅ Решение

### 1. Исправлен API_BASE в фронтенде
**Файл**: `apps/web/src/shared/config/env.ts`
```typescript
// Было:
export const API_BASE: string = 'http://localhost:8000/api/v1';

// Стало:
export const API_BASE: string = '/api/v1';
```

### 2. Добавлено проксирование API на порт 8080
**Файл**: `infra/nginx/dev.conf`
```nginx
# Добавлено в server блок для порта 8080:
location /api/ {
    proxy_pass http://api:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Preserve original request path
    proxy_redirect off;
    proxy_buffering off;
}
```

### 3. Перезапущены сервисы
- Перезапущен фронтенд для применения изменений API_BASE
- Перезапущен nginx для применения новой конфигурации

## ✅ Результат
Теперь фронтенд:
1. Отправляет запросы на `/api/v1/` (относительный путь)
2. nginx на порту 8080 проксирует API запросы к бэкенду
3. UUID чатов работают корректно
4. Отправка сообщений должна работать

## 🧪 Тестирование
После изменений фронтенд должен:
- Авторизоваться через `/api/v1/auth/login`
- Получать список чатов через `/api/v1/chats`
- Отправлять сообщения через `/api/v1/chats/{uuid}/messages`

Все запросы теперь проходят через nginx на порту 8080 и проксируются к API.
