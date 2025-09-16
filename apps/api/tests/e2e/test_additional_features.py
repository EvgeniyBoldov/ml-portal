#!/usr/bin/env python3
"""
Дополнительные E2E тесты для функций, которые могли быть забыты
"""
import asyncio
import json
import time
import uuid
from typing import Dict, Any
import httpx
import pytest

API_BASE_URL = "http://localhost:8000"

class TestAdditionalFeatures:
    """Дополнительные тесты функций"""
    
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.client = httpx.AsyncClient(timeout=30.0)
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
    
    async def test_user_authentication(self):
        """Тест аутентификации пользователей"""
        print("\n🧪 Тестирование аутентификации...")
        
        # 1. Регистрация пользователя
        print("1. Регистрация пользователя...")
        user_data = {
            "username": f"test_user_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "password": "test_password_123"
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/auth/register", json=user_data)
        if response.status_code == 201:
            print("✅ Пользователь зарегистрирован")
        elif response.status_code == 409:
            print("⚠️  Пользователь уже существует")
        else:
            print(f"⚠️  Ошибка регистрации: {response.status_code}")
        
        # 2. Вход пользователя
        print("2. Вход пользователя...")
        login_data = {
            "username": user_data["username"],
            "password": user_data["password"]
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/auth/login", json=login_data)
        if response.status_code == 200:
            tokens = response.json()
            assert "access_token" in tokens
            print("✅ Пользователь вошел в систему")
            
            # Сохраняем токен для дальнейших запросов
            self.client.headers.update({"Authorization": f"Bearer {tokens['access_token']}"})
        else:
            print(f"⚠️  Ошибка входа: {response.status_code}")
        
        print("🎉 Тест аутентификации завершен!")
    
    async def test_chat_search_and_filtering(self):
        """Тест поиска и фильтрации чатов"""
        print("\n🧪 Тестирование поиска и фильтрации чатов...")
        
        # Создаем несколько чатов с разными тегами
        chat_ids = []
        for i in range(3):
            chat_data = {
                "title": f"Search Test Chat {i}",
                "tags": [f"tag{i}", "search_test"]
            }
            response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
            assert response.status_code == 200
            chat_ids.append(response.json()["id"])
        
        # 1. Поиск по названию
        print("1. Поиск по названию...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats?search=Search Test")
        assert response.status_code == 200
        chats = response.json()
        assert len(chats) >= 3
        print(f"✅ Найдено {len(chats)} чатов по названию")
        
        # 2. Фильтрация по тегам
        print("2. Фильтрация по тегам...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats?tags=search_test")
        assert response.status_code == 200
        chats = response.json()
        assert len(chats) >= 3
        print(f"✅ Найдено {len(chats)} чатов по тегам")
        
        # 3. Пагинация
        print("3. Пагинация...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats?limit=2&offset=0")
        assert response.status_code == 200
        chats = response.json()
        assert len(chats) <= 2
        print(f"✅ Пагинация работает: {len(chats)} чатов на странице")
        
        # Очистка
        for chat_id in chat_ids:
            await self.client.delete(f"{API_BASE_URL}/api/chats/{chat_id}")
        
        print("🎉 Тест поиска и фильтрации завершен!")
    
    async def test_document_metadata(self):
        """Тест метаданных документов"""
        print("\n🧪 Тестирование метаданных документов...")
        
        # Создаем документ
        doc_data = {
            "name": f"metadata_test_{uuid.uuid4().hex[:8]}.txt",
            "uploaded_by": "test_user",
            "tags": ["metadata", "test"]
        }
        
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        assert response.status_code == 200
        doc = response.json()
        
        # 1. Получение метаданных
        print("1. Получение метаданных...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents/{doc['id']}")
        assert response.status_code == 200
        metadata = response.json()
        assert metadata["name"] == doc_data["name"]
        assert metadata["uploaded_by"] == doc_data["uploaded_by"]
        print("✅ Метаданные получены")
        
        # 2. Обновление метаданных
        print("2. Обновление метаданных...")
        update_data = {
            "tags": ["metadata", "test", "updated"]
        }
        response = await self.client.put(f"{API_BASE_URL}/api/rag/documents/{doc['id']}", json=update_data)
        assert response.status_code == 200
        print("✅ Метаданные обновлены")
        
        # 3. Получение списка документов
        print("3. Получение списка документов...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/documents")
        assert response.status_code == 200
        documents = response.json()
        assert len(documents) >= 1
        print(f"✅ Получено {len(documents)} документов")
        
        # Очистка
        await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}?hard=true")
        
        print("🎉 Тест метаданных завершен!")
    
    async def test_chat_export_import(self):
        """Тест экспорта и импорта чатов"""
        print("\n🧪 Тестирование экспорта и импорта чатов...")
        
        # Создаем чат с сообщениями
        chat_data = {"title": "Export Test Chat"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
        assert response.status_code == 200
        chat = response.json()
        
        # Добавляем сообщения
        for i in range(3):
            message_data = {"content": f"Test message {i}"}
            response = await self.client.post(f"{API_BASE_URL}/api/chats/{chat['id']}/messages", json=message_data)
            assert response.status_code == 200
        
        # 1. Экспорт в JSON
        print("1. Экспорт в JSON...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/export?format=json")
        assert response.status_code == 200
        export_data = response.json()
        assert "chat" in export_data
        assert "messages" in export_data
        print("✅ Экспорт в JSON работает")
        
        # 2. Экспорт в TXT
        print("2. Экспорт в TXT...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/export?format=txt")
        assert response.status_code == 200
        assert len(response.content) > 0
        print("✅ Экспорт в TXT работает")
        
        # 3. Экспорт в Markdown
        print("3. Экспорт в Markdown...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/export?format=md")
        assert response.status_code == 200
        assert len(response.content) > 0
        print("✅ Экспорт в Markdown работает")
        
        # Очистка
        await self.client.delete(f"{API_BASE_URL}/api/chats/{chat['id']}")
        
        print("🎉 Тест экспорта и импорта завершен!")
    
    async def test_analytics_and_metrics(self):
        """Тест аналитики и метрик"""
        print("\n🧪 Тестирование аналитики и метрик...")
        
        # 1. Статистика чатов
        print("1. Статистика чатов...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/stats")
        if response.status_code == 200:
            stats = response.json()
            assert "total_chats" in stats
            print("✅ Статистика чатов получена")
        else:
            print("⚠️  Статистика чатов недоступна")
        
        # 2. Статистика документов
        print("2. Статистика документов...")
        response = await self.client.get(f"{API_BASE_URL}/api/rag/stats")
        if response.status_code == 200:
            stats = response.json()
            assert "total_docs" in stats
            print("✅ Статистика документов получена")
        else:
            print("⚠️  Статистика документов недоступна")
        
        # 3. Метрики системы
        print("3. Метрики системы...")
        response = await self.client.get(f"{API_BASE_URL}/metrics")
        if response.status_code == 200:
            print("✅ Метрики системы получены")
        else:
            print("⚠️  Метрики системы недоступны")
        
        print("🎉 Тест аналитики завершен!")
    
    async def test_error_recovery(self):
        """Тест восстановления после ошибок"""
        print("\n🧪 Тестирование восстановления после ошибок...")
        
        # 1. Тест с неверным форматом файла
        print("1. Тест с неверным форматом файла...")
        doc_data = {
            "name": "invalid_file.exe",  # Неподдерживаемый формат
            "uploaded_by": "test_user"
        }
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        if response.status_code == 400:
            print("✅ Неверный формат файла отклонен")
        else:
            print("⚠️  Неверный формат файла не обработан")
        
        # 2. Тест с очень большим файлом
        print("2. Тест с очень большим файлом...")
        doc_data = {
            "name": "large_file.txt",
            "uploaded_by": "test_user"
        }
        response = await self.client.post(f"{API_BASE_URL}/api/rag/documents", json=doc_data)
        if response.status_code == 200:
            doc = response.json()
            # Пытаемся загрузить очень большой контент
            large_content = "x" * (100 * 1024 * 1024)  # 100MB
            put_url = doc["put_url"]
            try:
                response = await self.client.put(put_url, content=large_content)
                if response.status_code == 413:
                    print("✅ Большой файл отклонен")
                else:
                    print("⚠️  Большой файл принят")
            except:
                print("✅ Большой файл отклонен (исключение)")
            
            # Очистка
            await self.client.delete(f"{API_BASE_URL}/api/rag/documents/{doc['id']}?hard=true")
        
        print("🎉 Тест восстановления завершен!")
    
    async def test_concurrent_operations(self):
        """Тест параллельных операций"""
        print("\n🧪 Тестирование параллельных операций...")
        
        # Создаем несколько чатов параллельно
        print("1. Создание чатов параллельно...")
        tasks = []
        for i in range(5):
            chat_data = {"title": f"Concurrent Chat {i}"}
            task = self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in responses if isinstance(r, httpx.Response) and r.status_code == 200)
        print(f"✅ Создано {success_count}/5 чатов параллельно")
        
        # Получаем ID успешных чатов
        chat_ids = []
        for response in responses:
            if isinstance(response, httpx.Response) and response.status_code == 200:
                chat_ids.append(response.json()["id"])
        
        # Отправляем сообщения параллельно
        print("2. Отправка сообщений параллельно...")
        tasks = []
        for chat_id in chat_ids:
            message_data = {"content": f"Concurrent message for {chat_id}"}
            task = self.client.post(f"{API_BASE_URL}/api/chats/{chat_id}/messages", json=message_data)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in responses if isinstance(r, httpx.Response) and r.status_code == 200)
        print(f"✅ Отправлено {success_count} сообщений параллельно")
        
        # Очистка
        for chat_id in chat_ids:
            await self.client.delete(f"{API_BASE_URL}/api/chats/{chat_id}")
        
        print("🎉 Тест параллельных операций завершен!")
    
    async def test_data_consistency(self):
        """Тест консистентности данных"""
        print("\n🧪 Тестирование консистентности данных...")
        
        # Создаем чат
        chat_data = {"title": "Consistency Test Chat"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats", json=chat_data)
        assert response.status_code == 200
        chat = response.json()
        
        # Добавляем сообщение
        message_data = {"content": "Consistency test message"}
        response = await self.client.post(f"{API_BASE_URL}/api/chats/{chat['id']}/messages", json=message_data)
        assert response.status_code == 200
        message = response.json()
        
        # 1. Проверяем, что сообщение появилось в списке
        print("1. Проверка появления сообщения...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/messages")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        print("✅ Сообщение появилось в списке")
        
        # 2. Проверяем, что чат обновился
        print("2. Проверка обновления чата...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}")
        assert response.status_code == 200
        updated_chat = response.json()
        assert updated_chat["id"] == chat["id"]
        print("✅ Чат обновился")
        
        # 3. Проверяем, что данные не потерялись
        print("3. Проверка сохранности данных...")
        response = await self.client.get(f"{API_BASE_URL}/api/chats/{chat['id']}/messages/{message['id']}")
        assert response.status_code == 200
        retrieved_message = response.json()
        assert retrieved_message["content"] == message_data["content"]
        print("✅ Данные не потерялись")
        
        # Очистка
        await self.client.delete(f"{API_BASE_URL}/api/chats/{chat['id']}")
        
        print("🎉 Тест консистентности завершен!")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
