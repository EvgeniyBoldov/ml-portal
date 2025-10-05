# Отчет о наведении порядка с зависимостями

## Проблема
Был полный бардак с зависимостями:
- Requirements файлы были разбросаны по разным местам
- В `infra/docker/api/` было 5 разных requirements файлов!
- В `apps/api/` тоже были requirements файлы
- Непонятно было, куда добавлять новые зависимости

## Решение
Наведен порядок для каждого сервиса:

### Структура для каждого сервиса:
```
infra/docker/{service}/
├── requirements.txt          # Единый файл зависимостей
├── Dockerfile.prod          # Продакшн контейнер
└── Dockerfile.test          # Тестовый контейнер (с pytest)
```

### Принципы:
1. **Один requirements.txt на сервис** - рядом с Dockerfile
2. **Два Dockerfile** - prod и test
3. **Тестовые зависимости** - только в Dockerfile.test как дополнительный слой
4. **Изоляция зависимостей** - каждый сервис имеет только свои зависимости

## Выполненные изменения

### API сервис:
- ✅ `infra/docker/api/requirements.txt` - единый файл
- ✅ `infra/docker/api/Dockerfile.prod` - продакшн
- ✅ `infra/docker/api/Dockerfile.test` - с pytest
- ✅ Удалены все лишние файлы

### EMB сервис:
- ✅ `infra/docker/emb/requirements.txt` - только для эмбеддингов
- ✅ `infra/docker/emb/Dockerfile.prod` - продакшн
- ✅ `infra/docker/emb/Dockerfile.test` - с pytest
- ✅ Удалены старые файлы

### LLM сервис:
- ✅ `infra/docker/llm/requirements.txt` - минимальные зависимости
- ✅ `infra/docker/llm/Dockerfile.prod` - продакшн
- ✅ `infra/docker/llm/Dockerfile.test` - с pytest
- ✅ Удалены старые файлы

### Worker сервис:
- ✅ `infra/docker/worker/requirements.txt` - все для обработки документов
- ✅ `infra/docker/worker/Dockerfile.prod` - продакшн
- ✅ `infra/docker/worker/Dockerfile.test` - с pytest
- ✅ Удалены старые файлы

## Результат

### ✅ Преимущества:
1. **Понятно, куда добавлять зависимости** - в `infra/docker/{service}/requirements.txt`
2. **Изоляция сервисов** - API не тянет torch, EMB не тянет SQLAlchemy
3. **Чистые контейнеры** - тестовые зависимости только в test контейнерах
4. **Простота сборки** - один файл зависимостей на сервис

### ✅ Структура:
```
infra/docker/
├── api/
│   ├── requirements.txt
│   ├── Dockerfile.prod
│   └── Dockerfile.test
├── emb/
│   ├── requirements.txt
│   ├── Dockerfile.prod
│   └── Dockerfile.test
├── llm/
│   ├── requirements.txt
│   ├── Dockerfile.prod
│   └── Dockerfile.test
└── worker/
    ├── requirements.txt
    ├── Dockerfile.prod
    └── Dockerfile.test
```

## Статус
**ПОРЯДОК НАВЕДЕН!** 

Теперь каждый сервис имеет четкую структуру зависимостей, и понятно, куда добавлять новые библиотеки.
