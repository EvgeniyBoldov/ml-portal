#!/usr/bin/env python3
"""
Генератор кода и документации для ML Portal
"""
import os
import sys
import argparse
from pathlib import Path

def generate_backend_code():
    """Генерирует код бэкенда в back.txt"""
    backend_dir = Path("backend")
    if not backend_dir.exists():
        print("❌ Директория backend не найдена")
        return
    
    code_content = []
    
    # Сканируем все Python файлы
    for py_file in backend_dir.rglob("*.py"):
        if py_file.name == "__pycache__":
            continue
            
        relative_path = py_file.relative_to(backend_dir)
        code_content.append(f"\n# ===== {relative_path} =====\n")
        
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                code_content.append(content)
        except Exception as e:
            code_content.append(f"# Ошибка чтения файла: {e}")
    
    # Записываем в back.txt
    with open("back.txt", "w", encoding="utf-8") as f:
        f.write("".join(code_content))
    
    print("✅ Код бэкенда сгенерирован в back.txt")

def generate_frontend_code():
    """Генерирует код фронтенда в front.txt"""
    frontend_dir = Path("frontend/src")
    if not frontend_dir.exists():
        print("❌ Директория frontend/src не найдена")
        return
    
    code_content = []
    
    # Сканируем все TypeScript/JavaScript файлы
    for ext in ["*.ts", "*.tsx", "*.js", "*.jsx"]:
        for file_path in frontend_dir.rglob(ext):
            relative_path = file_path.relative_to(frontend_dir)
            code_content.append(f"\n// ===== {relative_path} =====\n")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    code_content.append(content)
            except Exception as e:
                code_content.append(f"// Ошибка чтения файла: {e}")
    
    # Записываем в front.txt
    with open("front.txt", "w", encoding="utf-8") as f:
        f.write("".join(code_content))
    
    print("✅ Код фронтенда сгенерирован в front.txt")

def generate_documentation():
    """Генерирует документацию проекта"""
    doc_content = []
    
    doc_content.append("# ML Portal - Архитектура и Логика Работы\n")
    doc_content.append("=" * 60 + "\n\n")
    
    # Общая архитектура
    doc_content.append("## Общая Архитектура\n\n")
    doc_content.append("ML Portal состоит из следующих компонентов:\n\n")
    doc_content.append("### Контейнеры\n")
    doc_content.append("- **API** (легкий) - HTTP API, аутентификация, координация\n")
    doc_content.append("- **Worker** (тяжелый) - обработка документов, ML задачи\n")
    doc_content.append("- **Embedding** - создание эмбеддингов\n")
    doc_content.append("- **LLM** - генерация ответов\n")
    doc_content.append("- **PostgreSQL** - основная БД\n")
    doc_content.append("- **Redis** - кэш и брокер сообщений\n")
    doc_content.append("- **Qdrant** - векторная БД\n")
    doc_content.append("- **MinIO** - файловое хранилище\n\n")
    
    # Система очередей
    doc_content.append("## Система Очередей Celery\n\n")
    doc_content.append("### Очереди по приоритетам\n\n")
    doc_content.append("#### Критический приоритет (priority=10)\n")
    doc_content.append("- **chat_critical** - обработка сообщений чата\n")
    doc_content.append("  - `app.tasks.chat.process_message`\n")
    doc_content.append("  - `app.tasks.chat.generate_response`\n")
    doc_content.append("  - Воркеры: 3-4 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Высокий приоритет (priority=8)\n")
    doc_content.append("- **upload_high** - загрузка и нормализация файлов\n")
    doc_content.append("  - `app.tasks.upload_watch.*`\n")
    doc_content.append("  - `app.tasks.normalize.normalize`\n")
    doc_content.append("  - `app.tasks.chunk.split`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Средний приоритет (priority=5)\n")
    doc_content.append("- **analyze_medium** - анализ документов\n")
    doc_content.append("  - `app.tasks.analyze.*`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    doc_content.append("- **ocr_medium** - OCR и извлечение таблиц\n")
    doc_content.append("  - `app.tasks.ocr_tables.*`\n")
    doc_content.append("  - Воркеры: 2-3 на тяжелых ВМ\n\n")
    
    doc_content.append("#### Низкий приоритет (priority=2-1)\n")
    doc_content.append("- **rag_low** - RAG индексация\n")
    doc_content.append("  - `app.tasks.embed.*`\n")
    doc_content.append("  - `app.tasks.index.*`\n")
    doc_content.append("  - Воркеры: 1-2 на легкой ВМ\n\n")
    doc_content.append("- **cleanup_low** - очистка\n")
    doc_content.append("  - `app.tasks.delete.*`\n")
    doc_content.append("  - Воркеры: 1 на легкой ВМ\n\n")
    
    # Распределение по ВМ
    doc_content.append("## Распределение по ВМ\n\n")
    doc_content.append("### Легкая ВМ (6 CPU, 43GB RAM, много HDD)\n")
    doc_content.append("- API (1 контейнер)\n")
    doc_content.append("- PostgreSQL, Redis, Qdrant, MinIO\n")
    doc_content.append("- Worker-RAG (1 воркер) - только RAG задачи\n")
    doc_content.append("- Frontend\n\n")
    
    doc_content.append("### Тяжелые ВМ (12 CPU, 86GB RAM) - 2 ВМ\n")
    doc_content.append("**На каждой ВМ:**\n")
    doc_content.append("- Worker-Mixed (2 воркера) - чат + анализ\n")
    doc_content.append("- Embedding (1 сервис)\n")
    doc_content.append("- LLM (1 сервис)\n\n")
    
    # Потоки данных
    doc_content.append("## Потоки Данных\n\n")
    doc_content.append("### 1. Загрузка документа\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> MinIO\n")
    doc_content.append("API -> upload_watch (upload_high) -> normalize (upload_high)\n")
    doc_content.append("normalize -> chunk (upload_high) -> embed (rag_low)\n")
    doc_content.append("embed -> index (rag_low) -> Qdrant\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### 2. Анализ документа\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> analyze (analyze_medium)\n")
    doc_content.append("analyze -> ocr_tables (ocr_medium) -> результат\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### 3. Чат с RAG\n")
    doc_content.append("```\n")
    doc_content.append("Frontend -> API -> process_message (chat_critical)\n")
    doc_content.append("process_message -> RAG search -> generate_response (chat_critical)\n")
    doc_content.append("generate_response -> LLM -> ответ\n")
    doc_content.append("```\n\n")
    
    # Метрики
    doc_content.append("## Метрики и Мониторинг\n\n")
    doc_content.append("### RAG метрики\n")
    doc_content.append("- `rag_ingest_stage_duration_seconds` - время на стадии инжеста\n")
    doc_content.append("- `rag_ingest_errors_total` - ошибки инжеста\n")
    doc_content.append("- `rag_vectors_total` - общее количество векторов\n")
    doc_content.append("- `rag_chunks_total` - общее количество чанков\n")
    doc_content.append("- `rag_search_latency_seconds` - задержка поиска\n")
    doc_content.append("- `rag_quality_mrr` - качество поиска (MRR@K)\n\n")
    
    doc_content.append("### Чат метрики\n")
    doc_content.append("- `chat_rag_usage_total` - использование RAG в чате\n")
    doc_content.append("- `chat_rag_fallback_total` - fallback без RAG\n\n")
    
    # Конфигурация
    doc_content.append("## Конфигурация\n\n")
    doc_content.append("### Переменные окружения\n")
    doc_content.append("- `DATABASE_URL` - подключение к PostgreSQL\n")
    doc_content.append("- `REDIS_URL` - подключение к Redis\n")
    doc_content.append("- `QDRANT_URL` - подключение к Qdrant\n")
    doc_content.append("- `S3_ENDPOINT` - MinIO endpoint\n")
    doc_content.append("- `S3_BUCKET_RAG` - бакет для RAG документов\n")
    doc_content.append("- `S3_BUCKET_ANALYSIS` - бакет для анализа\n\n")
    
    doc_content.append("### Docker Compose файлы\n")
    doc_content.append("- `docker-compose.local.yml` - для локальной разработки\n")
    doc_content.append("- `docker-compose.prod.yml` - для продакшна (Docker Swarm)\n\n")
    
    # Команды управления
    doc_content.append("## Команды Управления\n\n")
    doc_content.append("### Локальная разработка\n")
    doc_content.append("```bash\n")
    doc_content.append("make build-local    # Собрать образы\n")
    doc_content.append("make up-local       # Запустить стек\n")
    doc_content.append("make down-local     # Остановить стек\n")
    doc_content.append("make logs           # Показать логи\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### Продакшн\n")
    doc_content.append("```bash\n")
    doc_content.append("make build-prod     # Собрать образы\n")
    doc_content.append("make up-prod        # Запустить стек\n")
    doc_content.append("make down-prod      # Остановить стек\n")
    doc_content.append("```\n\n")
    
    doc_content.append("### Генерация кода\n")
    doc_content.append("```bash\n")
    doc_content.append("make gen-backend    # Код бэкенда\n")
    doc_content.append("make gen-frontend   # Код фронтенда\n")
    doc_content.append("make gen-all        # Весь код\n")
    doc_content.append("make gen-docs       # Документация\n")
    doc_content.append("```\n\n")
    
    # Записываем документацию
    with open("PROJECT_ARCHITECTURE.md", "w", encoding="utf-8") as f:
        f.write("".join(doc_content))
    
    print("✅ Документация сгенерирована в PROJECT_ARCHITECTURE.md")

def main():
    parser = argparse.ArgumentParser(description="Генератор кода и документации ML Portal")
    parser.add_argument("target", choices=["backend", "frontend", "all", "docs"], 
                       help="Что генерировать")
    
    args = parser.parse_args()
    
    if args.target == "backend":
        generate_backend_code()
    elif args.target == "frontend":
        generate_frontend_code()
    elif args.target == "all":
        generate_backend_code()
        generate_frontend_code()
    elif args.target == "docs":
        generate_documentation()

if __name__ == "__main__":
    main()
