"""Document-local search must distinguish absent indexes from empty retrieval."""
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.builtins.file_data import FileDataReadTool, FileDataPrepareTool, FileDataSearchTool
from app.services.file_data_service import FileDataService, FileDataError, split_file_text, _PRIVATE_VECTOR_COLLECTION


@pytest.fixture
def data_service():
    scope = {"artifact_id": str(uuid4()), "chat_id": str(uuid4()), "owner_id": str(uuid4()), "tenant_id": str(uuid4())}
    document = {"artifact_id": scope["artifact_id"], "representation_id": str(uuid4()),
                "content": "Find the treasure.\n" * 10, "source_fingerprint": "f" * 64,
                "source_complete": True, "status": "ready", "warnings": []}
    entry = {"status": "ready", "expires_at": int(time.time()) + 600,
             "representation_id": document["representation_id"], "source_fingerprint": "f" * 64,
             "chunk_count": 1, "collection": "private", "base": "base", "model_alias": "emb",
             "embedding_fingerprint": "encoder"}
    reference = SimpleNamespace(metadata_snapshot={"file_data": {"vector": entry}})
    service = FileDataService(AsyncMock())
    service.representations.canonical = AsyncMock(return_value=document)
    service.artifacts.get_reference = AsyncMock(return_value=reference)
    return service, scope, document, entry, reference


@pytest.mark.parametrize("fingerprint", ["a" * 24, "b" * 64])
def test_private_vector_collection_accepts_actual_physical_index_fingerprints(fingerprint):
    name = f"fd_{int(time.time())}_vi_{'c' * 16}_{fingerprint}"
    assert _PRIVATE_VECTOR_COLLECTION.fullmatch(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["representation", "backend", "expired", "stale", "zero_chunks", "incomplete"])
async def test_search_missing_index_never_returns_empty_success(data_service, missing):
    service, scope, document, entry, reference = data_service
    if missing == "representation":
        service.representations.canonical.return_value = None
    elif missing == "backend":
        reference.metadata_snapshot = {}
    elif missing == "expired":
        entry["expires_at"] = 1
    elif missing == "stale":
        entry["source_fingerprint"] = "old"
    elif missing == "zero_chunks":
        entry["chunk_count"] = 0
    else:
        document["source_complete"] = False
    service._vector = AsyncMock()
    with pytest.raises(FileDataError) as error:
        await service.search(**scope, query="treasure", backend="auto", limit=5)
    assert error.value.code == "document_not_indexed"
    assert "не векторизован" in str(error.value)
    service._vector.assert_not_awaited()
    service.representations.canonical.assert_awaited_once_with(**scope, extract=False)


@pytest.mark.asyncio
async def test_prepared_search_can_return_empty_hits_and_auto_uses_existing_backend(data_service):
    service, scope, document, _, _ = data_service
    service._vector = AsyncMock(return_value=[])
    output = await service.search(**scope, query="treasure", backend="auto", limit=5)
    assert output["status"] == "ready" and output["indexed_chunks"] == 1
    assert output["hits"] == [] and output["returned_count"] == 0
    assert output["source_fingerprint"] == document["source_fingerprint"]


@pytest.mark.asyncio
async def test_read_pages_and_version_fence(data_service):
    service, scope, document, _, _ = data_service
    first = await service.read(**scope, offset=0, limit=10)
    second = await service.read(**scope, offset=first["next_offset"], limit=1000,
                                representation_id=first["representation_id"])
    assert first["content"] + second["content"] == document["content"]
    assert not first["read_complete"] and second["read_complete"]
    with pytest.raises(FileDataError, match="changed"):
        await service.read(**scope, offset=10, limit=10, representation_id=str(uuid4()))


@pytest.mark.asyncio
async def test_prepare_rejects_partial_extraction_and_reuses_verified_index(data_service):
    service, scope, document, _, _ = data_service
    service._prepare_vector = AsyncMock()
    document["source_complete"] = False
    with pytest.raises(FileDataError) as error:
        await service.prepare(**scope, backend="vector")
    assert error.value.code == "document_extraction_incomplete"
    service._prepare_vector.assert_not_awaited()
    document["source_complete"] = True
    service._check_index = AsyncMock()
    output = await service.prepare(**scope, backend="vector")
    assert output["reused"] is True
    service._prepare_vector.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2, "missing", "disappeared"])
async def test_vector_query_checks_exact_document_chunks_and_missing_collection(data_service, monkeypatch, count):
    service, scope, document, entry, _ = data_service
    client = SimpleNamespace(close=AsyncMock(), query_points=AsyncMock())
    store = SimpleNamespace(get_client=AsyncMock(return_value=client),
        collection_exists=AsyncMock(return_value=count != "missing"),
        count_by_filter=AsyncMock(return_value=1 if count == "disappeared" else count))
    if count == "disappeared":
        client.query_points.side_effect = RuntimeError("404 collection not found")
    monkeypatch.setattr("app.services.file_data_service.QdrantVectorStore", lambda: store)
    monkeypatch.setattr("app.services.file_data_service.VectorIndexService", lambda _: SimpleNamespace(
        resolve=AsyncMock(return_value=SimpleNamespace(fingerprint="encoder", embedding_service=Mock()))))
    monkeypatch.setattr("app.services.file_data_service.embed_texts_bounded", lambda *args: [[1.0, 0.0]])
    with pytest.raises(FileDataError) as error:
        await service._vector(scope, document, entry, query="treasure", limit=5)
    assert error.value.code == "document_not_indexed"
    if count != "disappeared":
        client.query_points.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_longmemory_missing_scope_or_chunks_is_not_an_empty_result(data_service, monkeypatch):
    service, scope, document, _, _ = data_service
    hippo = SimpleNamespace(_models=AsyncMock(return_value={"identity": "model"}),
                            _call=AsyncMock(return_value={"status": "not_indexed", "chunk_count": 0}))
    monkeypatch.setattr("app.services.file_data_service.HippoRAGService", lambda _: hippo)
    with pytest.raises(FileDataError) as error:
        await service._longmemory(scope, document, {"model_identity": "model", "index": "index", "chunk_count": 1},
                                  query="treasure", limit=5)
    assert error.value.code == "document_not_indexed"
    assert hippo._call.await_args.args[0] == "files/search"


def test_chunk_spans_preserve_exact_text_and_overlap():
    text = "Русский текст, tabs\t and  repeated spaces.\n" * 200
    chunks = split_file_text(text)
    assert len(chunks) > 1
    assert all(chunk["text"] == text[chunk["start"]:chunk["end"]] for chunk in chunks)
    assert chunks[0]["start"] == 0 and chunks[-1]["end"] == len(text)
    assert all(second["start"] <= first["end"] for first, second in zip(chunks, chunks[1:]))


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [FileDataReadTool, FileDataPrepareTool, FileDataSearchTool])
async def test_tools_validate_arguments_before_access(tool):
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4())
    result = await tool().execute(ctx, {"artifact_id": "invalid"})
    assert not result.success and result.metadata["error_code"] == "invalid_arguments"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,code", [("missing", "document_not_indexed"), ("outage", "file_data_backend_unavailable")])
async def test_search_tool_returns_explicit_safe_errors(monkeypatch, failure, code):
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr("app.core.db.get_session_factory", lambda: lambda: session)
    error = FileDataError("document_not_indexed", "Документ не векторизован") if failure == "missing" else RuntimeError("SECRET_BACKEND_DETAIL")
    monkeypatch.setattr(FileDataService, "search", AsyncMock(side_effect=error))
    result = await FileDataSearchTool().execute(ToolContext(user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4()),
        {"artifact_id": str(uuid4()), "query": "treasure"})
    assert not result.success and result.data is None and result.metadata["error_code"] == code
    assert "SECRET_BACKEND_DETAIL" not in result.error
    session.commit.assert_not_awaited()


def test_root_role_contract_accepts_default_paged_read_and_search():
    from app.runtime.memory.role_tools import MemoryToolCall
    read = MemoryToolCall.model_validate({"tool": "file.data.read", "arguments": {"artifact_id": str(uuid4())}})
    search = MemoryToolCall.model_validate({"tool": "file.data.search", "arguments": {"artifact_id": str(uuid4()), "query": "treasure"}})
    assert read.arguments.limit == 10000
    assert search.arguments.backend == "auto"


@pytest.mark.parametrize("operation", ["file.data.read", "file.data.prepare", "file.data.search", "instance.system.file.data.search"])
def test_file_data_calls_cannot_reuse_stale_ledger_results(operation):
    from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
    ledger = Mock()
    result = ToolCallReusePolicy().maybe_reuse(operation_slug=operation, arguments={"artifact_id": str(uuid4())},
        ctx=ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"runtime_tool_ledger": ledger}))
    assert result is None
    ledger.find_successful_result.assert_not_called()


@pytest.mark.asyncio
async def test_file_search_branch_visibility_is_checked_before_storage():
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4(), extra={"runtime_branch_id": "frozen"})
    result = await FileDataSearchTool().execute(ctx, {"artifact_id": str(uuid4()), "query": "treasure"})
    assert not result.success and result.metadata["error_code"] == "artifact_unavailable"


@pytest.mark.asyncio
async def test_root_reader_keeps_not_indexed_code_in_model_receipt():
    from app.runtime.memory.role_tools import MemoryToolCall, RoleMemoryTools
    from app.agents.context import ToolResult
    tools = RoleMemoryTools(session=object(), ctx=ToolContext(user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4()))
    tools.descriptors = AsyncMock(return_value=[{"tool": "file.data.search"}])
    tools._execution_ctx = SimpleNamespace(extra={})
    tools._executor.execute = AsyncMock(return_value=ToolResult.fail(
        "Документ не векторизован", error_code="document_not_indexed"))
    receipt = await tools.execute(MemoryToolCall(tool="file.data.search", arguments={
        "artifact_id": str(uuid4()), "query": "treasure"}), actor="planner", parent_type="planner_iteration",
        parent_id="plan", event_sink=None)
    assert receipt["result"]["error_code"] == "document_not_indexed"
    assert receipt["result"]["error"] == "Документ не векторизован"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args,data", [
    (FileDataReadTool, {}, {"content": "Source", "offset": 0, "next_offset": None, "total_chars": 6,
                          "read_complete": True, "status": "ready", "warnings": [], "source_complete": True}),
    (FileDataPrepareTool, {}, {"backend": "vector", "status": "ready", "chunk_count": 1,
                             "expires_at": 9999999999, "reused": False}),
    (FileDataSearchTool, {"query": "treasure"}, {"backend": "vector", "status": "ready", "indexed_chunks": 1,
                    "source_complete": True, "hits": [], "returned_count": 0}),
])
async def test_file_tools_happy_path_matches_pydantic_contract_and_direct_delivery(monkeypatch, tool, args, data):
    from app.agents.handlers.versioned_tool import tool_registry
    artifact_id = str(uuid4())
    document = {"artifact_id": artifact_id, "representation_id": str(uuid4()), "source_fingerprint": "f" * 64, **data}
    operation = {FileDataReadTool: "read", FileDataPrepareTool: "prepare", FileDataSearchTool: "search"}[tool]
    monkeypatch.setattr(FileDataService, operation, AsyncMock(return_value=document))
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr("app.core.db.get_session_factory", lambda: lambda: session)
    result = await tool().execute(ToolContext(user_id=uuid4(), tenant_id=uuid4(), chat_id=uuid4()),
                                  {"artifact_id": artifact_id, **args})
    assert result.success and result.delivery == "direct"
    session.commit.assert_awaited_once()
    assert tool_registry.get(tool.tool_slug) is not None
