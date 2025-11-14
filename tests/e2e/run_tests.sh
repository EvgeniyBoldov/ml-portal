#!/bin/bash
set -e

echo "🚀 Запуск E2E тестов ML Portal"
echo "================================"

# Проверка, что сервис запущен
echo "📡 Проверка доступности API..."
if ! curl -s http://localhost:8000/api/v1/health > /dev/null; then
    echo "❌ API недоступен. Запустите docker-compose up"
    exit 1
fi
echo "✅ API доступен"

# Проверка .env
if [ ! -f .env ]; then
    echo "⚠️  Файл .env не найден. Создаю из .env.example..."
    cp .env.example .env
fi

# Установка зависимостей
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

echo "📦 Установка зависимостей..."
source venv/bin/activate
pip install -q -r requirements.txt

# Запуск тестов
echo ""
echo "🧪 Запуск тестов..."
echo "================================"

if [ "$1" == "admin" ]; then
    echo "Тесты админки..."
    pytest test_admin_crud.py -v
elif [ "$1" == "chat" ]; then
    echo "Тесты чатов..."
    pytest test_chat_flow.py -v
elif [ "$1" == "rag" ]; then
    echo "Тесты RAG..."
    pytest test_rag_flow.py -v
elif [ "$1" == "fast" ]; then
    echo "Быстрые тесты (без RAG)..."
    pytest test_admin_crud.py test_chat_flow.py -v
else
    echo "Все тесты..."
    pytest -v
fi

echo ""
echo "✅ Тесты завершены!"
