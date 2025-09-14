# Примеры использования скриптов

## 🚀 Скачивание конкретной модели

### Базовое использование
```bash
# Скачать модель BAAI/bge-3m
python scripts/download_model.py BAAI/bge-3m

# Скачать с тестированием
python scripts/download_model.py BAAI/bge-3m --test

# Показать информацию о модели
python scripts/download_model.py BAAI/bge-3m --info
```

### Через Makefile
```bash
# Скачать конкретную модель
make download-model MODEL_ID=BAAI/bge-3m

# Скачать с тестированием
make download-model MODEL_ID=BAAI/bge-3m ARGS="--test"

# Скачать с информацией
make download-model MODEL_ID=BAAI/bge-3m ARGS="--info"
```

### Продвинутые опции
```bash
# Скачать только safetensors файлы
python scripts/download_model.py BAAI/bge-3m --include "*.safetensors"

# Исключить большие файлы
python scripts/download_model.py BAAI/bge-3m --exclude "*.bin" "*.h5" "*.onnx"

# Скачать с конкретной ревизией
python scripts/download_model.py BAAI/bge-3m --revision abc123

# Комбинированные опции
python scripts/download_model.py BAAI/bge-3m --test --info --include "*.safetensors"
```

## 📦 Популярные модели для эмбеддингов

### Легкие модели (быстрые)
```bash
# MiniLM - самая легкая
python scripts/download_model.py sentence-transformers/all-MiniLM-L6-v2 --test

# MPNet - хорошее качество
python scripts/download_model.py sentence-transformers/all-mpnet-base-v2 --test
```

### Качественные модели
```bash
# E5 - современная модель
python scripts/download_model.py intfloat/e5-large-v2 --test

# BGE - китайская модель
python scripts/download_model.py BAAI/bge-large-en-v1.5 --test

# BGE-3M - многоязычная
python scripts/download_model.py BAAI/bge-3m --test
```

### Специализированные модели
```bash
# Для русского языка
python scripts/download_model.py cointegrated/rubert-tiny2 --test

# Для кода
python scripts/download_model.py microsoft/codebert-base --test
```

## 🔧 Интеграция с системой эмбеддингов

### 1. Скачать модель
```bash
python scripts/download_model.py BAAI/bge-3m --test
```

### 2. Загрузить в MinIO
```bash
# Скопировать в MinIO бакет
aws s3 cp models/BAAI--bge-3m/ s3://models/BAAI/bge-3m/default/ --recursive
```

### 3. Обновить docker-compose
```yaml
environment:
  - EMB_MODEL_ID=BAAI/bge-3m
  - EMB_MODEL_ALIAS=bge3m
  - EMB_MODEL_REV=default
  - EMB_DIM=1024
  - EMB_MAX_SEQ=512
```

### 4. Перезапустить сервисы
```bash
make down-local
make up-local
```

## 📊 Мониторинг

### Проверить скачанные модели
```bash
# Показать все модели
make list-models

# Проверить размер
du -sh models/*/

# Проверить отчет
cat models/download_report.json | jq '.total_models, .total_size_mb'
```

### Тестирование системы
```bash
# Тест системы эмбеддингов
make demo-embedding

# Логи embedding worker
make logs-embedding
```

## 🐛 Отладка

### Проблемы с памятью
```bash
# Скачать только safetensors
python scripts/download_model.py BAAI/bge-3m --include "*.safetensors"

# Исключить большие файлы
python scripts/download_model.py BAAI/bge-3m --exclude "*.bin" "*.h5" "*.onnx"
```

### Проблемы с сетью
```bash
# Использовать зеркало
export HF_ENDPOINT=https://hf-mirror.com

# Настроить прокси
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
```

### Проблемы с зависимостями
```bash
# Установить зависимости
pip install huggingface_hub transformers torch

# Обновить зависимости
pip install --upgrade huggingface_hub transformers torch
```

## 💡 Советы

### Экономия места
- Используйте `--include "*.safetensors"` для экономии места
- Исключайте `*.bin`, `*.h5`, `*.onnx` файлы
- Скачивайте только нужные модели

### Производительность
- Тестируйте модели с `--test` перед использованием
- Проверяйте размер модели перед скачиванием
- Используйте `--info` для получения информации

### Интеграция
- Всегда указывайте правильные размерности в docker-compose
- Проверяйте совместимость с sentence-transformers
- Тестируйте систему после добавления новой модели
