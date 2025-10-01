import pytest, respx, httpx
from app.adapters.impl.emb_http import HttpEmbeddingsClient

@pytest.mark.anyio
async def test_embed_texts_success():
    with respx.mock(base_url="https://emb") as rsx:
        rsx.post("/embed").mock(return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]}))
        cli = HttpEmbeddingsClient(base_url="https://emb", timeout=1.0)
        vecs = await cli.embed_texts(["hello", "world"])
        assert len(vecs) == 2 and len(vecs[0]) == 2

@pytest.mark.anyio
async def test_embed_error_raises():
    with respx.mock(base_url="https://emb") as rsx:
        rsx.post("/embed").mock(return_value=httpx.Response(400, text="bad"))
        cli = HttpEmbeddingsClient(base_url="https://emb", timeout=1.0)
        with pytest.raises(Exception):
            await cli.embed_texts(["x"])
