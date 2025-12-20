"""
Integration tests for Users API on real database
Tests: login, password change, user deletion, user creation
Uses real HTTP requests to running server
"""
import pytest
import httpx


BASE_URL = "http://api:8000"  # Internal Docker network address


@pytest.fixture
async def client():
    """Create async HTTP client for real server"""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as ac:
        yield ac


@pytest.fixture
async def admin_token(client: httpx.AsyncClient):
    """Login as admin and get token"""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "login": "admin",
            "password": "admin"
        }
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return data["access_token"]


class TestUsersRealDB:
    """Test users operations on real database"""
    
    @pytest.mark.asyncio
    async def test_01_admin_login(self, client: httpx.AsyncClient):
        """Test admin can login"""
        print("\n🔐 Testing admin login...")
        
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": "admin",
                "password": "admin"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["login"] == "admin"
        print("✅ Admin login works")
    
    @pytest.mark.asyncio
    async def test_02_create_test_user(self, client: httpx.AsyncClient, admin_token: str):
        """Test creating a new user"""
        print("\n👤 Testing user creation...")
        
        response = await client.post(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "login": "test_integration_user",
                "email": "test_integration@example.com",
                "password": "TestPassword123!",
                "full_name": "Test Integration User",
                "role": "editor",
                "is_active": True
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code in [200, 201], f"User creation failed: {response.text}"
        data = response.json()
        assert data["login"] == "test_integration_user"
        assert data["email"] == "test_integration@example.com"
        assert data["role"] == "editor"
        print(f"✅ User created with ID: {data['id']}")
        
        return data["id"]
    
    @pytest.mark.asyncio
    async def test_03_new_user_login(self, client: httpx.AsyncClient):
        """Test new user can login"""
        print("\n🔐 Testing new user login...")
        
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": "test_integration_user",
                "password": "TestPassword123!"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"New user login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["login"] == "test_integration_user"
        print("✅ New user login works")
        
        return data["access_token"]
    
    @pytest.mark.asyncio
    async def test_04_change_password(self, client: httpx.AsyncClient, admin_token: str):
        """Test password change"""
        print("\n🔑 Testing password change...")
        
        # Get user ID first
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"search": "test_integration_user"}
        )
        assert response.status_code == 200
        users = response.json()["items"]
        user = next((u for u in users if u["login"] == "test_integration_user"), None)
        assert user is not None, "Test user not found"
        user_id = user["id"]
        
        # Change password
        response = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "password": "NewPassword456!"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"Password change failed: {response.text}"
        print("✅ Password changed")
        
        # Try login with old password (should fail)
        print("\n🔐 Testing login with old password...")
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": "test_integration_user",
                "password": "TestPassword123!"
            }
        )
        print(f"Old password login status: {response.status_code}")
        assert response.status_code == 401, "Old password should not work"
        print("✅ Old password rejected")
        
        # Try login with new password (should work)
        print("\n🔐 Testing login with new password...")
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": "test_integration_user",
                "password": "NewPassword456!"
            }
        )
        print(f"New password login status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"New password login failed: {response.text}"
        print("✅ New password works")
    
    @pytest.mark.asyncio
    async def test_05_update_user(self, client: httpx.AsyncClient, admin_token: str):
        """Test updating user details"""
        print("\n✏️ Testing user update...")
        
        # Get user ID
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"search": "test_integration_user"}
        )
        users = response.json()["items"]
        user = next((u for u in users if u["login"] == "test_integration_user"), None)
        user_id = user["id"]
        
        # Update user
        response = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "full_name": "Updated Test User",
                "role": "reader"
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"User update failed: {response.text}"
        data = response.json()
        assert data["full_name"] == "Updated Test User"
        assert data["role"] == "reader"
        print("✅ User updated")
    
    @pytest.mark.asyncio
    async def test_06_deactivate_user(self, client: httpx.AsyncClient, admin_token: str):
        """Test deactivating user"""
        print("\n🚫 Testing user deactivation...")
        
        # Get user ID
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"search": "test_integration_user"}
        )
        users = response.json()["items"]
        user = next((u for u in users if u["login"] == "test_integration_user"), None)
        user_id = user["id"]
        
        # Deactivate user
        response = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "is_active": False
            }
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200, f"User deactivation failed: {response.text}"
        assert response.json()["is_active"] is False
        print("✅ User deactivated")
        
        # Try login (should fail)
        print("\n🔐 Testing login with deactivated user...")
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": "test_integration_user",
                "password": "NewPassword456!"
            }
        )
        print(f"Deactivated user login status: {response.status_code}")
        assert response.status_code == 401, "Deactivated user should not be able to login"
        print("✅ Deactivated user cannot login")
    
    @pytest.mark.asyncio
    async def test_07_delete_user(self, client: httpx.AsyncClient, admin_token: str):
        """Test deleting user"""
        print("\n🗑️ Testing user deletion...")
        
        # Get user ID
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"search": "test_integration_user"}
        )
        users = response.json()["items"]
        user = next((u for u in users if u["login"] == "test_integration_user"), None)
        assert user is not None, "Test user not found"
        user_id = user["id"]
        
        # Delete user
        response = await client.delete(
            f"/api/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"Status: {response.status_code}")
        if response.status_code != 204:
            print(f"Response: {response.text}")
        
        assert response.status_code == 204, f"User deletion failed: {response.text}"
        print("✅ User deleted")
        
        # Verify user is gone
        print("\n🔍 Verifying user is deleted...")
        response = await client.get(
            f"/api/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        print(f"Get deleted user status: {response.status_code}")
        assert response.status_code == 404, "Deleted user should not be found"
        print("✅ User is gone from database")
    
    @pytest.mark.asyncio
    async def test_08_list_users(self, client: httpx.AsyncClient, admin_token: str):
        """Test listing users"""
        print("\n📋 Testing user list...")
        
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        print(f"Status: {response.status_code}")
        
        assert response.status_code == 200, f"User list failed: {response.text}"
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) > 0
        print(f"✅ Found {data['total']} users")
    
    @pytest.mark.asyncio
    async def test_09_search_users(self, client: httpx.AsyncClient, admin_token: str):
        """Test searching users"""
        print("\n🔍 Testing user search...")
        
        response = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"search": "admin"}
        )
        
        print(f"Status: {response.status_code}")
        
        assert response.status_code == 200, f"User search failed: {response.text}"
        data = response.json()
        assert len(data["items"]) > 0
        assert any(u["login"] == "admin" for u in data["items"])
        print(f"✅ Search found {len(data['items'])} users")
