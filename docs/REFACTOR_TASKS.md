# ML Portal Refactoring Tasks

## 🎯 Цель рефакторинга
Консолидация API архитектуры: один входной файл, единый стиль хэндлеров, четкое разделение слоев.

## 📋 Чеклист задач

### ✅ Этап 1: Консолидация входной точки
- [x] **1.1** Merge main_enhanced → main
- [x] **1.2** Убедиться что все роутеры импортируются из routers/*
- [x] **1.3** Тесты: pytest -k health зеленый
- [x] **1.4** E2E: поднимается и отвечает /health

### ✅ Этап 2: Консолидация HTTP слоя
- [ ] **2.1** Move controllers/chats → routers/chats
- [ ] **2.2** Move controllers/rag → routers/rag
- [ ] **2.3** Move controllers/users → routers/users
- [ ] **2.4** Обновить тесты роутеров
- [ ] **2.5** Убедиться что логика только делегирует в сервисы

### ✅ Этап 3: Сервисный слой
- [ ] **3.1** Extract ChatService (+tests)
- [ ] **3.2** Extract RagIngestService (+tests)
- [ ] **3.3** Extract RagSearchService (+tests)
- [ ] **3.4** Extract AnalyzeService (+tests)
- [ ] **3.5** Extract AuthService (+tests)
- [ ] **3.6** Create ModelCatalog (+tests)

### ✅ Этап 4: Унификация ingestion
- [ ] **4.1** Unify rag_search into rag
- [ ] **4.2** Создать единый конвейер разборки/индексации
- [ ] **4.3** AnalyzeService переиспользует RAG pipeline
- [ ] **4.4** Unit тесты с моками
- [ ] **4.5** Integration тесты через compose.test

### ✅ Этап 5: Провайдеры LLM/Embeddings
- [ ] **5.1** Add LLMClient facade (+tests)
- [ ] **5.2** Add EmbClient facade (+tests)
- [ ] **5.3** Локальные HF модели без интернета
- [ ] **5.4** Конфиги для локальных весов
- [ ] **5.5** Тесты с tiny-моделями

### ✅ Этап 6: Чистка дублей
- [ ] **6.1** Delete main_enhanced.py
- [ ] **6.2** Delete controllers/* (после переноса)
- [ ] **6.3** Delete rag_search.py (после мержа)
- [ ] **6.4** Проверить setup.py и password_reset.py
- [ ] **6.5** Убедиться что все тесты зеленые

### ✅ Этап 7: RBAC + админ
- [ ] **7.1** Seed superuser (+tests)
- [ ] **7.2** RBAC минимальный (+tests)
- [ ] **7.3** Скрипт create_superuser.py
- [ ] **7.4** Makefile цель seed-admin
- [ ] **7.5** Integration тесты авторизации

### ✅ Этап 8: Тестовая дисциплина
- [ ] **8.1** Обновить pytest.ini с маркерами
- [ ] **8.2** Добавить make test (быстрый)
- [ ] **8.3** Добавить make test-all (полный)
- [ ] **8.4** Добавить make seed-admin
- [ ] **8.5** Убедиться что CI работает

### ✅ Этап 9: Документация
- [ ] **9.1** Обновить README с новыми командами
- [ ] **9.2** Обновить Makefile targets
- [ ] **9.3** Создать архитектурную диаграмму
- [ ] **9.4** Обновить API документацию

## 🚀 Команды для работы

### Запуск тестового окружения
```bash
docker compose -f docker-compose.test.yml up -d --build
docker compose -f docker-compose.test.yml exec api make test
```

### Создание ветки для задачи
```bash
git checkout -b refactor/routers-consolidation-01
```

### Коммит изменений
```bash
make git-auto
```

## 📊 Прогресс
- **Завершено**: 0/45 задач (0%)
- **Текущая ветка**: main
- **Следующая задача**: Merge main_enhanced → main

## 🎯 Критерии готовности
- [ ] Все тесты зеленые
- [ ] E2E тесты проходят
- [ ] Документация обновлена
- [ ] CI/CD работает
- [ ] Код ревью пройден
