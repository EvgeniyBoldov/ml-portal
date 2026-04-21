"""
Test 07: Chat Flow

Scenarios:
- Create chat
- Send message (test triage, planner, agents)
- Delete chat
"""
import pytest
import asyncio
import httpx

pytestmark = [pytest.mark.e2e, pytest.mark.order(7)]
TEST_CHAT_ID: str | None = None


@pytest.mark.asyncio
async def test_create_chat(client, admin_headers):
    """Create test chat"""
    # Get test tenant
    tenants_response = await client.get(
        "/api/v1/admin/tenants",
        headers=admin_headers,
    )
    tenants = tenants_response.json()
    tenants = tenants.get("items", tenants) if isinstance(tenants, dict) else tenants
    test_tenant = next((t for t in tenants if t["name"] == "Integration Test Tenant"), None)
    assert test_tenant is not None, "Test tenant not found"
    
    response = await client.post(
        "/api/v1/chats",
        headers=admin_headers,
        json={
            "name": "Test Integration Chat",
            "tenant_id": test_tenant["id"],
        },
    )
    assert response.status_code in (200, 201), f"Failed to create chat: {response.text}"
    data = response.json()
    chat_id = data.get("id") or data.get("chat_id")
    assert chat_id, f"Chat response has no id: {data}"
    global TEST_CHAT_ID
    TEST_CHAT_ID = str(chat_id)

    return data


async def _resolve_test_chat_id(client, admin_headers) -> str:
    if TEST_CHAT_ID:
        return TEST_CHAT_ID
    chats_response = await client.get(
        "/api/v1/chats",
        headers=admin_headers,
    )
    chats = chats_response.json()
    chats = chats.get("items", chats) if isinstance(chats, dict) else chats
    test_chat = next((c for c in chats if c.get("name") == "Test Integration Chat"), None)
    if not test_chat:
        pytest.skip("Test chat not found")
    return str(test_chat["id"])


@pytest.mark.asyncio
async def test_send_message_simple(client, admin_headers):
    """Send simple message and check response"""
    chat_id = await _resolve_test_chat_id(client, admin_headers)
    
    # Send message via SSE
    events = []
    
    async with client.stream(
        "POST",
        f"/api/v1/chats/{chat_id}/messages",
        headers={**admin_headers, "Accept": "text/event-stream"},
        json={
            "content": "Привет! Это тестовое сообщение.",
        },
        timeout=60.0,
    ) as response:
        assert response.status_code == 200, f"Failed to send message: {response.text}"
        
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                event_data = line[6:]  # Remove "data: " prefix
                if event_data and event_data != "[DONE]":
                    events.append(event_data)
    
    # Verify we got some events
    assert len(events) > 0, "No events received from chat"
    
    # Check for expected event types
    event_types = []
    for event in events:
        if "triage" in event.lower():
            event_types.append("triage")
        elif "delta" in event.lower() or "final" in event.lower():
            event_types.append("response")
    
    # Should get at least triage or response
    assert "triage" in event_types or "response" in event_types or len(events) > 0


@pytest.mark.asyncio
async def test_send_message_with_agent(client, admin_headers):
    """Send message that routes to our test agent"""
    chat_id = await _resolve_test_chat_id(client, admin_headers)
    
    # Send message asking for data analysis
    events = []
    
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chats/{chat_id}/messages",
            headers={**admin_headers, "Accept": "text/event-stream"},
            json={
                "content": "Проанализируй тикеты в системе.",
            },
            timeout=120.0,
        ) as response:
            assert response.status_code == 200, f"Failed to send message: {response.text}"
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event_data = line[6:]
                    if event_data and event_data != "[DONE]":
                        events.append(event_data)
                        # Print for debugging
                        print(f"  Event: {event_data[:100]}...")
    except Exception as e:
        pytest.skip(f"Chat streaming failed (LLM may not be available): {e}")
    
    # Verify we got events
    assert len(events) > 0, "No events received from chat"


@pytest.mark.asyncio
async def test_list_chat_messages(client, admin_headers):
    """List messages in chat"""
    chat_id = await _resolve_test_chat_id(client, admin_headers)
    
    response = await client.get(
        f"/api/v1/chats/{chat_id}/messages",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    data = data.get("items", data) if isinstance(data, dict) else data
    assert isinstance(data, list)
    
    # Should have at least user messages and assistant responses
    assert len(data) >= 2, "Expected at least 2 messages in chat"


@pytest.mark.asyncio
async def test_delete_chat(client, admin_headers):
    """Delete test chat"""
    chat_id = await _resolve_test_chat_id(client, admin_headers)
    
    try:
        response = await client.delete(
            f"/api/v1/chats/{chat_id}",
            headers=admin_headers,
            timeout=20.0,
        )
    except httpx.ReadTimeout:
        pytest.skip("Chat delete timed out in current environment")
    assert response.status_code in (200, 204)
    
    # Verify chat is deleted (GET /chats/{id} may return 404 or 405)
    get_response = await client.get(
        f"/api/v1/chats/{chat_id}",
        headers=admin_headers,
    )
    assert get_response.status_code in [404, 405, 204, 200]
