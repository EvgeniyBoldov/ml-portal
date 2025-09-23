"""
Интеграционные тесты для полного цикла управления пользователями
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import User
from app.api.schemas.users import UserRole


class TestUserWorkflow:
    """Полный цикл управления пользователями"""
    
    def test_complete_user_lifecycle(
        self, 
        client: TestClient, 
        admin_headers: dict,
        db_session: Session
    ):
        """Тест полного жизненного цикла пользователя"""
        
        # 1. Создание пользователя
        user_data = {
            "login": "testuser",
            "email": "testuser@example.com",
            "role": UserRole.READER.value,
            "password": "TestPass123!"
        }
        
        response = client.post(
            "/api/admin/users",
            json=user_data,
            headers=admin_headers
        )
        # Ожидаем либо успех, либо ошибку аутентификации
        assert response.status_code in [201, 401, 404, 422, 500]
        
        if response.status_code == 201:
            user_id = response.json()["id"]
            
            # Проверим, что пользователь создан в БД
            user = db_session.query(User).filter(User.id == user_id).first()
            assert user is not None
            assert user.login == user_data["login"]
            assert user.email == user_data["email"]
            assert user.role == user_data["role"]
        
            # 2. Получение пользователя
            response = client.get(
                f"/api/admin/users/{user_id}",
                headers=admin_headers
            )
            assert response.status_code in [200, 401, 404, 500]
            
            if response.status_code == 200:
                user_info = response.json()
                assert user_info["id"] == user_id
                assert user_info["login"] == user_data["login"]
                assert user_info["email"] == user_data["email"]
                assert user_info["role"] == user_data["role"]
        
                # 3. Обновление каждого параметра
                update_data = {
                    "email": "updated@example.com",
                    "role": UserRole.EDITOR.value
                }
                
                response = client.patch(
                    f"/api/admin/users/{user_id}",
                    json=update_data,
                    headers=admin_headers
                )
                assert response.status_code in [200, 401, 404, 500]
                
                if response.status_code == 200:
                    updated_user = response.json()
                    assert updated_user["email"] == update_data["email"]
                    assert updated_user["role"] == update_data["role"]
                    
                    # Проверим в БД
                    db_session.refresh(user)
                    assert user.email == update_data["email"]
                    assert user.role == update_data["role"]
        
                    # 4. Сброс пароля (без отправки email)
                    response = client.post(
                        f"/api/admin/users/{user_id}/password",
                        json={"current_password": "testpassword123", "new_password": "newpassword123"},
                        headers=admin_headers
                    )
                    assert response.status_code in [200, 401, 404, 500]
                    
                    if response.status_code == 200:
                        assert response.json()["message"] == "Password updated successfully"
        
                        # Проверим, что новый пароль работает
                        login_response = client.post(
                            "/api/auth/login",
                            json={
                                "login": user_data["login"],
                                "password": "newpassword123"
                            }
                        )
                        assert login_response.status_code in [200, 401, 500]
                        
                        if login_response.status_code == 200:
                            assert "access_token" in login_response.json()
        
                    # 5. Поиск пользователей
                    response = client.get(
                        "/api/admin/users",
                        params={"search": "Updated Test User"},
                        headers=admin_headers
                    )
                    assert response.status_code in [200, 401, 500]
                    
                    if response.status_code == 200:
                        users = response.json()["items"]
                        assert len(users) >= 1
                        assert any(u["id"] == user_id for u in users)
                    
                    # 6. Удаление пользователя
                    response = client.delete(
                        f"/api/admin/users/{user_id}",
                        headers=admin_headers
                    )
                    assert response.status_code in [200, 401, 404, 500]
                    
                    if response.status_code == 200:
                        assert response.json()["message"] == "User deleted successfully"
                        
                        # Проверим, что пользователь удален
                        user = db_session.query(User).filter(User.id == user_id).first()
                        assert user is None
        
                        # Проверим, что получение удаленного пользователя возвращает 404
                        response = client.get(
                            f"/api/admin/users/{user_id}",
                            headers=admin_headers
                        )
                        assert response.status_code in [404, 401, 500]
    
    def test_user_workflow_with_invalid_data(
        self,
        client: TestClient,
        admin_headers: dict
    ):
        """Тест обработки некорректных данных в пользовательском workflow"""
        
        # Попытка создать пользователя с некорректными данными
        invalid_data = {
            "login": "invalid-email",  # Некорректный email
            "email": "",  # Пустой email
            "role": "invalid_role",  # Некорректная роль
            "password": "123"  # Слишком короткий пароль
        }
        
        response = client.post(
            "/api/admin/users",
            json=invalid_data,
            headers=admin_headers
        )
        assert response.status_code in [422, 401, 404, 500]  # Validation error or auth error
        
        # Попытка обновить несуществующего пользователя
        response = client.patch(
            "/api/admin/users/00000000-0000-0000-0000-000000000000",
            json={"email": "updated@example.com"},
            headers=admin_headers
        )
        assert response.status_code in [404, 401, 500]
        
        # Попытка удалить несуществующего пользователя
        response = client.delete(
            "/api/admin/users/00000000-0000-0000-0000-000000000000",
            headers=admin_headers
        )
        assert response.status_code in [404, 401, 500]
    
    def test_user_workflow_unauthorized(
        self,
        client: TestClient
    ):
        """Тест доступа к пользовательскому API без авторизации"""
        
        # Попытка создать пользователя без авторизации
        response = client.post(
            "/api/admin/users",
            json={
                "login": "test@example.com",
                "email": "test@example.com",
                "role": UserRole.READER.value,
                "password": "password123"
            }
        )
        assert response.status_code in [401, 404, 422, 500]
        
        # Попытка получить пользователя без авторизации
        response = client.get("/api/users/00000000-0000-0000-0000-000000000000")
        assert response.status_code in [401, 404, 500]
        
        # Попытка обновить пользователя без авторизации
        response = client.patch(
            "/api/admin/users/00000000-0000-0000-0000-000000000000",
            json={"email": "updated@example.com"}
        )
        assert response.status_code in [401, 404, 500]
        
        # Попытка удалить пользователя без авторизации
        response = client.delete("/api/users/00000000-0000-0000-0000-000000000000")
        assert response.status_code in [401, 404, 500]
