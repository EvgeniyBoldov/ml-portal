#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой системы эмбеддингов
"""
import os
import sys
import time
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.model_registry import get_model_registry
from app.services.embedding_dispatcher import embed_texts_dispatcher

def test_model_registry():
    """Тестирует Model Registry"""
    print("Testing Model Registry...")
    
    registry = get_model_registry()
    
    # Список моделей
    models = registry.list_models()
    print(f"Found {len(models)} models:")
    for model in models:
        print(f"  - {model.alias}: {model.id} (dim={model.dim}, health={model.health})")
    
    # Дефолтные модели
    rt_models = registry.get_default_models("rt")
    bulk_models = registry.get_default_models("bulk")
    print(f"Default RT models: {rt_models}")
    print(f"Default BULK models: {bulk_models}")
    
    return True

def test_embedding_dispatcher():
    """Тестирует Embedding Dispatcher"""
    print("\nTesting Embedding Dispatcher...")
    
    try:
        # Тестовые тексты
        texts = [
            "This is a test document about machine learning.",
            "Another test document about natural language processing.",
            "A third document about artificial intelligence."
        ]
        
        print(f"Testing with {len(texts)} texts...")
        
        # Тест RT профиля
        print("Testing RT profile...")
        start_time = time.time()
        vectors_rt = embed_texts_dispatcher(texts, profile="rt")
        rt_time = time.time() - start_time
        
        print(f"RT: Got {len(vectors_rt)} vectors, first vector dim={len(vectors_rt[0]) if vectors_rt else 0}")
        print(f"RT: Time taken: {rt_time:.2f}s")
        
        # Тест BULK профиля
        print("Testing BULK profile...")
        start_time = time.time()
        vectors_bulk = embed_texts_dispatcher(texts, profile="bulk")
        bulk_time = time.time() - start_time
        
        print(f"BULK: Got {len(vectors_bulk)} vectors, first vector dim={len(vectors_bulk[0]) if vectors_bulk else 0}")
        print(f"BULK: Time taken: {bulk_time:.2f}s")
        
        return True
        
    except Exception as e:
        print(f"Embedding Dispatcher test failed: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("Testing New Embedding System")
    print("=" * 40)
    
    # Тест Model Registry
    registry_ok = test_model_registry()
    
    # Тест Embedding Dispatcher
    dispatcher_ok = test_embedding_dispatcher()
    
    print("\n" + "=" * 40)
    print("Test Results:")
    print(f"Model Registry: {'PASS' if registry_ok else 'FAIL'}")
    print(f"Embedding Dispatcher: {'PASS' if dispatcher_ok else 'FAIL'}")
    
    if registry_ok and dispatcher_ok:
        print("\nAll tests passed! 🎉")
        return 0
    else:
        print("\nSome tests failed! ❌")
        return 1

if __name__ == "__main__":
    sys.exit(main())
