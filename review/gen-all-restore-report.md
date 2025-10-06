# Отчет о восстановлении команды gen-all

## Выполненная задача

### ✅ Восстановлена команда `make gen-all`
- Добавлена команда `gen-all` в Makefile
- Команда использует существующий скрипт `scripts/generate-code-docs.py`
- Обновлена справка в `make help`

## Что делает команда

При выполнении `make gen-all` генерируются 4 монолитных файла с кодом:

1. **`code-docs-backend.txt`** (419 KB) - Код бэкенда
   - Python файлы из `apps/api`, `apps/emb`, `apps/llm`
   - Исключает `__pycache__`, миграции, тесты

2. **`code-docs-frontend.txt`** (1.03 MB) - Код фронтенда  
   - TypeScript, React, CSS файлы из `apps/web`
   - Исключает `node_modules`, `dist`, `build`

3. **`code-docs-infrastructure.txt`** (63 KB) - Инфраструктура
   - Docker файлы, конфигурации, скрипты
   - `infra/`, `docker-compose.*`, `Makefile`, `env.example`

4. **`code-docs-tests.txt`** (333 KB) - Тесты
   - Python тесты из `apps/api/src/app/tests`
   - Исключает `__pycache__`, `node_modules`

## Особенности

- **Ограничение размера**: Файлы больше 10KB обрезаются до первых 200 строк
- **Кодировка**: UTF-8 с обработкой ошибок
- **Структура**: Каждый файл содержит полный код с путями и размерами
- **Исключения**: Автоматически исключаются служебные файлы и директории

## Использование

```bash
make gen-all
```

Команда готова к использованию! 🎉
