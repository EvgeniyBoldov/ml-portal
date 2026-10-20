"""Private, explicitly prepared document indexes over authorized chat artifacts."""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.impl.qdrant import QdrantVectorStore, _is_not_found_error, _dict_to_filter
from app.core.config import get_settings
from app.services.artifact_representation_service import ArtifactRepresentationService
from app.services.bounded_embeddings import embed_texts_bounded
from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
from app.services.collection.vector_lifecycle import CollectionVectorLifecycleService
from app.services.hipporag_service import HippoRAGService
from app.services.vector_index_service import VectorIndexService


_PRIVATE_VECTOR_COLLECTION = re.compile(r"fd_[0-9]+_vi_[a-f0-9]{16}_[a-f0-9]{16,64}\Z")


class FileDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def not_indexed() -> FileDataError:
    return FileDataError("document_not_indexed", "Документ не векторизован для выбранного поиска. Выполните file.data.prepare.")


def split_file_text(text: str) -> list[dict[str, Any]]:
    """Exact character spans, including whitespace; embedding limits apply later."""
    settings = get_settings()
    size, overlap = settings.FILE_DATA_CHUNK_CHARS, settings.FILE_DATA_CHUNK_OVERLAP
    if overlap >= size:
        raise FileDataError("file_data_configuration_error", "File chunk overlap must be smaller than its size")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append({"text": text[start:end], "start": start, "end": end})
        if end == len(text):
            break
        start = end - overlap
    return chunks


class FileDataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.artifacts = ChatArtifactReferenceService(session)
        self.representations = ArtifactRepresentationService(session)

    async def read(self, *, offset: int, limit: int, representation_id: str | None = None,
                   **scope: Any) -> dict[str, Any]:
        if limit > get_settings().CHAT_FILE_READ_MAX_CHARS:
            raise FileDataError("file_data_read_limit", "Requested page exceeds the configured file read limit")
        document = await self.representations.canonical(**scope)
        if representation_id and representation_id != document["representation_id"]:
            raise FileDataError("file_representation_changed", "File representation changed; restart reading the new version")
        text = document["content"]
        if offset > len(text):
            raise FileDataError("file_data_invalid_offset", "Read offset is beyond the end of the document")
        end = min(offset + limit, len(text))
        return {**{key: document[key] for key in ("artifact_id", "representation_id", "source_fingerprint",
                    "source_complete", "status", "warnings")}, "content": text[offset:end],
                "offset": offset, "next_offset": end if end < len(text) else None,
                "total_chars": len(text), "read_complete": end == len(text)}

    @staticmethod
    def _namespace(scope: dict[str, Any]) -> str:
        return hashlib.sha256(f"{scope['chat_id']}:{scope['artifact_id']}".encode()).hexdigest()

    @staticmethod
    def _document(scope: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
        return {"id": scope["artifact_id"], "content": document["content"], "metadata": {
            "artifact_id": scope["artifact_id"], "representation_id": document["representation_id"],
            "source_fingerprint": document["source_fingerprint"], "file_namespace": FileDataService._namespace(scope)}}

    async def prepare(self, *, backend: str, **scope: Any) -> dict[str, Any]:
        document = await self.representations.canonical(**scope)
        if not document["content"].strip():
            raise FileDataError("document_has_no_text", "Документ не содержит извлечённого текста; индекс не создан")
        if not document["source_complete"]:
            raise FileDataError("document_extraction_incomplete", "Документ извлечён не полностью; индекс не создан")
        reference = await self.artifacts.get_reference(**{key: scope[key] for key in ("artifact_id", "chat_id", "owner_id")})
        indexes = dict((reference.metadata_snapshot or {}).get("file_data") or {})
        existing = indexes.get(backend) or {}
        if self._current(existing, document):
            try:
                await self._check_index(existing, scope, document)
                return self._prepared(scope, document, backend, existing, reused=True)
            except FileDataError as exc:
                if exc.code != "document_not_indexed":
                    raise
        expiry = int(time.time()) + get_settings().FILE_DATA_INDEX_TTL_SECONDS
        entry = {"status": "ready", "expires_at": expiry,
                 "source_fingerprint": document["source_fingerprint"], "representation_id": document["representation_id"]}
        if backend == "vector":
            entry.update(await self._prepare_vector(scope, document, expiry))
        else:
            hippo = HippoRAGService(self.session)
            models = await hippo._models()
            result = await hippo._call("files/prepare", {"namespace": self._namespace(scope),
                "expires_at": expiry, "documents": [self._document(scope, document)]}, models=models)
            if not result.get("chunk_count") or not result.get("index"):
                raise not_indexed()
            entry.update(index=result["index"], chunk_count=result["chunk_count"], model_identity=models["identity"])
        if expiry <= time.time():
            raise FileDataError("document_not_indexed", "Срок действия индекса истёк во время подготовки; индекс не опубликован")
        indexes[backend] = entry
        reference.metadata_snapshot = {**(reference.metadata_snapshot or {}), "file_data": indexes}
        await self.session.flush()
        return self._prepared(scope, document, backend, entry, reused=False)

    @staticmethod
    def _prepared(scope: dict, document: dict, backend: str, entry: dict, *, reused: bool) -> dict[str, Any]:
        return {"artifact_id": scope["artifact_id"], "representation_id": document["representation_id"],
                "source_fingerprint": document["source_fingerprint"], "backend": backend, "status": "ready",
                "chunk_count": entry["chunk_count"], "expires_at": entry["expires_at"], "reused": reused}

    @staticmethod
    def _current(entry: dict, document: dict) -> bool:
        return (entry.get("status") == "ready" and entry.get("expires_at", 0) > time.time()
                and entry.get("source_fingerprint") == document.get("source_fingerprint")
                and entry.get("representation_id") == document.get("representation_id")
                and entry.get("chunk_count", 0) > 0)

    async def _prepare_vector(self, scope: dict, document: dict, expiry: int) -> dict[str, Any]:
        aliases = await CollectionVectorLifecycleService(self.session).resolve_target_vector_models(
            uuid.UUID(scope["tenant_id"]) if scope.get("tenant_id") else None)
        if not aliases:
            raise FileDataError("embedding_unavailable", "Модель векторизации недоступна")
        settings = get_settings()
        base = f"file:{self._namespace(scope)}:{document['source_fingerprint']}:{settings.FILE_DATA_CHUNK_CHARS}:{settings.FILE_DATA_CHUNK_OVERLAP}"
        target = await VectorIndexService(self.session).resolve(base, aliases[0])
        collection = f"fd_{expiry}_{target.collection_name}"
        chunks = split_file_text(document["content"])
        store = QdrantVectorStore()
        client = await store.get_client()
        try:
            await store.ensure_collection(collection, target.dimensions)
            for start in range(0, len(chunks), settings.EMB_REQUEST_BATCH_SIZE):
                batch = chunks[start:start + settings.EMB_REQUEST_BATCH_SIZE]
                vectors = await asyncio.to_thread(embed_texts_bounded, target.embedding_service, [chunk["text"] for chunk in batch])
                payloads = [{**chunk, "artifact_id": scope["artifact_id"], "namespace": self._namespace(scope),
                             "representation_id": document["representation_id"], "source_fingerprint": document["source_fingerprint"]}
                            for chunk in batch]
                ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base}:{chunk['start']}:{chunk['end']}")) for chunk in batch]
                await store.upsert(collection, vectors, payloads, ids)
            count = await store.count_by_filter(collection, {"namespace": self._namespace(scope), "artifact_id": scope["artifact_id"]})
            if count != len(chunks):
                raise FileDataError("document_index_incomplete", "Векторизация документа не завершена")
            return {"collection": collection, "base": base, "model_alias": target.model_alias,
                    "embedding_fingerprint": target.fingerprint, "chunk_count": count}
        finally:
            await client.close()

    async def _check_index(self, entry: dict, scope: dict, document: dict) -> None:
        if entry.get("collection"):
            await self._vector(scope, document, entry, query=None, limit=1)
        else:
            await self._longmemory(scope, document, entry, query=None, limit=1)

    async def _vector(self, scope: dict, document: dict, entry: dict, *, query: str | None, limit: int) -> list[dict]:
        store = QdrantVectorStore()
        client = await store.get_client()
        filter = {"namespace": self._namespace(scope), "artifact_id": scope["artifact_id"],
                  "representation_id": document["representation_id"], "source_fingerprint": document["source_fingerprint"]}
        try:
            if not await store.collection_exists(entry["collection"]):
                raise not_indexed()
            count = await store.count_by_filter(entry["collection"], filter)
            if count <= 0 or count != entry["chunk_count"]:
                raise not_indexed()
            target = await VectorIndexService(self.session).resolve(entry["base"], entry["model_alias"])
            if target.fingerprint != entry["embedding_fingerprint"]:
                raise not_indexed()
            if query is None:
                return []
            vector = (await asyncio.to_thread(embed_texts_bounded, target.embedding_service, [query]))[0]
            # Use the strict native query: the shared adapter maps a missing
            # collection to [], which would be a false negative for this tool.
            response = await client.query_points(collection_name=entry["collection"], query=vector,
                query_filter=_dict_to_filter(filter), limit=limit, with_payload=True)
            if await store.count_by_filter(entry["collection"], filter) != entry["chunk_count"]:
                raise not_indexed()
            return [{"chunk_id": str(point.id), "text": point.payload["text"], "score": float(point.score),
                     "start": point.payload["start"], "end": point.payload["end"]} for point in response.points]
        except Exception as exc:
            if _is_not_found_error(exc):
                raise not_indexed() from exc
            raise
        finally:
            await client.close()

    async def _longmemory(self, scope: dict, document: dict, entry: dict, *, query: str | None, limit: int) -> list[dict]:
        hippo = HippoRAGService(self.session)
        models = await hippo._models()
        if models["identity"] != entry.get("model_identity"):
            raise not_indexed()
        result = await hippo._call("files/search", {"namespace": self._namespace(scope),
            "expected_index": entry["index"], "expected_chunks": entry["chunk_count"],
            "documents": [self._document(scope, document)], "query": query,
            "top_k": limit}, models=models)
        if result.get("status") != "ready" or result.get("chunk_count") != entry["chunk_count"]:
            raise not_indexed()
        hits = []
        for hit in result.get("hits") or []:
            refs = (hit.get("metadata") or {}).get("source_refs") or []
            for ref in refs:
                if ref.get("document_id") == scope["artifact_id"]:
                    hits.append({"chunk_id": f"{scope['artifact_id']}:{ref['start']}:{ref['end']}",
                        "text": hit["text"], "score": hit["score"], "start": ref["start"], "end": ref["end"]})
        return hits[:limit]

    async def search(self, *, backend: str, query: str, limit: int, **scope: Any) -> dict[str, Any]:
        # Does not extract or index: absence is explicit and recoverable via prepare.
        document = await self.representations.canonical(**scope, extract=False)
        if document is None or not document["source_complete"]:
            raise not_indexed()
        reference = await self.artifacts.get_reference(**{key: scope[key] for key in ("artifact_id", "chat_id", "owner_id")})
        indexes = (reference.metadata_snapshot or {}).get("file_data") or {}
        candidates = ["vector", "longmemory"] if backend == "auto" else [backend]
        for candidate in candidates:
            entry = indexes.get(candidate) or {}
            if not self._current(entry, document):
                continue
            try:
                if candidate == "vector":
                    hits = await self._vector(scope, document, entry, query=query, limit=limit)
                else:
                    hits = await self._longmemory(scope, document, entry, query=query, limit=limit)
            except FileDataError as exc:
                if backend == "auto" and exc.code == "document_not_indexed":
                    continue
                raise
            budget = get_settings().CHAT_FILE_READ_MAX_CHARS
            bounded = []
            response_truncated = False
            for hit in hits:
                if len(hit["text"]) > budget:
                    response_truncated = True
                    if not bounded and budget > 0:
                        bounded.append({**hit, "artifact_id": scope["artifact_id"],
                            "representation_id": document["representation_id"],
                            "text": hit["text"][:budget], "end": hit["start"] + budget,
                            "truncated": True, "metadata": {"chunk_end": hit["end"]}})
                    break
                bounded.append({**hit, "artifact_id": scope["artifact_id"],
                                "representation_id": document["representation_id"]})
                budget -= len(hit["text"])
            return {"artifact_id": scope["artifact_id"], "representation_id": document["representation_id"],
                    "source_fingerprint": document["source_fingerprint"], "source_complete": True,
                    "backend": candidate, "status": "ready", "indexed_chunks": entry["chunk_count"],
                    "hits": bounded, "returned_count": len(bounded), "response_truncated": response_truncated or len(bounded) != len(hits)}
        raise not_indexed()

    async def delete_indexes(self, *, reference: Any) -> None:
        """Delete only derived private indexes; never delete a source collection."""
        indexes = (reference.metadata_snapshot or {}).get("file_data") or {}
        vector = indexes.get("vector") or {}
        if vector.get("collection"):
            name = vector["collection"]
            if not _PRIVATE_VECTOR_COLLECTION.fullmatch(name):
                raise FileDataError("file_data_invalid_index", "Invalid private index identity")
            store = QdrantVectorStore()
            client = await store.get_client()
            try:
                if await store.collection_exists(name):
                    await store.delete_collection(name)
            finally:
                await client.close()
        graph = indexes.get("longmemory") or {}
        if graph.get("index"):
            await self._worker_cleanup("delete", {"namespace": self._namespace({
                "chat_id": str(reference.chat_id), "artifact_id": str(reference.id)}), "index": graph["index"]})

    @staticmethod
    async def _worker_cleanup(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx
        settings = get_settings()
        async with httpx.AsyncClient(timeout=settings.TIMEOUT_SECONDS) as client:
            response = await client.post(f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/files/{operation}", json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def cleanup_expired_indexes() -> int:
        store = QdrantVectorStore()
        client = await store.get_client()
        deleted = 0
        try:
            for name in await store.collection_names("fd_"):
                match = re.fullmatch(r"fd_([0-9]+)_vi_[a-f0-9]{16}_[a-f0-9]{16,64}", name)
                if match and int(match[1]) <= time.time():
                    try:
                        await store.delete_collection(name)
                        deleted += 1
                    except Exception as exc:
                        if not _is_not_found_error(exc):
                            raise
        finally:
            await client.close()
        result = await FileDataService._worker_cleanup("cleanup", {})
        return deleted + result["deleted"]
