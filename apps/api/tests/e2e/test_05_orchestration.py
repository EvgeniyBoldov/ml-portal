"""
Test 05: Orchestration Settings

Scenarios:
- Add orchestrators (triage, planner, memory)
- Update system LLM roles
"""
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.order(5)]


@pytest.mark.asyncio
async def test_update_triage_role(client, admin_headers):
    """Update triage system LLM role"""
    # Get models
    models_response = await client.get(
        "/api/v1/admin/models",
        headers=admin_headers,
    )
    models = models_response.json()
    models = models.get("items", models) if isinstance(models, dict) else models
    llm_model = next((m for m in models if m["type"] == "llm_chat"), None)
    assert llm_model is not None, "LLM model not found"
    
    # Get active triage role
    response = await client.get(
        "/api/v1/admin/system-llm-roles/active/triage",
        headers=admin_headers,
    )
    if response.status_code == 404:
        pytest.skip("No active triage role found")
    assert response.status_code == 200, f"Failed to get triage role: {response.text}"
    role = response.json()
    
    # Update role via PUT
    response = await client.put(
        f"/api/v1/admin/system-llm-roles/{role['id']}",
        headers=admin_headers,
        json={
            "model": llm_model["alias"],
            "temperature": 0.3,
            "max_tokens": 2000,
            "identity": "Ты — триаж-роутер. Определи тип запроса пользователя.",
            "mission": "Определить intent запроса и выбрать подходящего агента.",
            "rules": "Отвечай JSON: {\"intent\": \"...\", \"agent_slug\": \"...\", \"confidence\": 0.9}",
            "is_active": True,
        },
    )
    assert response.status_code == 200, f"Failed to update triage: {response.text}"
    data = response.json()
    assert data["is_active"] is True
    
    return data


@pytest.mark.asyncio
async def test_update_planner_role(client, admin_headers):
    """Update planner system LLM role"""
    # Get models
    models_response = await client.get(
        "/api/v1/admin/models",
        headers=admin_headers,
    )
    models = models_response.json()
    models = models.get("items", models) if isinstance(models, dict) else models
    llm_model = next((m for m in models if m["type"] == "llm_chat"), None)
    assert llm_model is not None, "LLM model not found"
    
    # Get active planner role
    response = await client.get(
        "/api/v1/admin/system-llm-roles/active/planner",
        headers=admin_headers,
    )
    if response.status_code == 404:
        pytest.skip("No active planner role found")
    assert response.status_code == 200, f"Failed to get planner role: {response.text}"
    role = response.json()
    
    # Update role via PUT
    response = await client.put(
        f"/api/v1/admin/system-llm-roles/{role['id']}",
        headers=admin_headers,
        json={
            "model": llm_model["alias"],
            "temperature": 0.2,
            "max_tokens": 4000,
            "identity": "Ты — планировщик задач.",
            "mission": "Разбить задачу на шаги и определить последовательность вызовов.",
            "rules": "1. Определи инструменты\n2. Составь план\n3. Укажи зависимости",
            "is_active": True,
        },
    )
    assert response.status_code == 200, f"Failed to update planner: {response.text}"
    data = response.json()
    assert data["is_active"] is True
    
    return data


@pytest.mark.asyncio
async def test_update_memory_role(client, admin_headers):
    """Update memory (summary) system LLM role"""
    # Get models
    models_response = await client.get(
        "/api/v1/admin/models",
        headers=admin_headers,
    )
    models = models_response.json()
    models = models.get("items", models) if isinstance(models, dict) else models
    llm_model = next((m for m in models if m["type"] == "llm_chat"), None)
    assert llm_model is not None, "LLM model not found"
    
    # Get active summary role
    response = await client.get(
        "/api/v1/admin/system-llm-roles/active/summary",
        headers=admin_headers,
    )
    if response.status_code == 404:
        pytest.skip("No active summary role found")
    assert response.status_code == 200, f"Failed to get summary role: {response.text}"
    role = response.json()
    
    # Update role via PUT
    response = await client.put(
        f"/api/v1/admin/system-llm-roles/{role['id']}",
        headers=admin_headers,
        json={
            "model": llm_model["alias"],
            "temperature": 0.1,
            "max_tokens": 1000,
            "identity": "Ты — система памяти диалога.",
            "mission": "Извлекать ключевые факты из разговора.",
            "rules": "Сохраняй: контекст, уточнения, фильтры. Отвечай кратко.",
            "is_active": True,
        },
    )
    assert response.status_code == 200, f"Failed to update summary: {response.text}"
    data = response.json()
    assert data["is_active"] is True
    
    return data


@pytest.mark.asyncio
async def test_get_orchestration_settings(client, admin_headers):
    """Get all system LLM roles"""
    response = await client.get(
        "/api/v1/admin/system-llm-roles",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    
    # Verify roles exist (list of roles)
    assert isinstance(data, list)
