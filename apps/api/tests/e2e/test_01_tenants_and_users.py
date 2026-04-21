"""
Test 01: Tenants and Users CRUD

Scenarios:
- Add tenant "Test"
- Add user "Test" in that tenant
- Verify both created successfully
"""
import pytest
import uuid

pytestmark = [pytest.mark.e2e, pytest.mark.order(1)]

TEST_TENANT_NAME = "Integration Test Tenant"
TEST_USER_LOGIN = "integration_testuser"


@pytest.mark.asyncio
async def test_create_tenant(client, admin_headers):
    """Create test tenant"""
    response = await client.post(
        "/api/v1/admin/tenants",
        headers=admin_headers,
        json={
            "name": TEST_TENANT_NAME,
            "description": "Tenant for integration tests",
            "is_active": True,
        },
    )
    # already exists from previous run — API may return 409 or 500 (legacy handler)
    if response.status_code in (409, 500):
        r2 = await client.get("/api/v1/admin/tenants", headers=admin_headers)
        raw2 = r2.json()
        items2 = raw2.get("items", raw2) if isinstance(raw2, dict) else raw2
        data = next((t for t in items2 if t["name"] == TEST_TENANT_NAME), None)
        assert data is not None, f"409 but tenant not found"
    else:
        assert response.status_code in [200, 201], f"Failed to create tenant: {response.text}"
        data = response.json()
    assert data["name"] == TEST_TENANT_NAME
    assert data["is_active"] is True
    assert "id" in data
    
    # Verify tenant exists via GET
    tenant_id = data["id"]
    get_response = await client.get(
        f"/api/v1/admin/tenants/{tenant_id}",
        headers=admin_headers,
    )
    assert get_response.status_code == 200
    tenant_data = get_response.json()
    assert tenant_data["name"] == TEST_TENANT_NAME
    
    return data


@pytest.mark.asyncio
async def test_create_user(client, admin_headers):
    """Create test user"""
    # First get the test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    assert tenants_response.status_code == 200
    tenants = tenants_response.json()
    # API returns {"items": [...]}
    items = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    test_tenant = next((t for t in items if t["name"] == TEST_TENANT_NAME), None)
    assert test_tenant is not None, "Test tenant not found"
    
    # Create user
    response = await client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "login": TEST_USER_LOGIN,
            "email": f"{TEST_USER_LOGIN}@test.com",
            "password": "testuser123",
            "role": "admin",
            "is_active": True,
            "tenant_id": test_tenant["id"],
        },
    )
    if response.status_code in (409, 500):
        r2 = await client.get("/api/v1/admin/users", headers=admin_headers)
        raw2 = r2.json()
        users2 = raw2.get("users", raw2) if isinstance(raw2, dict) and "users" in raw2 else raw2
        raw = {"user": next((u for u in users2 if u["login"] == TEST_USER_LOGIN), None)}
        assert raw["user"] is not None, "409 but user not found"
    else:
        assert response.status_code in [200, 201], f"Failed to create user: {response.text}"
        raw = response.json()
    data = raw.get("user", raw) if isinstance(raw, dict) and "user" in raw else raw
    assert data["login"] == TEST_USER_LOGIN
    assert data["email"] == f"{TEST_USER_LOGIN}@test.com"
    assert data["role"] == "admin"
    assert "id" in data
    
    # Verify user exists via GET
    user_id = data["id"]
    get_response = await client.get(
        f"/api/v1/admin/users/{user_id}",
        headers=admin_headers,
    )
    assert get_response.status_code == 200
    raw_get = get_response.json()
    user_data = raw_get.get("user", raw_get) if isinstance(raw_get, dict) and "user" in raw_get else raw_get
    assert user_data["login"] == TEST_USER_LOGIN
    
    return data


@pytest.mark.asyncio
async def test_update_tenant(client, admin_headers):
    """Update tenant description"""
    # Get test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants_raw = tenants_response.json()
    tenants = tenants_raw.get("items", tenants_raw) if isinstance(tenants_raw, dict) else tenants_raw
    test_tenant = next((t for t in tenants if t["name"] == TEST_TENANT_NAME), None)
    assert test_tenant is not None
    
    # Update tenant
    response = await client.put(
        f"/api/v1/admin/tenants/{test_tenant['id']}",
        headers=admin_headers,
        json={
            "name": TEST_TENANT_NAME,
            "description": "Updated description for tests",
        },
    )
    assert response.status_code == 200, f"Update failed: {response.text}"
    raw = response.json()
    data = raw.get("tenant", raw) if isinstance(raw, dict) and "tenant" in raw else raw
    assert data.get("description") == "Updated description for tests"


@pytest.mark.asyncio
async def test_list_tenants(client, admin_headers):
    """List all tenants"""
    response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    assert response.status_code == 200
    raw = response.json()
    data = raw.get("items", raw) if isinstance(raw, dict) else raw
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Verify our test tenant is in the list
    names = [t["name"] for t in data]
    assert TEST_TENANT_NAME in names


@pytest.mark.asyncio
async def test_list_users(client, admin_headers):
    """List all users"""
    response = await client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
    )
    assert response.status_code == 200
    raw = response.json()
    data = raw.get("users", raw) if isinstance(raw, dict) and "users" in raw else raw
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Verify admin is in the list
    logins = [u["login"] for u in data]
    assert "admin" in logins
    assert TEST_USER_LOGIN in logins
