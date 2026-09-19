from unittest.mock import AsyncMock

import pytest

from app.services.chat_title_generator import (
    ChatTitleGenerator,
    is_default_chat_title,
    normalize_title,
)


def test_default_title_detection_is_normalized():
    assert is_default_chat_title(None)
    assert is_default_chat_title(" Новый чат ")
    assert is_default_chat_title("New Chat")
    assert not is_default_chat_title("Manual title")


def test_normalize_title_accepts_plain_or_json_title():
    assert normalize_title('  "Network configuration" ') == "Network configuration"
    assert normalize_title('{"title": "Проверка памяти"}') == "Проверка памяти"
    assert normalize_title("ok") is None


@pytest.mark.asyncio
async def test_generator_uses_dedicated_title_prompt_and_model_client(mock_llm_client):
    mock_llm_client.chat = AsyncMock(return_value={"content": "Настройка OSPF"})
    service = ChatTitleGenerator(mock_llm_client)

    title = await service.generate(
        user_message="Настрой OSPF",
        assistant_message="Вот пример конфигурации.",
    )

    assert title == "Настройка OSPF"
    mock_llm_client.chat.assert_awaited_once()
