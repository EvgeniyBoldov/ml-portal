import pytest, respx, httpx, anyio
from app.adapters.impl.llm_http import HttpLLMClient

@pytest.mark.anyio
async def test_chat_success():
    with respx.mock(base_url="https://llm") as rsx:
        route = rsx.post("/chat").mock(return_value=httpx.Response(200, json={"ok": True, "id": "1"}))
        cli = HttpLLMClient(base_url="https://llm", timeout=1.0)
        data = await cli.chat([{"role": "user", "content": "hi"}])
        assert data["ok"] is True
        assert route.called

@pytest.mark.anyio
async def test_chat_error_raises():
    with respx.mock(base_url="https://llm") as rsx:
        rsx.post("/chat").mock(return_value=httpx.Response(500, text="boom"))
        cli = HttpLLMClient(base_url="https://llm", timeout=1.0)
        with pytest.raises(Exception):
            await cli.chat([{"role": "user", "content": "hi"}])

@pytest.mark.anyio
async def test_chat_stream_yields_chunks():
    with respx.mock(base_url="https://llm") as rsx:
        async def _stream(request):
            return httpx.Response(200, content="a\nb\n", headers={})
        rsx.post("/chat/stream").mock(side_effect=_stream)
        cli = HttpLLMClient(base_url="https://llm", timeout=1.0)
        chunks = []
        async for ch in cli.chat_stream([{"role": "user", "content": "hi"}]):
            chunks.append(ch)
        assert "a" in ''.join(chunks)
        assert "b" in ''.join(chunks)
