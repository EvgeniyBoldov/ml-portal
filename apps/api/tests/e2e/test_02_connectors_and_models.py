"""
Test 02: Groq Connector + Models + Tool Instances

Scenarios:
1. Create Groq connector (instance with connector_type=model)
2. Create 3 LLM models (llama-3.1-8b-instant, llama-4-scout, gpt-oss-120b)
3. Create embedding model
4. Create MCP instances (mcp-sql, mcp-netbox)
5. Create data instances (data-sql, data-netbox)
6. Add credentials for Netbox
"""
import os
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.order(2)]

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


@pytest.mark.asyncio
async def test_create_groq_connector(client, admin_headers):
    """Create Groq connector instance for LLM models"""
    json_data = {
        "slug": "groq_api",
        "name": "Groq API",
        "description": "Groq API connector for LLM models",
        "instance_kind": "service",
        "placement": "remote",
        "connector_type": "model",
        "url": "https://api.groq.com/openai/v1",
        "config": {
            "api_key": GROQ_API_KEY,
        },
        "is_active": True,
    }
    response = await client.post(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
        json=json_data,
    )
    # If already exists, fetch it
    if response.status_code in [409, 500]:
        list_resp = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
        items = list_resp.json()
        data = next((i for i in items if i["slug"] == "groq_api"), None)
        assert data is not None, "Groq connector not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create Groq connector: {response.text}"
        data = response.json()
    assert data["slug"] == "groq_api"
    assert data["connector_type"] == "model"
    return data


@pytest.mark.asyncio
async def test_create_llm_model_llama31(client, admin_headers):
    """Create LLM model: llama-3.1-8b-instant"""
    # Get Groq connector
    instances_response = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
    instances = instances_response.json()
    groq = next((i for i in instances if i["slug"] == "groq_api"), None)
    assert groq is not None, "Groq connector not found"
    
    response = await client.post(
        "/api/v1/admin/models",
        headers=admin_headers,
        json={
            "alias": "llm.groq.llama31",
            "name": "Groq Llama 3.1 8B",
            "type": "llm_chat",
            "status": "available",
            "provider": "groq",
            "provider_model_name": "llama-3.1-8b-instant",
            "connector": "openai_http",
            "model_version": "llama-3.1-8b-instant",
            "instance_id": str(groq["id"]),
            "default_for_type": False,
            "extra_config": {
                "max_tokens": 8192,
                "temperature": 0.7,
            },
        },
    )
    if response.status_code in [409, 400]:
        list_resp = await client.get("/api/v1/admin/models", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((m for m in items if m["alias"] == "llm.groq.llama31"), None)
        assert data is not None, "Model not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create model: {response.text}"
        data = response.json()
    assert data["alias"] == "llm.groq.llama31"
    return data


@pytest.mark.asyncio
async def test_create_llm_model_llama4(client, admin_headers):
    """Create LLM model: llama-4-scout"""
    # Get Groq connector
    instances_response = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
    instances = instances_response.json()
    groq = next((i for i in instances if i["slug"] == "groq_api"), None)
    assert groq is not None, "Groq connector not found"
    
    response = await client.post(
        "/api/v1/admin/models",
        headers=admin_headers,
        json={
            "alias": "llm.groq.llama4",
            "name": "Groq Llama 4 Scout",
            "type": "llm_chat",
            "status": "available",
            "provider": "groq",
            "provider_model_name": "meta-llama/llama-4-scout-17b-16e-instruct",
            "connector": "openai_http",
            "model_version": "llama-4-scout",
            "instance_id": str(groq["id"]),
            "default_for_type": True,
            "extra_config": {
                "max_tokens": 8192,
                "temperature": 0.7,
            },
        },
    )
    if response.status_code in [409, 400]:
        list_resp = await client.get("/api/v1/admin/models", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((m for m in items if m["alias"] == "llm.groq.llama4"), None)
        assert data is not None, "Model not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create model: {response.text}"
        data = response.json()
    assert data["alias"] == "llm.groq.llama4"
    return data


@pytest.mark.asyncio
async def test_create_llm_model_gptoss(client, admin_headers):
    """Create LLM model: openai/gpt-oss-120b"""
    # Get Groq connector
    instances_response = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
    instances = instances_response.json()
    groq = next((i for i in instances if i["slug"] == "groq_api"), None)
    assert groq is not None, "Groq connector not found"
    
    response = await client.post(
        "/api/v1/admin/models",
        headers=admin_headers,
        json={
            "alias": "llm.groq.gptoss",
            "name": "Groq GPT OSS 120B",
            "type": "llm_chat",
            "status": "available",
            "provider": "groq",
            "provider_model_name": "openai/gpt-oss-120b",
            "connector": "openai_http",
            "model_version": "gpt-oss-120b",
            "instance_id": str(groq["id"]),
            "default_for_type": False,
            "extra_config": {
                "max_tokens": 16384,
                "temperature": 0.7,
            },
        },
    )
    if response.status_code in [409, 400]:
        list_resp = await client.get("/api/v1/admin/models", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((m for m in items if m["alias"] == "llm.groq.gptoss"), None)
        assert data is not None, "Model not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create model: {response.text}"
        data = response.json()
    assert data["alias"] == "llm.groq.gptoss"
    return data


@pytest.mark.asyncio
async def test_create_embedding_model(client, admin_headers):
    """Create embedding model"""
    response = await client.post(
        "/api/v1/admin/models",
        headers=admin_headers,
        json={
            "alias": "embed.local.minilm",
            "name": "Local MiniLM",
            "type": "embedding",
            "status": "available",
            "provider": "sentence-transformers",
            "provider_model_name": "all-MiniLM-L6-v2",
            "connector": "local_emb_http",
            "model_version": "all-MiniLM-L6-v2",
            "base_url": "http://emb:8001",
            "default_for_type": True,
            "extra_config": {
                "vector_dim": 384,
            },
        },
    )
    if response.status_code in [409, 400]:
        list_resp = await client.get("/api/v1/admin/models", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((m for m in items if m["alias"] == "embed.local.minilm"), None)
        assert data is not None, "Embedding model not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create embedding model: {response.text}"
        data = response.json()
    assert data["alias"] == "embed.local.minilm"
    return data


@pytest.mark.asyncio
async def test_create_mcp_sql_instance(client, admin_headers):
    """Create or get MCP SQL instance (remote service)"""
    json_data = {
        "slug": "mcp-sql-local",
        "name": "MCP SQL Local",
        "description": "Local SQL MCP service for testing",
        "instance_kind": "service",
        "placement": "remote",
        "connector_type": "mcp",
        "url": "http://mcp-sql:8080",
        "connection_config": {
            "db_type": "postgresql",
            "host": "postgres",
            "port": 5432,
        },
        "is_active": True,
    }
    response = await client.post(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
        json=json_data,
    )
    # If already exists, fetch it
    if response.status_code in [409, 500]:
        list_resp = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((i for i in items if i["slug"] == "mcp-sql-local"), None)
        assert data is not None, "MCP SQL instance not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create MCP SQL instance: {response.text}"
        data = response.json()
    assert data["slug"] == "mcp-sql-local"
    assert data["instance_kind"] == "service"
    assert data["placement"] == "remote"
    return data


@pytest.mark.asyncio
async def test_create_mcp_netbox_instance(client, admin_headers):
    """Create or get MCP Netbox instance (remote service)"""
    netbox_url = os.getenv("NETBOX_URL", "https://demo.netbox.dev/")
    json_data = {
        "slug": "mcp-netbox-demo",
        "name": "MCP Netbox Demo",
        "description": "Netbox demo MCP service",
        "instance_kind": "service",
        "placement": "remote",
        "connector_type": "mcp",
        "url": netbox_url,
        "connection_config": {
            "api_version": "v4",
        },
        "is_active": True,
    }
    response = await client.post(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
        json=json_data,
    )
    if response.status_code in [409, 500]:
        list_resp = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
        items = list_resp.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        data = next((i for i in items if i["slug"] == "mcp-netbox-demo"), None)
        assert data is not None, "MCP Netbox instance not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create MCP Netbox instance: {response.text}"
        data = response.json()
    assert data["slug"] == "mcp-netbox-demo"
    return data


@pytest.mark.asyncio
async def test_create_data_sql_instance(client, admin_headers):
    """Create or get data SQL instance (linked to mcp-sql)"""
    # First get the MCP SQL instance
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    mcp_sql = next((i for i in instances if i["slug"] == "mcp-sql-local"), None)
    assert mcp_sql is not None, "MCP SQL instance not found"
    
    json_data = {
        "slug": "data-sql-tickets",
        "name": "Data SQL Tickets",
        "description": "SQL data source for tickets",
        "instance_kind": "data",
        "placement": "remote",
        "connector_type": "data",
        "connector_subtype": "sql",
        "url": "http://postgres:5432",
        "access_via_instance_id": mcp_sql["id"],
        "config": {
            "database_name": "ml_portal",
            "table_name": "tickets",
        },
        "is_active": True,
    }
    response = await client.post(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
        json=json_data,
    )
    if response.status_code in [409, 500]:
        list_resp = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
        items = list_resp.json()
        data = next((i for i in items if i["slug"] == "data-sql-tickets"), None)
        assert data is not None, "Data SQL instance not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create data SQL instance: {response.text}"
        data = response.json()
    assert data["slug"] == "data-sql-tickets"
    assert data["instance_kind"] == "data"
    return data


@pytest.mark.asyncio
async def test_create_data_netbox_instance(client, admin_headers):
    """Create or get data Netbox instance (linked to mcp-netbox)"""
    # Get the MCP Netbox instance
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    mcp_netbox = next((i for i in instances if i["slug"] == "mcp-netbox-demo"), None)
    assert mcp_netbox is not None, "MCP Netbox instance not found"
    
    json_data = {
        "slug": "data-netbox-devices",
        "name": "Data Netbox Devices",
        "description": "Netbox devices data source",
        "instance_kind": "data",
        "placement": "remote",
        "connector_type": "data",
        "connector_subtype": "api",
        "url": "https://demo.netbox.dev/",
        "access_via_instance_id": mcp_netbox["id"],
        "config": {
            "base_path": "dcim/devices",
        },
        "is_active": True,
    }
    response = await client.post(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
        json=json_data,
    )
    if response.status_code in [409, 500]:
        list_resp = await client.get("/api/v1/admin/tool-instances", headers=admin_headers)
        items = list_resp.json()
        data = next((i for i in items if i["slug"] == "data-netbox-devices"), None)
        assert data is not None, "Data Netbox instance not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create data Netbox instance: {response.text}"
        data = response.json()
    assert data["slug"] == "data-netbox-devices"
    return data


@pytest.mark.asyncio
async def test_add_netbox_credentials(client, admin_headers):
    """Add credentials for Netbox"""
    netbox_token = os.getenv("NETBOX_API_TOKEN")
    if not netbox_token:
        pytest.skip("NETBOX_API_TOKEN not set in environment")
    
    # Get the MCP Netbox instance
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    mcp_netbox = next((i for i in instances if i["slug"] == "mcp-netbox-demo"), None)
    assert mcp_netbox is not None, "MCP Netbox instance not found"
    
    # Add credentials
    response = await client.post(
        f"/api/v1/admin/tool-instances/{mcp_netbox['id']}/credentials",
        headers=admin_headers,
        json={
            "scope": "default",
            "payload": {
                "api_token": netbox_token,
            },
        },
    )
    assert response.status_code in [200, 201], f"Failed to add credentials: {response.text}"
    
    return response.json()
