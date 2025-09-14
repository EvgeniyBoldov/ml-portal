# Быстрый старт: Новая система эмбеддингов

## 🚀 Запуск за 3 шага

### 1. Сборка и запуск
```bash
# Собрать образы
make build-local

# Запустить все сервисы
make up-local
```

### 2. Инициализация MinIO
```bash
# Создать бакет для моделей
make init-models
```

### 3. Тестирование
```bash
# Демонстрация работы
make demo-embedding

# Или простой тест
make test-embedding
```

## 📊 Что получили

✅ **Model Registry** - реестр моделей в Redis  
✅ **Embedding Dispatcher** - маршрутизатор задач  
✅ **Embedding Worker** - воркер с кэшированием из MinIO  
✅ **RT/BULK профили** - разные очереди для разных задач  
✅ **Fallback** - автоматический откат на HTTP API  
✅ **Простая конфигурация** - через переменные окружения  

## 🔧 Конфигурация

Модели настраиваются через переменные в `docker-compose.local.yml`:

```yaml
environment:
  - EMB_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
  - EMB_MODEL_ALIAS=minilm
  - EMB_DIM=384
  - EMB_MAX_SEQ=256
```

## 📝 Использование

```python
from app.services.clients import embed_texts

# Быстрый режим (RT)
vectors = embed_texts(["Hello world"], profile="rt")

# Массовый режим (BULK)  
vectors = embed_texts(["Hello world"], profile="bulk")
```

## 🐛 Отладка

```bash
# Логи embedding worker
make logs-embedding

# Статус всех сервисов
make status

# Перезапуск только embedding worker
docker-compose -f docker-compose.local.yml restart embedding-worker
```

## 📈 Мониторинг

- **Health check**: `curl http://localhost:8001/health`
- **Логи**: `make logs-embedding`
- **Статус**: `make status`

## 🎯 Следующие шаги

1. Добавить больше моделей через переменные окружения
2. Настроить GPU поддержку
3. Добавить метрики Prometheus
4. Создать админку для управления моделями

---

**Готово!** 🎉 Система эмбеддингов работает и интегрирована в ваш RAG.
