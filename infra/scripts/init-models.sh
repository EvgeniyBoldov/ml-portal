#!/bin/bash

# Скрипт для инициализации легких ML моделей для тестирования

set -e

echo "🚀 Инициализация легких ML моделей для тестирования..."

# Создаем директории
mkdir -p models/embeddings
mkdir -p models/llm

# Устанавливаем зависимости для скачивания моделей
pip install sentence-transformers transformers torch

echo "📥 Скачиваем легкую модель эмбеддингов (all-MiniLM-L6-v2)..."
python -c "
from sentence_transformers import SentenceTransformer
import os
os.makedirs('models/embeddings/all-MiniLM-L6-v2', exist_ok=True)
model = SentenceTransformer('all-MiniLM-L6-v2')
model.save('./models/embeddings/all-MiniLM-L6-v2')
print('✅ Модель эмбеддингов сохранена')
"

echo "📥 Скачиваем легкую LLM модель (TinyLlama)..."
python -c "
from transformers import AutoModel, AutoTokenizer
import os
os.makedirs('models/llm/tiny-llama', exist_ok=True)
model = AutoModel.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0')
tokenizer = AutoTokenizer.from_pretrained('TinyLlama/TinyLlama-1.1B-Chat-v1.0')
model.save_pretrained('./models/llm/tiny-llama')
tokenizer.save_pretrained('./models/llm/tiny-llama')
print('✅ LLM модель сохранена')
"

echo "📊 Проверяем размеры моделей..."
du -sh models/embeddings/all-MiniLM-L6-v2
du -sh models/llm/tiny-llama

echo "✅ Инициализация моделей завершена!"
echo "📁 Модели сохранены в:"
echo "   - Эмбеддинги: models/embeddings/all-MiniLM-L6-v2"
echo "   - LLM: models/llm/tiny-llama"
