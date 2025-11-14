FROM nginx:alpine

# Устанавливаем wget для health check
RUN apk add --no-cache wget

# Создаем директории для логов
RUN mkdir -p /var/log/nginx

# Копируем конфигурации
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx.prod.conf /etc/nginx/nginx.prod.conf

# Создаем скрипт для выбора конфигурации
RUN echo '#!/bin/sh' > /docker-entrypoint.d/select-config.sh && \
    echo 'if [ "$ENVIRONMENT" = "production" ]; then' >> /docker-entrypoint.d/select-config.sh && \
    echo '  cp /etc/nginx/nginx.prod.conf /etc/nginx/nginx.conf' >> /docker-entrypoint.d/select-config.sh && \
    echo 'fi' >> /docker-entrypoint.d/select-config.sh && \
    chmod +x /docker-entrypoint.d/select-config.sh

# Открываем порты
EXPOSE 80 443

# Запускаем nginx
CMD ["nginx", "-g", "daemon off;"]
