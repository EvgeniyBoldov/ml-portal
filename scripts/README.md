# Хелпер-скрипты ML Portal

Полезные скрипты для разработки и развертывания ML Portal.

## 📁 Содержимое

### `generate_code.py`
Генератор кода и документации проекта.

**Использование:**
```bash
# Генерация кода бэкенда
python scripts/generate_code.py backend

# Генерация кода фронтенда  
python scripts/generate_code.py frontend

# Генерация всего кода
python scripts/generate_code.py all

# Генерация документации
python scripts/generate_code.py docs
```

**Результат:**
- `back.txt` - весь код бэкенда в одном файле
- `front.txt` - весь код фронтенда в одном файле
- `PROJECT_ARCHITECTURE.md` - архитектурная документация

### `download_models.py`
Скачивание моделей из HuggingFace в локальную директорию.

**Установка зависимостей:**
```bash
pip install huggingface_hub transformers torch
```

**Использование:**
```bash
# Скачать одну модель
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2

# Скачать несколько моделей
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 sentence-transformers/all-mpnet-base-v2

# Скачать с указанием ревизии
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --revision abc123

# Скачать только safetensors файлы
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --include "*.safetensors"

# Исключить pytorch_model.bin
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --exclude "*.bin"

# Тестировать скачанные модели
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --test

# Показать информацию о моделях
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --info

# Указать директорию для сохранения
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --output-dir ./my_models
```

**Результат:**
- `models/` - директория с моделями
- `models/download_report.json` - отчет о скачивании
- `models/*/metadata.json` - метаданные каждой модели

### `download_model.py`
Скачивание конкретной модели из HuggingFace с интерактивным интерфейсом.

**Использование:**
```bash
# Скачать конкретную модель
python scripts/download_model.py BAAI/bge-3m

# Скачать с тестированием
python scripts/download_model.py sentence-transformers/all-MiniLM-L6-v2 --test

# Показать информацию о модели
python scripts/download_model.py intfloat/e5-large-v2 --info

# Скачать только safetensors файлы
python scripts/download_model.py sentence-transformers/all-MiniLM-L6-v2 --include "*.safetensors"

# Исключить большие файлы
python scripts/download_model.py sentence-transformers/all-MiniLM-L6-v2 --exclude "*.bin" "*.h5"

# Скачать с указанием ревизии
python scripts/download_model.py sentence-transformers/all-MiniLM-L6-v2 --revision abc123
```

**Особенности:**
- ✅ Интерактивное подтверждение скачивания
- ✅ Автоматические настройки по умолчанию (safetensors, исключение больших файлов)
- ✅ Показ информации о модели перед скачиванием
- ✅ Примеры интеграции с системой эмбеддингов

## 🚀 Быстрый старт

### 1. Генерация кода
```bash
# Весь код проекта
python scripts/generate_code.py all

# Только документация
python scripts/generate_code.py docs
```

### 2. Скачивание моделей
```bash
# Конкретная модель для эмбеддингов
python scripts/download_model.py BAAI/bge-3m --test --info

# Или через Makefile
make download-model MODEL_ID=BAAI/bge-3m --test

# Несколько моделей
python scripts/download_models.py \
  sentence-transformers/all-MiniLM-L6-v2 \
  sentence-transformers/all-mpnet-base-v2 \
  intfloat/e5-large-v2 \
  --test --info
```

### 3. Интеграция с Makefile
```bash
# Генерация кода (уже есть в Makefile)
make gen-all

# Скачивание моделей (можно добавить в Makefile)
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --test
```

## 📋 Примеры моделей

### Эмбеддинги
- `sentence-transformers/all-MiniLM-L6-v2` - легкая модель (384 dim)
- `sentence-transformers/all-mpnet-base-v2` - качественная модель (768 dim)
- `intfloat/e5-large-v2` - современная модель (1024 dim)
- `BAAI/bge-large-en-v1.5` - китайская модель (1024 dim)

### LLM (для будущего использования)
- `microsoft/DialoGPT-medium` - диалоговая модель
- `microsoft/DialoGPT-large` - большая диалоговая модель
- `Qwen/Qwen2-7B-Instruct` - современная инструкционная модель

## 🔧 Настройка

### Переменные окружения
```bash
# Для HuggingFace Hub
export HF_TOKEN=your_token_here

# Для кэширования моделей
export HF_HOME=./models
export TRANSFORMERS_CACHE=./models
```

### Конфигурация .gitignore
Добавьте в `.gitignore`:
```
# Модели
models/
*.bin
*.safetensors
*.h5
*.onnx
```

## 📊 Мониторинг

### Размер моделей
```bash
# Общий размер директории моделей
du -sh models/

# Размер каждой модели
du -sh models/*/
```

### Проверка целостности
```bash
# Проверить checksums
python -c "
import json
with open('models/download_report.json') as f:
    report = json.load(f)
    print(f'Моделей: {report[\"total_models\"]}')
    print(f'Файлов: {report[\"total_files\"]}')
    print(f'Размер: {report[\"total_size_mb\"]:.1f} MB')
"
```

## 🐛 Отладка

### Проблемы с памятью
```bash
# Скачивать только safetensors
python scripts/download_models.py model_name --include "*.safetensors"

# Исключить большие файлы
python scripts/download_models.py model_name --exclude "*.bin" "*.h5"
```

### Проблемы с сетью
```bash
# Использовать зеркало
export HF_ENDPOINT=https://hf-mirror.com

# Или настроить прокси
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
```

## 📝 Логи

Все скрипты выводят подробную информацию о процессе:
- ✅ Успешные операции
- ❌ Ошибки
- ⚠️ Предупреждения
- 📊 Статистика

Для тихого режима перенаправьте вывод:
```bash
python scripts/download_models.py model_name > download.log 2>&1
```
