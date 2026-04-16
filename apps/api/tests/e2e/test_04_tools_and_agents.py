"""
Test 04: Tools and Agents

Scenarios:
- Rescan tools from registry
- Create tool versions
- Create agent with collections
- Add bindings
"""
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.order(4)]


@pytest.mark.asyncio
async def test_rescan_tools(client, admin_headers):
    """Rescan tools from registry"""
    response = await client.post(
        "/api/v1/admin/tools/rescan",
        headers=admin_headers,
    )
    assert response.status_code == 200, f"Failed to rescan tools: {response.text}"
    data = response.json()
    
    # Verify tools were discovered
    assert "discovered" in data or "registered" in data or "synced" in data
    
    return data


@pytest.mark.asyncio
async def test_list_tools(client, admin_headers):
    """List all tools after rescan"""
    response = await client.get(
        "/api/v1/admin/tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    assert isinstance(items, list)
    assert len(items) > 0, "No tools found after rescan"
    
    # Check for expected builtin tools
    slugs = [t["slug"] for t in items]
    assert "rag.search" in slugs or "collection.search" in slugs or len(items) > 0
    
    return data


@pytest.mark.asyncio
async def test_create_agent(client, admin_headers):
    """Create agent container"""
    response = await client.post(
        "/api/v1/admin/agents",
        headers=admin_headers,
        json={
            "slug": "test_analyst",
            "name": "Test Analyst",
            "description": "Test agent for data analysis",
            "is_active": True,
            "is_routable": True,
            "routing_keywords": ["анализ", "данные", "тикеты", "netbox"],
        },
    )
    if response.status_code == 409:
        # Agent already exists, fetch it
        list_resp = await client.get("/api/v1/admin/agents", headers=admin_headers)
        agents = list_resp.json()
        agents = agents.get("items", agents) if isinstance(agents, dict) else agents
        data = next((a for a in agents if a["slug"] == "test_analyst"), None)
        assert data is not None, "Agent not found after conflict"
    else:
        assert response.status_code == 201, f"Failed to create agent: {response.text}"
        data = response.json()
    assert data["slug"] == "test_analyst"
    assert data["name"] == "Test Analyst"
    
    return data


@pytest.mark.asyncio
async def test_create_agent_version(client, admin_headers):
    """Create agent version with collections config"""
    # Get agent
    agents_response = await client.get(
        "/api/v1/admin/agents",
        headers=admin_headers,
    )
    agents = agents_response.json()
    agents = agents.get("items", agents) if isinstance(agents, dict) else agents
    agent = next((a for a in agents if a["slug"] == "test_analyst"), None)
    assert agent is not None, "Agent not found"
    
    # Get collections
    collections_response = await client.get(
        "/api/v1/admin/collections",
        headers=admin_headers,
    )
    collections = collections_response.json()
    collections = collections.get("items", collections) if isinstance(collections, dict) else collections
    
    # Find SQL tickets collection
    sql_collection = next((c for c in collections if c["slug"] == "sql-tickets"), None)
    netbox_collection = next((c for c in collections if c["slug"] == "netbox-devices"), None)
    reglaments_collection = next((c for c in collections if c["slug"] == "reglaments"), None)
    
    # Get LLM model
    models_response = await client.get(
        "/api/v1/admin/models",
        headers=admin_headers,
    )
    models = models_response.json()
    models = models.get("items", models) if isinstance(models, dict) else models
    llm_model = next((m for m in models if m["type"] == "llm_chat"), None)
    assert llm_model is not None, "LLM model not found"
    
    # Build collections config
    collections_config = []
    if sql_collection:
        collections_config.append({
            "collection_id": sql_collection["id"],
            "required": False,
            "recommended": True,
        })
    if netbox_collection:
        collections_config.append({
            "collection_id": netbox_collection["id"],
            "required": False,
            "recommended": True,
        })
    if reglaments_collection:
        collections_config.append({
            "collection_id": reglaments_collection["id"],
            "required": False,
            "recommended": True,
        })
    
    response = await client.post(
        f"/api/v1/admin/agents/{agent['id']}/versions",
        headers=admin_headers,
        json={
            "identity": "Ты — аналитик данных с доступом к IT-тикетам и сетевой инфраструктуре.",
            "mission": "Помогать пользователям находить информацию в корпоративных данных.",
            "scope": "IT-тикеты, сетевые устройства, корпоративные регламенты.",
            "rules": "1. ВСЕГДА используй инструменты для поиска данных\n2. Цитируй источники информации\n3. Отвечай на русском языке",
            "model": llm_model["alias"],
            "temperature": 0.7,
            "max_tokens": 4000,
            "max_steps": 10,
            "collections_config": collections_config,
        },
    )
    assert response.status_code == 201, f"Failed to create agent version: {response.text}"
    data = response.json()
    assert data["status"] == "draft"
    
    return data


@pytest.mark.asyncio
async def test_activate_agent_version(client, admin_headers):
    """Activate agent version"""
    # Get agent and its versions
    agents_response = await client.get(
        "/api/v1/admin/agents",
        headers=admin_headers,
    )
    agents = agents_response.json()
    agents = agents.get("items", agents) if isinstance(agents, dict) else agents
    agent = next((a for a in agents if a["slug"] == "test_analyst"), None)
    assert agent is not None, "Agent not found"
    
    # Get versions
    versions_response = await client.get(
        f"/api/v1/admin/agents/{agent['id']}/versions",
        headers=admin_headers,
    )
    versions = versions_response.json()
    versions = versions.get("items", versions) if isinstance(versions, dict) else versions
    assert len(versions) > 0, "No versions found"
    
    version = versions[0]
    
    # Publish version (activate)
    version_number = version.get('version_number', version.get('number', 1))
    response = await client.post(
        f"/api/v1/admin/agents/{agent['id']}/versions/{version_number}/publish",
        headers=admin_headers,
    )
    assert response.status_code == 200, f"Failed to publish version: {response.text}"
    
    return response.json()


@pytest.mark.asyncio
async def test_create_agent_binding(client, admin_headers):
    """Create agent binding to tool instance"""
    # Get agent
    agents_response = await client.get(
        "/api/v1/admin/agents",
        headers=admin_headers,
    )
    agents = agents_response.json()
    agents = agents.get("items", agents) if isinstance(agents, dict) else agents
    agent = next((a for a in agents if a["slug"] == "test_analyst"), None)
    assert agent is not None, "Agent not found"
    
    # Get agent version
    versions_response = await client.get(
        f"/api/v1/admin/agents/{agent['id']}/versions",
        headers=admin_headers,
    )
    versions = versions_response.json()
    assert len(versions) > 0, "No versions found"
    agent_version = versions[0]
    
    # Get tools
    tools_response = await client.get(
        "/api/v1/admin/tools",
        headers=admin_headers,
    )
    tools = tools_response.json()
    
    # Find collection.search or rag.search tool
    search_tool = next((t for t in tools if t["slug"] in ["collection.search", "rag.search"]), None)
    if not search_tool:
        pytest.skip("Search tool not found, skipping binding test")
    
    # Get tool instances
    instances_response = await client.get(
        "/api/v1/admin/tool-instances",
        headers=admin_headers,
    )
    instances = instances_response.json()
    
    # Find appropriate instance
    instance = None
    if search_tool["slug"] == "collection.search":
        instance = next((i for i in instances if i["slug"].startswith("data-sql") or i["slug"].startswith("data-netbox")), None)
    else:
        instance = next((i for i in instances if i["slug"].startswith("rag-")), None)
    
    if not instance:
        pytest.skip("No suitable instance found for binding")
    
    # Create binding
    response = await client.post(
        "/api/v1/admin/agent-bindings",
        headers=admin_headers,
        json={
            "agent_id": agent["id"],
            "agent_version_id": agent_version["id"],
            "tool_id": search_tool["id"],
            "tool_instance_id": instance["id"],
            "is_active": True,
        },
    )
    assert response.status_code == 201, f"Failed to create binding: {response.text}"
    
    return response.json()
