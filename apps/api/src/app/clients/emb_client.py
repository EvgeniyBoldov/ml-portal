"""
HTTP клиент для EMB (Embedding Service) — базовые правки:
- .health() и .get_models() переписаны на sync httpx.Client, чтобы не вызывать run_until_complete внутри активного event loop.
- Остальной API (embed) остаётся асинхронным.
"""
import asyncio
import json
import time
import random
from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EMBClient:
    def __init__(self):
        self.base_url = settings.EMB_URL
        self.timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            headers={"Content-Type": "application/json"}
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def health(self) -> Dict[str, Any]:
        """Проверка здоровья сервиса (sync)"""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as c:
                r = c.get("/healthz")
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"EMB health check failed: {e}")
            raise

    def get_models(self) -> List[Dict[str, Any]]:
        """Получение списка доступных моделей (sync)"""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as c:
                r = c.get("/models")
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"Failed to get EMB models: {e}")
            raise

    async def embed(
        self,
        texts: List[str],
        model: str = "minilm",
        normalize: bool = True,
        batch_size: int = 64,
        batch_latency_ms: int = 20,
        max_retries: int = 3
    ) -> List[List[float]]:
        payload = {
            "texts": texts,
            "model": model,
            "normalize": normalize,
            "batch_size": batch_size,
            "batch_latency_ms": batch_latency_ms
        }
        for attempt in range(max_retries + 1):
            try:
                response = await self.client.post("/embed", json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("embeddings", [])
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", "60"))
                    if attempt < max_retries:
                        delay = min(retry_after, (2 ** attempt) + random.uniform(0, 1))
                        logger.warning(f"EMB rate limited, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"EMB rate limited after {max_retries} retries")
                        raise Exception(f"Rate limited, retry after {retry_after} seconds")
                elif e.response.status_code == 503:
                    if attempt < max_retries:
                        delay = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"EMB service unavailable, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error("EMB service unavailable after retries")
                        raise Exception("Service unavailable")
                else:
                    logger.error(f"EMB embed failed with status {e.response.status_code}: {e.response.text}")
                    raise
            except Exception as e:
                if attempt < max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"EMB request failed, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"EMB embed request failed after {max_retries} retries: {e}")
                    raise

emb_client = EMBClient()
