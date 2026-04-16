"""
Test 06: RBAC Rules

Scenarios:
- Add rules for data instances access
"""
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.order(6)]


@pytest.mark.asyncio
async def test_create_rbac_rule_for_sql(client, admin_headers):
    """Create RBAC rule allowing access to data-sql instance"""
    # Get test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    test_tenant = next((t for t in tenants if t["name"] == "Integration Test Tenant"), None)
    assert test_tenant is not None, "Test tenant not found"
    
    # Get data instances
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    data_sql = next((i for i in instances if i["slug"] == "data-sql-tickets"), None)
    
    if not data_sql:
        pytest.skip("Data SQL instance not found")
    
    # Create allow rule for tenant
    response = await client.post(
        "/api/v1/admin/rbac/rules",
        headers=admin_headers,
        json={
            "scope": "tenant",
            "tenant_id": test_tenant["id"],
            "resource_type": "tool_instance",
            "resource_id": data_sql["id"],
            "action": "allow",
            "effect": "allow",
        },
    )
    assert response.status_code == 201, f"Failed to create RBAC rule: {response.text}"
    data = response.json()
    assert data["effect"] == "allow"
    
    return data


@pytest.mark.asyncio
async def test_create_rbac_rule_for_netbox(client, admin_headers):
    """Create RBAC rule allowing access to data-netbox instance"""
    # Get test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    test_tenant = next((t for t in tenants if t["name"] == "Integration Test Tenant"), None)
    assert test_tenant is not None, "Test tenant not found"
    
    # Get data instances
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    data_netbox = next((i for i in instances if i["slug"] == "data-netbox-devices"), None)
    
    if not data_netbox:
        pytest.skip("Data Netbox instance not found")
    
    # Create allow rule for tenant
    response = await client.post(
        "/api/v1/admin/rbac/rules",
        headers=admin_headers,
        json={
            "scope": "tenant",
            "tenant_id": test_tenant["id"],
            "resource_type": "tool_instance",
            "resource_id": data_netbox["id"],
            "action": "allow",
            "effect": "allow",
        },
    )
    assert response.status_code == 201, f"Failed to create RBAC rule: {response.text}"
    data = response.json()
    assert data["effect"] == "allow"
    
    return data


@pytest.mark.asyncio
async def test_list_rbac_rules(client, admin_headers):
    """List all RBAC rules"""
    response = await client.get(
        "/api/v1/admin/rbac/rules",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # Should have our created rules
    assert len(data) >= 2, "Expected at least 2 RBAC rules"
