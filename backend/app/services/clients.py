from __future__ import annotations
import os, time, httpx
from typing import List, Dict, Any, Optional
from app.core.qdrant import get_qdrant
from app.core.metrics import external_request_total, external_request_seconds
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

EMB_URL = os.getenv("EMBEDDINGS_URL", "http://emb:8001")
LLM_URL = os.getenv("LLM_URL", "http://llm:8002")
COLLECTION = os.getenv("QDRANT_COLLECTION", "rag_chunks")

def _timed(name: str):
    class _Ctx:
        def __enter__(self):
            self.t0 = time.perf_counter()
            return self
        def __exit__(self, exc_type, exc, tb):
            dt = time.perf_counter() - self.t0
            external_request_total.labels(target=name, status=("ok" if exc is None else "fail")).inc()
            external_request_seconds.labels(target=name).observe(dt)
    return _Ctx()

def embed_texts(texts: List[str]) -> List[List[float]]:
    with _timed("emb"):
        with httpx.Client(timeout=60) as client:
            r = client.post(f"{EMB_URL}/embed", json={"inputs": texts})
            r.raise_for_status()
            return r.json().get("vectors", [])

def llm_chat(messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    """Обычный чат с LLM (не стриминг)"""
    payload = {"messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    with _timed("llm"):
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{LLM_URL}/v1/chat/completions", json=payload)
            r.raise_for_status()
            # Обрабатываем стриминг ответ
            content = ""
            for line in r.text.split('\n'):
                if line.startswith('data: '):
                    data = line[6:]  # Убираем "data: "
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = r.json() if not line.startswith('data: ') else __import__('json').loads(data)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            chunk_content = delta.get("content", "")
                            if chunk_content:
                                content += chunk_content
                    except:
                        continue
            return content

async def llm_chat_stream(messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: Optional[int] = None):
    """Настоящий стриминг чат с LLM"""
    payload = {"messages": messages, "temperature": temperature, "stream": True}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    
    with _timed("llm"):
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{LLM_URL}/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]  # Убираем "data: "
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = __import__('json').loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except:
                            continue

def qdrant_search(vector: List[float], top_k: int, offset: Optional[int] = None,
                  doc_id: Optional[str] = None, tags: Optional[List[str]] = None,
                  sort_by: str = "score_desc"):
    client = get_qdrant()
    must = []
    if doc_id:
        must.append(FieldCondition(key="document_id", match=MatchValue(value=doc_id)))
    if tags:
        must.append(FieldCondition(key="tags", match=MatchValue(value=tags)))
    f = Filter(must=must) if must else None
    with _timed("qdrant.search"):
        hits = client.search(collection_name=COLLECTION, query_vector=vector, limit=top_k, offset=offset or 0, with_payload=True, query_filter=f)
    out = []
    for h in hits:
        out.append({"score": float(h.score), "id": str(h.id), "payload": h.payload or {}})
    return out

def qdrant_count_by_doc(doc_id: str) -> int:
    client = get_qdrant()
    f = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
    with _timed("qdrant.count"):
        try:
            res = client.count(collection_name=COLLECTION, count_filter=f, exact=True)
            return int(getattr(res, "count", None) or (res.get("count") if isinstance(res, dict) else 0) or 0)
        except Exception:
            total = 0
            next_page = None
            while True:
                points, next_page = client.scroll(
                    collection_name=COLLECTION,
                    scroll_filter=f,
                    limit=1024,
                    with_payload=False,
                    with_vectors=False,
                    offset=next_page,
                )
                total += len(points or [])
                if not next_page:
                    break
            return total
