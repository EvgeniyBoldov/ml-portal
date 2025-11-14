"""
E2E тесты для чатов: CRUD + полный флоу
"""
import pytest
import time
from uuid import uuid4


class TestChatCRUD:
    """Тесты CRUD операций для чатов"""
    
    def test_create_chat(self, user_client):
        """Создание чата"""
        response = user_client.post("/chats", json={
            "name": "Test Chat",
            "tags": ["test", "e2e"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "chat_id" in data
        
        # Cleanup
        user_client.delete(f"/chats/{data['chat_id']}")
    
    def test_list_chats(self, user_client):
        """Получение списка чатов"""
        # Создаем чат
        create_response = user_client.post("/chats", json={
            "name": "Chat for listing"
        })
        assert create_response.status_code == 200
        chat_id = create_response.json()["chat_id"]
        
        # Получаем список
        response = user_client.get("/chats")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0
        
        # Cleanup
        user_client.delete(f"/chats/{chat_id}")
    
    def test_update_chat_name(self, user_client):
        """Обновление имени чата"""
        # Создаем чат
        create_response = user_client.post("/chats", json={
            "name": "Original Name"
        })
        assert create_response.status_code == 200
        chat_id = create_response.json()["chat_id"]
        
        # Обновляем имя
        new_name = "Updated Name"
        update_response = user_client.patch(f"/chats/{chat_id}", json={
            "name": new_name
        })
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["name"] == new_name
        
        # Cleanup
        user_client.delete(f"/chats/{chat_id}")
    
    def test_update_chat_tags(self, user_client):
        """Обновление тегов чата"""
        # Создаем чат
        create_response = user_client.post("/chats", json={
            "name": "Chat with tags",
            "tags": ["old"]
        })
        assert create_response.status_code == 200
        chat_id = create_response.json()["chat_id"]
        
        # Обновляем теги
        new_tags = ["new", "updated"]
        update_response = user_client.put(f"/chats/{chat_id}/tags", json={
            "tags": new_tags
        })
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["tags"] == new_tags
        
        # Cleanup
        user_client.delete(f"/chats/{chat_id}")
    
    def test_delete_chat(self, user_client):
        """Удаление чата"""
        # Создаем чат
        create_response = user_client.post("/chats", json={
            "name": "Chat to delete"
        })
        assert create_response.status_code == 200
        chat_id = create_response.json()["chat_id"]
        
        # Удаляем
        delete_response = user_client.delete(f"/chats/{chat_id}")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["deleted"] is True


class TestChatMessagesFlow:
    """Тесты флоу сообщений в чате"""
    
    @pytest.fixture
    def test_chat(self, user_client):
        """Создать тестовый чат"""
        response = user_client.post("/chats", json={
            "name": "Test Chat for Messages"
        })
        assert response.status_code == 200
        chat_id = response.json()["chat_id"]
        
        yield chat_id
        
        # Cleanup
        try:
            user_client.delete(f"/chats/{chat_id}")
        except:
            pass
    
    def test_send_message_without_rag(self, user_client, test_chat):
        """Отправка сообщения без RAG"""
        response = user_client.post(f"/chats/{test_chat}/messages", json={
            "content": "Hello, this is a test message",
            "use_rag": False
        }, headers={
            "Idempotency-Key": f"test-{uuid4()}"
        })
        
        # Для SSE стрима проверяем, что запрос начался
        assert response.status_code == 200
        
        # Даем время на обработку
        time.sleep(2)
        
        # Проверяем, что сообщения сохранились
        messages_response = user_client.get(f"/chats/{test_chat}/messages")
        assert messages_response.status_code == 200
        messages = messages_response.json()
        assert len(messages["items"]) >= 2  # user + assistant
    
    def test_send_message_with_rag(self, user_client, test_chat):
        """Отправка сообщения с RAG"""
        response = user_client.post(f"/chats/{test_chat}/messages", json={
            "content": "What is in the knowledge base?",
            "use_rag": True
        }, headers={
            "Idempotency-Key": f"test-rag-{uuid4()}"
        })
        
        assert response.status_code == 200
        time.sleep(2)
        
        # Проверяем сообщения
        messages_response = user_client.get(f"/chats/{test_chat}/messages")
        assert messages_response.status_code == 200
    
    def test_idempotency(self, user_client, test_chat):
        """Тест идемпотентности запросов"""
        idempotency_key = f"test-idem-{uuid4()}"
        
        # Первый запрос
        response1 = user_client.post(f"/chats/{test_chat}/messages", json={
            "content": "Idempotency test",
            "use_rag": False
        }, headers={
            "Idempotency-Key": idempotency_key
        })
        assert response1.status_code == 200
        
        time.sleep(2)
        
        # Повторный запрос с тем же ключом
        response2 = user_client.post(f"/chats/{test_chat}/messages", json={
            "content": "Idempotency test",
            "use_rag": False
        }, headers={
            "Idempotency-Key": idempotency_key
        })
        assert response2.status_code == 200
        
        # Должно быть событие cached
        # (проверка через SSE stream в реальности)
    
    def test_list_messages_pagination(self, user_client, test_chat):
        """Тест пагинации сообщений"""
        # Отправляем несколько сообщений
        for i in range(3):
            user_client.post(f"/chats/{test_chat}/messages", json={
                "content": f"Message {i}",
                "use_rag": False
            }, headers={
                "Idempotency-Key": f"test-pag-{i}-{uuid4()}"
            })
            time.sleep(1)
        
        time.sleep(2)
        
        # Получаем первую страницу
        response = user_client.get(f"/chats/{test_chat}/messages?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        
        # Если есть cursor, получаем следующую страницу
        if data.get("next_cursor"):
            next_response = user_client.get(
                f"/chats/{test_chat}/messages?limit=2&cursor={data['next_cursor']}"
            )
            assert next_response.status_code == 200
    
    def test_send_message_with_model_selection(self, user_client, test_chat):
        """Отправка сообщения с выбором модели"""
        # Получаем список доступных моделей
        models_response = user_client.get("/chats/models")
        assert models_response.status_code == 200
        models = models_response.json()["models"]
        assert len(models) > 0
        
        # Отправляем сообщение с выбранной моделью
        response = user_client.post(f"/chats/{test_chat}/messages", json={
            "content": "Test with specific model",
            "use_rag": False,
            "model": models[0]["id"]
        }, headers={
            "Idempotency-Key": f"test-model-{uuid4()}"
        })
        
        assert response.status_code == 200


class TestChatAuthorization:
    """Тесты авторизации чатов"""
    
    def test_cannot_access_other_user_chat(self, admin_client, user_client, test_user):
        """Пользователь не может получить доступ к чужому чату"""
        # Админ создает чат
        admin_response = admin_client.post("/chats", json={
            "name": "Admin's private chat"
        })
        assert admin_response.status_code == 200
        admin_chat_id = admin_response.json()["chat_id"]
        
        # Пользователь пытается отправить сообщение в чужой чат
        user_response = user_client.post(f"/chats/{admin_chat_id}/messages", json={
            "content": "Trying to access",
            "use_rag": False
        }, headers={
            "Idempotency-Key": f"test-auth-{uuid4()}"
        })
        
        # Должен быть 403 или 404
        assert user_response.status_code in [403, 404]
        
        # Cleanup
        admin_client.delete(f"/chats/{admin_chat_id}")
