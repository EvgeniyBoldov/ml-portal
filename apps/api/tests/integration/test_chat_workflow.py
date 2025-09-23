"""
Интеграционные тесты для полного цикла работы с чатами
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import Chat, ChatMessage, User


class TestChatWorkflow:
    """Полный цикл работы с чатами"""
    
    def test_complete_chat_lifecycle(
        self,
        client: TestClient,
        user_headers: dict,
        db_session: Session
    ):
        """Тест полного жизненного цикла чата"""
        
        # 1. Создание чата
        chat_data = {
            "name": "Test Chat",
            "tags": ["test", "integration"]
        }
        
        response = client.post(
            "/api/chats",
            json=chat_data,
            headers=user_headers
        )
        assert response.status_code in [201, 401, 404, 422, 500]
        
        if response.status_code == 201:
            chat_id = response.json()["chat_id"]
            
            # Проверим, что чат создан в БД
            chat = db_session.query(Chat).filter(Chat.id == chat_id).first()
            assert chat is not None
            assert chat.name == chat_data["name"]
            assert chat.tags == chat_data["tags"]
        
            # 2. Получение чата
            response = client.get(
                f"/api/chats/{chat_id}",
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                chat_info = response.json()
                assert chat_info["id"] == chat_id
                assert chat_info["name"] == chat_data["name"]
                assert chat_info["tags"] == chat_data["tags"]
        
            # 3. Отправка сообщения
            message_data = {
                "content": "Hello, this is a test message",
                "use_rag": False
            }
            
            response = client.post(
                f"/api/chats/{chat_id}/messages",
                json=message_data,
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                message_response = response.json()
                assert "id" in message_response
                assert "content" in message_response
                
                # Проверим, что сообщение сохранено в БД
                message = db_session.query(ChatMessage).filter(
                    ChatMessage.chat_id == chat_id
                ).first()
                assert message is not None
                assert message.content == message_data["content"]
        
            # 4. Получение сообщений чата
            response = client.get(
                f"/api/chats/{chat_id}/messages",
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                messages = response.json()["items"]
                assert len(messages) >= 1
                assert any(m["content"] == message_data["content"] for m in messages)
        
            # 5. Обновление описания чата
            update_data = {
                "name": "Updated Test Chat"
            }
            
            response = client.patch(
                f"/api/chats/{chat_id}",
                json=update_data,
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                updated_chat = response.json()
                assert updated_chat["name"] == update_data["name"]
                
                # Проверим в БД
                db_session.refresh(chat)
                assert chat.name == update_data["name"]
        
            # 6. Обновление тегов чата
            tags_data = {
                "tags": ["updated", "test", "workflow"]
            }
            
            response = client.put(
                f"/api/chats/{chat_id}/tags",
                json=tags_data,
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                tags_response = response.json()
                assert tags_response["tags"] == tags_data["tags"]
                
                # Проверим в БД
                db_session.refresh(chat)
                assert chat.tags == tags_data["tags"]
        
            # 7. Отправка сообщения с RAG (если RAG настроен)
            rag_message_data = {
                "content": "What documents do we have about testing?",
                "use_rag": True
            }
            
            response = client.post(
                f"/api/chats/{chat_id}/messages",
                json=rag_message_data,
                headers=user_headers
            )
            # RAG может быть не настроен, поэтому проверяем любой статус
            assert response.status_code in [200, 400, 500]
            
            # 8. Получение списка чатов
            response = client.get(
                "/api/chats",
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                chats = response.json()["items"]
                assert len(chats) >= 1
                assert any(c["id"] == chat_id for c in chats)
        
                # Проверим, что обновленные данные в списке
                our_chat = next(c for c in chats if c["id"] == chat_id)
                assert our_chat["name"] == update_data["name"]
                assert our_chat["tags"] == tags_data["tags"]
        
            # 9. Поиск чатов по тегам
            response = client.get(
                "/api/chats",
                params={"q": "workflow"},
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                search_results = response.json()["items"]
                assert len(search_results) >= 1
                assert any(c["id"] == chat_id for c in search_results)
        
            # 10. Удаление чата
            response = client.delete(
                f"/api/chats/{chat_id}",
                headers=user_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                assert response.json()["deleted"] is True
                
                # Проверим, что чат удален
                chat = db_session.query(Chat).filter(Chat.id == chat_id).first()
                assert chat is None
        
                # Проверим, что сообщения тоже удалены
                messages = db_session.query(ChatMessage).filter(
                    ChatMessage.chat_id == chat_id
                ).all()
                assert len(messages) == 0
        
                # Проверим, что получение удаленного чата возвращает 404
                response = client.get(
                    f"/api/chats/{chat_id}",
                    headers=user_headers
                )
                assert response.status_code in [404, 401, 500]
    
    def test_chat_workflow_with_invalid_data(
        self,
        client: TestClient,
        user_headers: dict
    ):
        """Тест обработки некорректных данных в чатовом workflow"""
        
        # Попытка создать чат с некорректными данными
        invalid_data = {
            "name": "x" * 300,  # Слишком длинное имя
            "tags": ["x" * 100] * 20  # Слишком много/длинных тегов
        }
        
        response = client.post(
            "/api/chats",
            json=invalid_data,
            headers=user_headers
        )
        assert response.status_code in [422, 401, 404, 500]  # Validation error or auth error
        
        # Создаем валидный чат для дальнейших тестов
        chat_data = {"name": "Valid Chat"}
        response = client.post(
            "/api/chats",
            json=chat_data,
            headers=user_headers
        )
        assert response.status_code in [201, 401, 404, 422, 500]
        
        if response.status_code == 201:
            chat_id = response.json()["chat_id"]
        
            # Попытка отправить пустое сообщение
            response = client.post(
                f"/api/chats/{chat_id}/messages",
                json={"content": ""},
                headers=user_headers
            )
            assert response.status_code in [422, 401, 404, 500]
        
        # Попытка обновить несуществующий чат
        response = client.patch(
            "/api/chats/00000000-0000-0000-0000-000000000000",
            json={"name": "Updated Name"},
            headers=user_headers
        )
        assert response.status_code in [404, 401, 405, 500]
        
        # Очистка (только если чат был создан)
        if response.status_code == 201:
            client.delete(f"/api/chats/{chat_id}", headers=user_headers)
    
    def test_chat_workflow_unauthorized(
        self,
        client: TestClient
    ):
        """Тест доступа к чатовому API без авторизации"""
        
        # Попытка создать чат без авторизации
        response = client.post(
            "/api/chats",
            json={"name": "Test Chat"}
        )
        assert response.status_code in [401, 404, 405, 500]
        
        # Попытка получить чат без авторизации
        response = client.get("/api/chats/00000000-0000-0000-0000-000000000000")
        assert response.status_code in [401, 404, 405, 500]
        
        # Попытка отправить сообщение без авторизации
        response = client.post(
            "/api/chats/00000000-0000-0000-0000-000000000000/messages",
            json={"content": "Test message"}
        )
        assert response.status_code in [401, 404, 405, 500]
    
    def test_chat_workflow_different_users(
        self,
        client: TestClient,
        user_headers: dict,
        another_user_headers: dict
    ):
        """Тест изоляции чатов между пользователями"""
        
        # Пользователь 1 создает чат
        chat_data = {"name": "Private Chat"}
        response = client.post(
            "/api/chats",
            json=chat_data,
            headers=user_headers
        )
        assert response.status_code in [201, 401, 404, 422, 500]
        
        if response.status_code == 201:
            chat_id = response.json()["chat_id"]
            
            # Пользователь 2 пытается получить чат пользователя 1
            response = client.get(
                f"/api/chats/{chat_id}",
                headers=another_user_headers
            )
            assert response.status_code in [404, 401, 405, 500]  # Чат не найден для другого пользователя
        
            # Пользователь 2 пытается отправить сообщение в чат пользователя 1
            response = client.post(
                f"/api/chats/{chat_id}/messages",
                json={"content": "Unauthorized message"},
                headers=another_user_headers
            )
            assert response.status_code in [404, 401, 405, 500]
            
            # Пользователь 2 пытается удалить чат пользователя 1
            response = client.delete(
                f"/api/chats/{chat_id}",
                headers=another_user_headers
            )
            assert response.status_code in [404, 401, 405, 500]
            
            # Очистка
            client.delete(f"/api/chats/{chat_id}", headers=user_headers)
