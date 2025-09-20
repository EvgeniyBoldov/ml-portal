from __future__ import annotations
import asyncio, random
from typing import Any, Dict, Optional
import aiohttp

class HttpClient:
    def __init__(
        self,
        *,
        timeout_s: float = 20.0,
        retries: int = 3,
        backoff_base_s: float = 0.3,
        headers: Optional[Dict[str, str]] = None,
        max_connections: int = 200,
        max_keepalive: int = 50,
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.retries = retries
        self.backoff_base_s = backoff_base_s
        self.headers = headers or {}
        self.connector = aiohttp.TCPConnector(limit=max_connections, limit_per_host=max_keepalive, ssl=False)

    async def close(self):
        await self.connector.close()

    async def request(
        self,
        method: str,
        url: str,
        *,
        json_body: Any | None = None,
        params: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
        expected_status: int | None = None,
    ) -> Any:
        hdrs = self.headers.copy()
        if headers:
            hdrs.update(headers)

        attempt = 0
        while True:
            try:
                async with aiohttp.ClientSession(timeout=self.timeout, connector=self.connector) as sess:
                    async with sess.request(method, url, json=json_body, params=params, headers=hdrs) as resp:
                        if expected_status and resp.status != expected_status:
                            # let raise_for_status() handle non-matching statuses as errors
                            pass

                        if resp.status in (429, 503) and attempt < self.retries:
                            attempt += 1
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    delay = float(retry_after)
                                except ValueError:
                                    delay = self._backoff(attempt)
                            else:
                                delay = self._backoff(attempt)
                            await asyncio.sleep(delay)
                            continue

                        resp.raise_for_status()
                        ctype = resp.headers.get("Content-Type", "")
                        if "application/json" in ctype:
                            return await resp.json()
                        return await resp.text()
            except aiohttp.ClientResponseError as e:
                if e.status in (429, 503) and attempt < self.retries:
                    attempt += 1
                    delay = self._backoff(attempt)
                    await asyncio.sleep(delay)
                    continue
                raise
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                if attempt < self.retries:
                    attempt += 1
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise

    def _backoff(self, attempt: int) -> float:
        # exponential backoff with jitter
        base = self.backoff_base_s * (2 ** (attempt - 1))
        return base + random.uniform(0, base / 2)
