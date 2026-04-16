"""
Test 99: Cleanup

Scenarios:
- Delete all created entities in reverse order
"""
import pytest

pytestmark = [pytest.mark.order(99), pytest.mark.cleanup]


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_agents(client, admin_headers):
    """Delete test agent"""
    # Get agent
    agents_response = await client.get(
        "/api/v1/admin/agents",
        headers=admin_headers,
    )
    agents = agents_response.json()
    test_agent = next((a for a in agents if a["slug"] == "test-analyst"), None)
    
    if not test_agent:
        pytest.skip("Test agent not found for cleanup")
    
    response = await client.delete(
        f"/api/v1/admin/agents/{test_agent['id']}",
        headers=admin_headers,
    )
    assert response.status_code in [200, 204]
    
    # Verify deleted
    get_response = await client.get(
        f"/api/v1/admin/agents/{test_agent['id']}",
        headers=admin_headers,
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_collections(client, admin_headers):
    """Delete all test collections"""
    collections_response = await client.get(
        "/api/v1/admin/collections",
        headers=admin_headers,
    )
    collections = collections_response.json()
    collections = collections.get("items", collections) if isinstance(collections, dict) else collections
    
    test_slugs = ["sql-tickets", "netbox-devices", "reglaments", "switch-configs", "vector-articles"]
    
    for collection in collections:
        if collection["slug"] in test_slugs:
            response = await client.delete(
                f"/api/v1/admin/collections/{collection['id']}",
                headers=admin_headers,
            )
            assert response.status_code in [200, 204]
            print(f"  ✅ Deleted collection: {collection['slug']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_tool_instances(client, admin_headers):
    """Delete all test tool instances"""
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    
    test_slugs = ["mcp-sql-local", "mcp-netbox-demo", "data-sql-tickets", "data-netbox-devices"]
    
    for instance in instances:
        if instance["slug"] in test_slugs:
            response = await client.delete(
                f"/api/v1/admin/tool-instances/{instance['id']}",
                headers=admin_headers,
            )
            assert response.status_code in [200, 204]
            print(f"  ✅ Deleted instance: {instance['slug']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_models(client, admin_headers):
    """Delete test models"""
    models_response = await client.get(
        "/api/v1/admin/models",
        headers=admin_headers,
    )
    models = models_response.json()
    models = models.get("items", models) if isinstance(models, dict) else models
    
    test_aliases = ["llm.groq.llama4", "embed.local.minilm"]
    
    for model in models:
        if model["alias"] in test_aliases:
            response = await client.delete(
                f"/api/v1/admin/models/{model['id']}",
                headers=admin_headers,
            )
            assert response.status_code in [200, 204]
            print(f"  ✅ Deleted model: {model['alias']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_rbac_rules(client, admin_headers):
    """Delete test RBAC rules"""
    # List all rules
    response = await client.get(
        "/api/v1/admin/rbac/rules",
        headers=admin_headers,
    )
    if response.status_code == 200:
        rules = response.json()
        
        # Delete rules for test tenant instances
        for rule in rules:
            if rule.get("scope") == "tenant":
                delete_response = await client.delete(
                    f"/api/v1/admin/rbac/rules/{rule['id']}",
                    headers=admin_headers,
                )
                if delete_response.status_code in [200, 204]:
                    print(f"  ✅ Deleted RBAC rule: {rule['id']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_users(client, admin_headers):
    """Delete test users (except admin)"""
    users_response = await client.get(
        "/api/v1/admin/users",
        headers=admin_headers,
    )
    users = users_response.json()
    users = users.get("users", users) if isinstance(users, dict) else users
    
    for user in users:
        if user["login"] == "testuser":
            response = await client.delete(
                f"/api/v1/admin/users/{user['id']}",
                headers=admin_headers,
            )
            assert response.status_code in [200, 204]
            print(f"  ✅ Deleted user: {user['login']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_delete_tenants(client, admin_headers):
    """Delete test tenants (except default)"""
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    
    for tenant in tenants:
        if tenant["name"] == "Integration Test Tenant":
            response = await client.delete(
                f"/api/v1/admin/tenants/{tenant['id']}",
                headers=admin_headers,
            )
            assert response.status_code in [200, 204]
            print(f"  ✅ Deleted tenant: {tenant['name']}")


@pytest.mark.asyncio
@pytest.mark.cleanup
async def test_verify_cleanup(client, admin_headers):
    """Verify all test entities are deleted"""
    # Check agents
    agents_response = await client.get("/api/v1/admin/agents", headers=admin_headers)
    agents = agents_response.json()
    assert "test-analyst" not in [a["slug"] for a in agents]
    
    # Check collections
    collections_response = await client.get("/api/v1/admin/collections", headers=admin_headers)
    collections = collections_response.json()
    collections = collections.get("items", collections) if isinstance(collections, dict) else collections
    test_slugs = ["sql-tickets", "netbox-devices", "reglaments", "switch-configs"]
    collection_slugs = [c["slug"] for c in collections]
    for slug in test_slugs:
        assert slug not in collection_slugs, f"Collection {slug} not deleted"
    
    # Check users
    users_response = await client.get("/api/v1/admin/users", headers=admin_headers)
    users = users_response.json()
    users = users.get("users", users) if isinstance(users, dict) else users
    assert "testuser" not in [u["login"] for u in users]
    
    # Check tenants
    tenants_response = await client.get("/api/v1/admin/tenants", headers=admin_headers)
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    assert "Integration Test Tenant" not in [t["name"] for t in tenants]
    
    print("  ✅ All test entities cleaned up successfully")
