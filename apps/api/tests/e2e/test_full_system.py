#!/usr/bin/env python3
"""
Комплексные E2E тесты всей системы ML Portal
"""
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List
import httpx
import pytest

# Конфигурация тестов
API_BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 300  # 5 минут на весь тест

class TestFullSystem:
    """Комплексные тесты всей системы"""
    
    @pytest.fixture(autouse=True)
    async def setup(self):
        """Настройка перед каждым тестом"""
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_data = {
            "chat_id": None,
            "document_id": None,
            "analysis_id": None,
            "tags": []
        }
        yield
        await self.client.aclose()
    
    async def wait_for_condition(self, check_func, timeout: int = 60, interval: int = 2):
        """Ждет выполнения условия с таймаутом"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if await check_func():
                    return True
            except Exception as e:
                print(f"Condition check failed: {e}")
            await asyncio.sleep(interval)
        return False
    
    async def test_chat_workflow(self):
        """Тест полного workflow чата"""
        print("\n🧪 Тестирование workflow чата...")
        
        # 1. Создание чата
        print("1. Создание чата...")
        chat_data = {
            "title": f"Test Chat {uuid.uuid4().hex[:8]}",
            "tags": ["test", "e2e"]
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
        assert response.status_code == 200
        chat = response.json()
        self.test_data["chat_id"] = chat["id"]
        print(f"✅ Чат создан: {chat['id']}")
        
        # 2. Отправка сообщения
        print("2. Отправка сообщения...")
        message_data = {
            "content": "Привет! Как дела? Расскажи что-нибудь интересное.",
            "use_rag": False
        }
        
        response = await self.client.post(
            f"{API_BASE_URL}/api/chats/{chat['id']}/messages", 
            json=message_data
        )
        assert response.status_code == 200
        message = response.json()
        print(f"✅ Сообщение отправлено: {message['id']}")
        
        # 3. Получение ответа (стрим)
        print("3. Получение ответа...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/messages/{message['id']}/stream")
        assert response.status_code == 200
        
        # Читаем стрим
        content = ""
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        chunk_content = delta.get("content", "")
                        if chunk_content:
                            content += chunk_content
                except:
                    continue
        
        assert len(content) > 0
        print(f"✅ Ответ получен: {len(content)} символов")
        
        # 4. Добавление тега
        print("4. Добавление тега...")
        tag_data = {"tag": "important"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats/{chat['id']}/tags", json=tag_data)
        assert response.status_code == 200
        print("✅ Тег добавлен")
        
        # 5. Переименование чата
        print("5. Переименование чата...")
        new_title = f"Renamed Chat {uuid.uuid4().hex[:8]}"
        update_data = {"title": new_title}
        response = await self.client.put(f"{API_BASE_URL}/api/chats/{chat['id']}", json=update_data)
        assert response.status_code == 200
        print("✅ Чат переименован")
        
        # 6. Удаление чата
        print("6. Удаление чата...")
        response = await self.client.delete(f"{API_BASE_URL}/api/chats/{chat['id']}")
        assert response.status_code == 200
        print("✅ Чат удален")
        
        print("🎉 Тест чата завершен успешно!")
    
    async def test_rag_workflow(self):
        """Тест полного workflow RAG"""
        print("\n🧪 Тестирование workflow RAG...")
        
        # 1. Создание документа
        print("1. Создание документа...")
        doc_data = {
            "name": f"test_document_{uuid.uuid4().hex[:8]}.txt",
            "uploaded_by": "test_user"
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        assert response.status_code == 200
        doc = response.json()
        self.test_data["document_id"] = doc["id"]
        print(f"✅ Документ создан: {doc['id']}")
        
        # 2. Загрузка файла
        print("2. Загрузка файла...")
        test_content = "Это тестовый документ для проверки RAG системы. Содержит информацию о машинном обучении и обработке естественного языка."
        put_url = doc["put_url"]
        
        # Загружаем файл через presigned URL
        upload_response = await self.client.put(put_url, content=test_content)
        assert upload_response.status_code == 200
        print("✅ Файл загружен")
        
        # 3. Ожидание обработки
        print("3. Ожидание обработки...")
        async def check_processing():
            response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/progress")
            if response.status_code == 200:
                progress = response.json()
                return progress.get("status") == "processed"
            return False
        
        processing_ok = await self.wait_for_condition(check_processing, timeout=120)
        assert processing_ok, "Документ не был обработан в течение 2 минут"
        print("✅ Документ обработан")
        
        # 4. Проверка статусов
        print("4. Проверка статусов...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/progress")
        assert response.status_code == 200
        progress = response.json()
        assert progress["chunks_total"] > 0
        assert progress["vectors_total"] > 0
        print(f"✅ Статус: {progress['chunks_total']} чанков, {progress['vectors_total']} векторов")
        
        # 5. Скачивание оригинала
        print("5. Скачивание оригинала...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/download?type=original")
        assert response.status_code == 200
        assert len(response.content) > 0
        print("✅ Оригинал скачан")
        
        # 6. Скачивание канонического файла
        print("6. Скачивание канонического файла...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/download?type=canonical")
        assert response.status_code == 200
        print("✅ Канонический файл скачан")
        
        # 7. Поиск в RAG
        print("7. Поиск в RAG...")
        search_data = {
            "query": "машинное обучение",
            "top_k": 5
        }
        response = await self.client.post(f"{API_BASE_URL}/api/rag/search", json=search_data)
        assert response.status_code == 200
        results = response.json()
        assert len(results["results"]) > 0
        print(f"✅ Найдено {len(results['results'])} результатов")
        
        # 8. Пересчет на новую модель (если доступно)
        print("8. Пересчет на новую модель...")
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/reprocess")
        if response.status_code == 200:
            print("✅ Пересчет запущен")
            # Ждем завершения пересчета
            reprocess_ok = await self.wait_for_condition(check_processing, timeout=120)
            assert reprocess_ok, "Пересчет не завершился в течение 2 минут"
            print("✅ Пересчет завершен")
        else:
            print("⚠️  Пересчет недоступен")
        
        # 9. Архивирование документа
        print("9. Архивирование документа...")
        response = await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}")
        assert response.status_code == 200
        print("✅ Документ архивирован")
        
        # 10. Удаление документа
        print("10. Удаление документа...")
        response = await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}?hard=true")
        assert response.status_code == 200
        print("✅ Документ удален")
        
        print("🎉 Тест RAG завершен успешно!")
    
    async def test_analysis_workflow(self):
        """Тест полного workflow анализа"""
        print("\n🧪 Тестирование workflow анализа...")
        
        # 1. Создание документа для анализа
        print("1. Создание документа для анализа...")
        doc_data = {
            "name": f"analysis_document_{uuid.uuid4().hex[:8]}.txt",
            "uploaded_by": "test_user"
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        assert response.status_code == 200
        doc = response.json()
        
        # 2. Загрузка файла
        print("2. Загрузка файла...")
        test_content = "Это документ для анализа. Содержит важную информацию о проекте и его результатах."
        put_url = doc["put_url"]
        
        upload_response = await self.client.put(put_url, content=test_content)
        assert upload_response.status_code == 200
        print("✅ Файл загружен")
        
        # 3. Запуск анализа
        print("3. Запуск анализа...")
        analysis_data = {
            "document_id": doc["id"],
            "analysis_type": "summary"
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/analyze", json=analysis_data)
        assert response.status_code == 200
        analysis = response.json()
        self.test_data["analysis_id"] = analysis["id"]
        print(f"✅ Анализ запущен: {analysis['id']}")
        
        # 4. Ожидание результата
        print("4. Ожидание результата...")
        async def check_analysis():
            response = await self.client.get(f"{API_BASE_URL}/api/analyze/{analysis['id']}")
            if response.status_code == 200:
                result = response.json()
                return result.get("status") in ["completed", "failed"]
            return False
        
        analysis_ok = await self.wait_for_condition(check_analysis, timeout=120)
        assert analysis_ok, "Анализ не завершился в течение 2 минут"
        print("✅ Анализ завершен")
        
        # 5. Получение результата
        print("5. Получение результата...")
        response = await self.client.get(f"{API_BASE_URL}/api/analyze/{analysis['id']}")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "completed"
        assert "result" in result
        print("✅ Результат получен")
        
        # 6. Очистка
        print("6. Очистка...")
        await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}?hard=true")
        print("✅ Очистка завершена")
        
        print("🎉 Тест анализа завершен успешно!")
    
    async def test_system_health(self):
        """Тест здоровья системы"""
        print("\n🧪 Тестирование здоровья системы...")
        
        # 1. Проверка API
        print("1. Проверка API...")
        response = await self.client.get(f"{API_BASE_URL}/healthz")
        assert response.status_code == 200
        print("✅ API работает")
        
        # 2. Проверка эмбеддингов
        print("2. Проверка эмбеддингов...")
        try:
            response = await self.client.get("http://localhost:8001/healthz")
            if response.status_code == 200:
                print("✅ Эмбеддинги работают")
            else:
                print("⚠️  Эмбеддинги недоступны")
        except:
            print("⚠️  Эмбеддинги недоступны")
        
        # 3. Проверка LLM
        print("3. Проверка LLM...")
        try:
            response = await self.client.get("http://localhost:8002/healthz")
            if response.status_code == 200:
                print("✅ LLM работает")
            else:
                print("⚠️  LLM недоступен")
        except:
            print("⚠️  LLM недоступен")
        
        print("🎉 Тест здоровья системы завершен!")
    
    async def test_error_handling(self):
        """Тест обработки ошибок"""
        print("\n🧪 Тестирование обработки ошибок...")
        
        # 1. Несуществующий чат
        print("1. Несуществующий чат...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/nonexistent")
        assert response.status_code == 404
        print("✅ 404 для несуществующего чата")
        
        # 2. Несуществующий документ
        print("2. Несуществующий документ...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/nonexistent")
        assert response.status_code == 404
        print("✅ 404 для несуществующего документа")
        
        # 3. Неверные данные
        print("3. Неверные данные...")
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json={})
        assert response.status_code == 422
        print("✅ 422 для неверных данных")
        
        print("🎉 Тест обработки ошибок завершен!")

# Дополнительные тесты
class TestAdditionalFeatures:
    """Дополнительные тесты функций"""
    
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        yield
        await self.client.aclose()
    
    async def test_chat_with_rag(self):
        """Тест чата с RAG"""
        print("\n🧪 Тестирование чата с RAG...")
        
        # Создаем документ
        doc_data = {
            "name": f"rag_test_{uuid.uuid4().hex[:8]}.txt",
            "uploaded_by": "test_user"
        }
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        assert response.status_code == 200
        doc = response.json()
        
        # Загружаем файл
        test_content = "Это документ о машинном обучении. Содержит информацию о нейронных сетях и алгоритмах."
        put_url = doc["put_url"]
        await self.client.put(put_url, content=test_content)
        
        # Ждем обработки
        async def check_processing():
            response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}/progress")
            if response.status_code == 200:
                progress = response.json()
                return progress.get("status") == "processed"
            return False
        
        await self.wait_for_condition(check_processing, timeout=120)
        
        # Создаем чат
        chat_data = {"title": f"RAG Chat {uuid.uuid4().hex[:8]}"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
        assert response.status_code == 200
        chat = response.json()
        
        # Отправляем сообщение с RAG
        message_data = {
            "content": "Расскажи о машинном обучении",
            "use_rag": True
        }
        response = await self.client.post(f"{API_BASE_URL}/api/chats/{chat['id']}/messages", json=message_data)
        assert response.status_code == 200
        
        # Очистка
        await self.client.delete(f"{API_BASE_URL}/api/chats/{chat['id']}")
        await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}?hard=true")
        
        print("✅ Чат с RAG работает")
    
    async def test_batch_operations(self):
        """Тест пакетных операций"""
        print("\n🧪 Тестирование пакетных операций...")
        
        # Создаем несколько чатов
        chat_ids = []
        for i in range(3):
            chat_data = {"title": f"Batch Chat {i}"}
            response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
            assert response.status_code == 200
            chat_ids.append(response.json()["id"])
        
        # Получаем список чатов
        response = await self.client.get(f"{API_BASE_URL}/api/chats")
        assert response.status_code == 200
        chats = response.json()
        assert len(chats) >= 3
        
        # Удаляем все чаты
        for chat_id in chat_ids:
            await self.client.delete(f"{API_BASE_URL}/api/chats/{chat_id}")
        
        print("✅ Пакетные операции работают")
    
    async def test_performance(self):
        """Тест производительности"""
        print("\n🧪 Тестирование производительности...")
        
        start_time = time.time()
        
        # Создаем чат
        chat_data = {"title": "Performance Test"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
        assert response.status_code == 200
        chat = response.json()
        
        # Отправляем несколько сообщений
        for i in range(5):
            message_data = {"content": f"Сообщение {i}"}
            response = await self.client.post(f"{API_BASE_URL}/api/chats/{chat['id']}/messages", json=message_data)
            assert response.status_code == 200
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"✅ 5 сообщений за {duration:.2f} секунд")
        assert duration < 30, "Слишком медленно"
        
        # Очистка
        await self.client.delete(f"{API_BASE_URL}/api/chats/{chat['id']}")

if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "-s"])
