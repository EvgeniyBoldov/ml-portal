import httpx
from ...core.config import get_settings

def new_async_http_client(base_url: str) -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=s.HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": "ml-portal/conn"},
    )
