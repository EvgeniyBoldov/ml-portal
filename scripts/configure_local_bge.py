"""Run inside api: register local BGE defaults; optionally reindex documents."""
from __future__ import annotations

import argparse
import asyncio
import json
import math

import httpx
from sqlalchemy import select

import app.models  # noqa: F401: initialize ORM relationships
from app.core.db import get_session_factory
from app.models.model_registry import ModelType
from app.models.collection import Collection
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.repositories.factory import AsyncRepositoryFactory
from app.services.model_service import ModelService
from app.services.rag_ingest_service import RAGIngestService
from app.services.rag_status_manager import RAGStatusManager


async def main(reindex: bool) -> None:
    deployments = [
        ("emb.bge.m3", ModelType.EMBEDDING, "http://emb-bge:8001", "bge-m3"),
        ("rerank.bge.v2.m3", ModelType.RERANKER, "http://rerank-bge:8002", "bge-reranker-v2-m3"),
    ]
    async with httpx.AsyncClient(timeout=180) as client:
        metadata = {}
        for alias, _, url, served in deployments:
            response = await client.get(f"{url}/models")
            response.raise_for_status()
            metadata[alias] = next(item for item in response.json() if item["alias"] == served)
        response = await client.post("http://emb-bge:8001/embed/batch", json={
            "model": "bge-m3", "texts": ["План отката изменения", "Прогноз погоды на завтра"],
        })
        response.raise_for_status()
        vectors = response.json()["vectors"]
        if len(vectors) != 2 or any(len(vector) != 1024 for vector in vectors):
            raise RuntimeError("Unexpected BGE embedding dimensions")
        if vectors[0] == vectors[1] or any(not math.isfinite(value) for vector in vectors for value in vector):
            raise RuntimeError("Encoder returned invalid or dummy embeddings")
        response = await client.post("http://rerank-bge:8002/rerank", json={
            "query": "Когда нужен план отката?", "documents": [
                "До изменения оборудования необходимо подготовить план отката.",
                "Прогноз погоды: завтра будет солнечно.",
            ], "top_k": 2,
        })
        response.raise_for_status()
        ranked = response.json()["results"]
        if len(ranked) != 2 or ranked[0]["index"] != 0:
            raise RuntimeError("Russian reranker smoke check failed")
        print(json.dumps({"embedding": metadata[deployments[0][0]],
                          "reranker": metadata[deployments[1][0]],
                          "rerank_scores": [row["score"] for row in ranked]}, ensure_ascii=False))

    async with get_session_factory()() as session:
        service = ModelService(session)
        for alias, kind, url, served in deployments:
            info = metadata[alias]
            payload = {"name": served, "type": kind, "provider": "local",
                       "provider_model_name": served, "base_url": url,
                       "default_for_type": True, "enabled": True, "status": "available",
                       "extra_config": {"vector_dim": info["dimensions"],
                                        "max_tokens": info["max_tokens"], "version": info["version"]}}
            existing = await service.get_by_alias(alias)
            if existing:
                await service.update_model(existing.id, payload)
            else:
                await service.create_model({"alias": alias, **payload})
        await session.commit()
        print("BGE embedding and reranker are system defaults")

    if reindex:
        async with get_session_factory()() as session:
            # A collection's primary model uses its unsuffixed physical target.
            # Move the pointer when dimensions change; retain the old index.
            async with httpx.AsyncClient(timeout=30) as client:
                collections = list((await session.execute(select(Collection).where(
                    Collection.collection_type == "document",
                    Collection.qdrant_collection_name.is_not(None),
                ))).scalars().all())
                for collection in collections:
                    base = collection.qdrant_collection_name
                    response = await client.get(f"http://qdrant:6333/collections/{base}")
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    vectors = response.json()["result"]["config"]["params"]["vectors"]
                    if vectors.get("size") != 1024:
                        collection.qdrant_collection_name = f"{base}__emb_bge_m3"
                        collection.vector_config = {**dict(collection.vector_config or {}),
                                                    "embed_model_aliases": ["emb.bge.m3"]}
                        print(f"Vector target: {base} -> {collection.qdrant_collection_name}; old index retained")
                await session.commit()
            documents = list((await session.execute(select(RAGDocument.id, Source.tenant_id).join(
                Source, Source.source_id == RAGDocument.id,
            ).where(RAGDocument.status != "archived"))).all())
        for document_id, tenant_id in documents:
            async with get_session_factory()() as session:
                factory = AsyncRepositoryFactory(session, tenant_id=tenant_id)
                manager = RAGStatusManager(session, factory)
                result = await RAGIngestService(session, factory, manager).reindex_document(
                    document_id, "emb.bge.m3",
                )
                await session.commit()
                print(json.dumps(result, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reindex", action="store_true")
    asyncio.run(main(parser.parse_args().reindex))
