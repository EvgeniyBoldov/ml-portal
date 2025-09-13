#!/usr/bin/env python3
"""
Тестовый скрипт для проверки улучшенных функций экстракции и chunking
"""
import sys
import os
sys.path.insert(0, '/app')

def test_enhanced_extractor():
    """Тестируем улучшенный экстрактор"""
    print("=== Тест улучшенного экстрактора ===")
    
    try:
        from app.services.enhanced_text_extractor import extract_text_enhanced
        
        # Тест 1: Простой текст
        print("\n--- Тест 1: Простой текст ---")
        text_data = "Заголовок документа\n\nЭто основной текст документа.\nВторая строка с информацией.".encode('utf-8')
        result = extract_text_enhanced(text_data, 'test.txt')
        print(f"Тип: {result.kind}")
        print(f"Текст: {result.text[:100]}...")
        print(f"Мета: {result.meta}")
        print(f"Таблицы: {len(result.tables)}")
        print(f"Предупреждения: {result.warnings}")
        
        # Тест 2: CSV с таблицами
        print("\n--- Тест 2: CSV с таблицами ---")
        csv_data = "Name,Age,City\nИван,25,Москва\nПетр,30,СПб\nМария,28,Казань".encode('utf-8')
        result = extract_text_enhanced(csv_data, 'test.csv')
        print(f"Тип: {result.kind}")
        print(f"Текст: {result.text}")
        print(f"Таблицы: {len(result.tables)}")
        if result.tables:
            print(f"Первая таблица: {result.tables[0].name}, {result.tables[0].rows}x{result.tables[0].cols}")
        print(f"Предупреждения: {result.warnings}")
        
        print("\n✅ Улучшенный экстрактор работает!")
        
    except Exception as e:
        print(f"❌ Ошибка в улучшенном экстракторе: {e}")

def test_adaptive_chunker():
    """Тестируем адаптивный chunker"""
    print("\n=== Тест адаптивного chunker ===")
    
    try:
        from app.services.adaptive_chunker import chunk_text_adaptive
        
        # Тест с структурированным текстом
        text = """
# Глава 1: Введение

Это введение в документ. Здесь описываются основные концепции.

## Подраздел 1.1

Детальное описание концепций.

| Название | Значение | Описание |
|----------|----------|----------|
| Параметр 1 | 100 | Первый параметр |
| Параметр 2 | 200 | Второй параметр |

## Подраздел 1.2

Дополнительная информация.

### 1.2.1 Детали

Очень детальная информация о процессе.
        """.strip()
        
        chunks = chunk_text_adaptive(text, max_chars=200, overlap=50)
        
        print(f"Создано чанков: {len(chunks)}")
        
        for i, chunk in enumerate(chunks):
            print(f"\n--- Чанк {i} ---")
            print(f"Текст: {chunk.text[:100]}...")
            print(f"Заголовок: {chunk.is_header}")
            print(f"Таблица: {chunk.is_table}")
            print(f"Секция: {chunk.parent_section}")
            print(f"Метаданные: {chunk.metadata}")
        
        print("\n✅ Адаптивный chunker работает!")
        
    except Exception as e:
        print(f"❌ Ошибка в адаптивном chunker: {e}")

def test_reranker():
    """Тестируем reranker"""
    print("\n=== Тест reranker ===")
    
    try:
        from app.services.reranker import rerank_search_results
        
        # Тестовые документы
        documents = [
            {"text": "Этот документ о машинном обучении и нейронных сетях", "id": "1"},
            {"text": "Информация о программировании на Python", "id": "2"},
            {"text": "Руководство по использованию API", "id": "3"},
            {"text": "Документация по машинному обучению и алгоритмам", "id": "4"},
        ]
        
        query = "машинное обучение"
        
        # Тест cross-encoder reranking
        print("\n--- Cross-encoder reranking ---")
        results = rerank_search_results(query, documents, method="cross-encoder", top_k=3)
        
        for i, result in enumerate(results):
            print(f"{i+1}. ID: {result['document']['id']}, Score: {result['score']:.3f}")
            print(f"   Text: {result['document']['text']}")
        
        # Тест semantic reranking
        print("\n--- Semantic reranking ---")
        results = rerank_search_results(query, documents, method="semantic", top_k=3)
        
        for i, result in enumerate(results):
            print(f"{i+1}. ID: {result['document']['id']}, Score: {result['score']:.3f}")
            print(f"   Text: {result['document']['text']}")
        
        print("\n✅ Reranker работает!")
        
    except Exception as e:
        print(f"❌ Ошибка в reranker: {e}")

def test_metrics():
    """Тестируем метрики"""
    print("\n=== Тест метрик ===")
    
    try:
        from app.core.metrics import (
            llm_request_total, llm_latency_seconds, llm_tokens_total,
            embedding_request_total, embedding_latency_seconds,
            document_processing_total, document_processing_seconds,
            chunking_quality, reranking_total, reranking_latency_seconds,
            pipeline_stage_duration, pipeline_errors_total
        )
        
        # Симулируем некоторые метрики
        llm_request_total.labels(model="gpt-4", status="success").inc()
        llm_latency_seconds.labels(model="gpt-4").observe(1.5)
        llm_tokens_total.labels(model="gpt-4", type="input").inc(100)
        llm_tokens_total.labels(model="gpt-4", type="output").inc(50)
        
        embedding_request_total.labels(model="text-embedding-ada-002", status="success").inc()
        embedding_latency_seconds.labels(model="text-embedding-ada-002").observe(0.3)
        
        document_processing_total.labels(format="pdf", status="success").inc()
        document_processing_seconds.labels(format="pdf").observe(5.2)
        
        chunking_quality.labels(metric="coherence").observe(0.8)
        chunking_quality.labels(metric="completeness").observe(0.9)
        
        reranking_total.labels(method="cross-encoder", status="success").inc()
        reranking_latency_seconds.labels(method="cross-encoder").observe(0.1)
        
        pipeline_stage_duration.labels(stage="extract").observe(2.1)
        pipeline_stage_duration.labels(stage="chunk").observe(0.8)
        pipeline_stage_duration.labels(stage="embed").observe(1.2)
        
        print("✅ Метрики работают!")
        
    except Exception as e:
        print(f"❌ Ошибка в метриках: {e}")

if __name__ == "__main__":
    print("Тестирование улучшенных функций ML Portal")
    print("=" * 50)
    
    test_enhanced_extractor()
    test_adaptive_chunker()
    test_reranker()
    test_metrics()
    
    print("\n" + "=" * 50)
    print("Тестирование завершено!")
