#!/usr/bin/env python3
"""
Демонстрация новой системы эмбеддингов
"""
import os
import sys
import time
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent))

def demo_embedding_system():
    """Демонстрация работы системы эмбеддингов"""
    print("🚀 Демонстрация новой системы эмбеддингов")
    print("=" * 50)
    
    # Импортируем после настройки путей
    from app.services.clients import embed_texts
    from app.core.model_registry import get_model_registry
    
    # 1. Показываем конфигурацию моделей
    print("\n📋 Конфигурация моделей:")
    registry = get_model_registry()
    models = registry.list_models()
    
    for model in models:
        print(f"  • {model.alias}: {model.id}")
        print(f"    - Размерность: {model.dim}")
        print(f"    - Макс. длина: {model.max_seq}")
        print(f"    - Статус: {model.health}")
        print(f"    - Очереди: {list(model.queues.values())}")
    
    # 2. Тестовые тексты
    test_texts = [
        "Машинное обучение - это подраздел искусственного интеллекта.",
        "Обработка естественного языка позволяет компьютерам понимать текст.",
        "Векторные представления текста используются для поиска и классификации.",
        "Эмбеддинги позволяют находить семантически похожие документы.",
        "Система RAG объединяет поиск и генерацию текста."
    ]
    
    print(f"\n📝 Тестовые тексты ({len(test_texts)} шт.):")
    for i, text in enumerate(test_texts, 1):
        print(f"  {i}. {text[:60]}{'...' if len(text) > 60 else ''}")
    
    # 3. Тест RT профиля (быстрый)
    print(f"\n⚡ Тест RT профиля (быстрый):")
    start_time = time.time()
    try:
        vectors_rt = embed_texts(test_texts, profile="rt")
        rt_time = time.time() - start_time
        
        print(f"  ✅ Успешно получено {len(vectors_rt)} векторов")
        print(f"  📊 Размерность: {len(vectors_rt[0]) if vectors_rt else 0}")
        print(f"  ⏱️  Время: {rt_time:.2f}с")
        
        # Показываем первые несколько значений первого вектора
        if vectors_rt and vectors_rt[0]:
            first_vector = vectors_rt[0][:5]
            print(f"  🔢 Первые 5 значений: {[round(x, 4) for x in first_vector]}")
            
    except Exception as e:
        print(f"  ❌ Ошибка RT профиля: {e}")
    
    # 4. Тест BULK профиля (массовый)
    print(f"\n📦 Тест BULK профиля (массовый):")
    start_time = time.time()
    try:
        vectors_bulk = embed_texts(test_texts, profile="bulk")
        bulk_time = time.time() - start_time
        
        print(f"  ✅ Успешно получено {len(vectors_bulk)} векторов")
        print(f"  📊 Размерность: {len(vectors_bulk[0]) if vectors_bulk else 0}")
        print(f"  ⏱️  Время: {bulk_time:.2f}с")
        
    except Exception as e:
        print(f"  ❌ Ошибка BULK профиля: {e}")
    
    # 5. Тест с указанием конкретной модели
    print(f"\n🎯 Тест с указанием модели:")
    try:
        vectors_model = embed_texts(test_texts[:2], models=["minilm"])
        print(f"  ✅ Успешно получено {len(vectors_model)} векторов для модели minilm")
        
    except Exception as e:
        print(f"  ❌ Ошибка с указанием модели: {e}")
    
    # 6. Сравнение производительности
    print(f"\n📈 Сравнение производительности:")
    if 'rt_time' in locals() and 'bulk_time' in locals():
        speedup = bulk_time / rt_time if rt_time > 0 else 0
        print(f"  RT профиль:  {rt_time:.2f}с")
        print(f"  BULK профиль: {bulk_time:.2f}с")
        print(f"  Ускорение: {speedup:.1f}x")
    
    print(f"\n🎉 Демонстрация завершена!")
    print(f"\n💡 Для использования в коде:")
    print(f"   from app.services.clients import embed_texts")
    print(f"   vectors = embed_texts(['Ваш текст'], profile='rt')")

if __name__ == "__main__":
    try:
        demo_embedding_system()
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Демонстрация прервана пользователем")
    except Exception as e:
        print(f"\n\n❌ Ошибка демонстрации: {e}")
        sys.exit(1)
