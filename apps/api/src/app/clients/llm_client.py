"""
HTTP клиент для LLM (Generation Service) — совместим с тестами:
- .chat_stream(...) теперь yield'ит dict-чанки (а не строки)
- добавлен async .chat(...), чтобы тесты могли monkeypatch'ить llm_client.chat
"""
import asyncio
import json
import random
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.base_url = settings.LLM_URL
        self.timeout = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            headers={"Content-Type": "application/json"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def health(self) -> Dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            response = loop.run_until_complete(self.client.get("/healthz"))
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            raise

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        system_prompt: Optional[str] = None,
        rag_context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Нестриминговый чат. Возвращает dict с ключами {'content', 'usage'}"""
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "stream": False,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if rag_context:
            payload["rag_context"] = rag_context
        if max_tokens:
            payload["max_tokens"] = max_tokens

        resp = await self.client.post("/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Нормализуем поле текста
        if "content" in data:
            return data
        if "text" in data:
            return {"content": data.get("text", ""), "usage": data.get("usage", {})}
        # Бэкап
        return {"content": data.get("content", "") or data.get("delta", "") or "", "usage": data.get("usage", {})}

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-3.5-turbo",
        system_prompt: Optional[str] = None,
        rag_context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_retries: int = 2,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Стриминговый чат.
        Теперь yield'ит разобранные dict-чанки вида {'delta': '...', 'done': False} или {'done': True}.
        Поддерживает как простой формат {'content': '...'}, так и {'delta': '...'}.
        """
        payload = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "stream": True,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if rag_context:
            payload["rag_context"] = rag_context
        if max_tokens:
            payload["max_tokens"] = max_tokens

        for attempt in range(max_retries + 1):
            try:
                async with self.client.stream("POST", "/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                        else:
                            data = line
                        data = data.strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            yield {"done": True}
                            break
                        try:
                            chunk = json.loads(data)
                            # Нормализуем к единому виду
                            if isinstance(chunk, dict):
                                if "delta" in chunk:
                                    yield {"delta": chunk.get("delta", ""), "done": chunk.get("done", False), **({k:v for k,v in chunk.items() if k not in ('delta','done')})}
                                elif "content" in chunk:
                                    yield {"delta": chunk.get("content", ""), "done": chunk.get("done", False), **({k:v for k,v in chunk.items() if k not in ('content','done')})}
                                elif "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                    yield {"delta": delta, "done": chunk["choices"][0].get("finish_reason") is not None}
                                else:
                                    # Неизвестный формат — передаём как есть
                                    yield chunk
                            else:
                                # число/строка/список — приводим к строке
                                yield {"delta": str(chunk), "done": False}
                        except json.JSONDecodeError:
                            # Линия — это просто кусок текста
                            yield {"delta": data, "done": False}
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 503) and attempt < max_retries:
                    # экспоненциальный бэкофф + джиттер
                    retry_after = int(e.response.headers.get("Retry-After", "1"))
                    delay = min(retry_after, (2 ** attempt)) + random.uniform(0, 1)
                    logger.warning(f"LLM stream retry in {delay:.2f}s due to {e.response.status_code}")
                    await asyncio.sleep(delay)
                    continue
                raise
            except Exception as e:
                if attempt < max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"LLM stream error, retry in {delay:.2f}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                raise

# Глобальный экземпляр клиента
llm_client = LLMClient()
