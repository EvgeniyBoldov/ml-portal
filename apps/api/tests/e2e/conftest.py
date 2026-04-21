"""
E2E test fixtures — tests talk to running API over HTTP.
Run tests: TEST_API_BASE_URL=http://localhost:8080 pytest tests/e2e/ -v
"""
import os
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

# When tests run inside docker-compose (`docker compose run api pytest ...`),
# localhost points to the test container itself; use service DNS by default.
TEST_API_BASE_URL = os.getenv("TEST_API_BASE_URL", "http://api:8000")
DEFAULT_ADMIN_LOGIN = os.getenv("DEFAULT_ADMIN_LOGIN", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

# Module-level cache for admin token (avoid rate limiting)
_cached_token: str | None = None


async def _get_admin_token() -> str:
    """Get cached admin token or login to get new one"""
    global _cached_token
    if _cached_token:
        return _cached_token
    
    async with AsyncClient(base_url=TEST_API_BASE_URL, timeout=30.0) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "login": DEFAULT_ADMIN_LOGIN,
                "password": DEFAULT_ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        _cached_token = data["access_token"]
        return _cached_token


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client for E2E tests"""
    async with AsyncClient(
        base_url=TEST_API_BASE_URL,
        follow_redirects=True,
        timeout=30.0,
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admin_token() -> str:
    """Get admin JWT token (cached)"""
    return await _get_admin_token()


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict:
    """Get admin auth headers"""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }
