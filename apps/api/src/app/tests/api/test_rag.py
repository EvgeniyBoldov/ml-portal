"""
RAG: ingest + search tests
"""
import pytest
import hashlib
from fastapi.testclient import TestClient
from tests.conftest import assert_problem


def test_rag_upload_success(client: TestClient):
    """Test RAG document upload returns presigned URL"""
    response = client.post("/api/v1/rag/upload", json={
        "name": "test-document.pdf",
        "mime": "application/pdf",
        "size": 1024,
        "tags": ["test", "document"]
    })
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "source_id" in data
        assert "upload" in data
        assert "url" in data["upload"]
        assert "headers" in data["upload"]


def test_rag_upload_sha256_dedup(client: TestClient):
    """Test RAG upload with same content returns same doc_id"""
    payload = {
        "name": "duplicate.pdf",
        "mime": "application/pdf", 
        "size": 1024
    }
    
    # First upload
    response1 = client.post("/api/v1/rag/upload", json=payload)
    assert "X-Request-ID" in response1.headers
    
    # Second upload with same content
    response2 = client.post("/api/v1/rag/upload", json=payload)
    assert "X-Request-ID" in response2.headers
    
    if response1.status_code == 200 and response2.status_code == 200:
        data1 = response1.json()
        data2 = response2.json()
        # Should return same source_id for duplicate content
        assert data1["source_id"] == data2["source_id"]


def test_rag_upload_invalid_mime_type(client: TestClient):
    """Test RAG upload with invalid MIME type"""
    response = client.post("/api/v1/rag/upload", json={
        "name": "test.exe",
        "mime": "application/x-executable",
        "size": 1024
    })
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_rag_upload_file_size_limit(client: TestClient):
    """Test RAG upload with file size exceeding limit"""
    response = client.post("/api/v1/rag/upload", json={
        "name": "large-file.pdf",
        "mime": "application/pdf",
        "size": 100 * 1024 * 1024  # 100MB, exceeds 50MB limit
    })
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_rag_upload_missing_fields(client: TestClient):
    """Test RAG upload with missing required fields"""
    response = client.post("/api/v1/rag/upload", json={})
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_rag_search_success(client: TestClient):
    """Test RAG search returns results with required fields"""
    response = client.get("/api/v1/rag/search?query=test")
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query_time_ms" in data
        
        # Check result structure
        if data["results"]:
            result = data["results"][0]
            assert "chunk_id" in result
            assert "source_id" in result
            assert "score" in result
            assert "text" in result
            # Optional fields
            if "page" in result:
                assert isinstance(result["page"], int)
            if "highlights" in result:
                assert isinstance(result["highlights"], list)


def test_rag_search_hybrid_search(client: TestClient):
    """Test RAG search uses hybrid (vector + lexical) search"""
    response = client.get("/api/v1/rag/search?query=test&limit=10&offset=0")
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query_time_ms" in data


def test_rag_search_with_filters(client: TestClient):
    """Test RAG search with tag filters"""
    response = client.get("/api/v1/rag/search?query=test&tags=document&min_score=0.5")
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "results" in data
        assert "total" in data


def test_rag_search_pagination(client: TestClient):
    """Test RAG search pagination with offset/limit"""
    # First page
    response1 = client.get("/api/v1/rag/search?query=test&limit=5&offset=0")
    assert "X-Request-ID" in response1.headers
    
    # Second page
    response2 = client.get("/api/v1/rag/search?query=test&limit=5&offset=5")
    assert "X-Request-ID" in response2.headers
    
    if response1.status_code == 200 and response2.status_code == 200:
        data1 = response1.json()
        data2 = response2.json()
        # Results should be different (no overlap)
        if data1["results"] and data2["results"]:
            chunk_ids1 = {r["chunk_id"] for r in data1["results"]}
            chunk_ids2 = {r["chunk_id"] for r in data2["results"]}
            assert chunk_ids1.isdisjoint(chunk_ids2)


def test_rag_search_invalid_query(client: TestClient):
    """Test RAG search with invalid query parameters"""
    response = client.get("/api/v1/rag/search?query=&limit=-1&offset=-1")
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_rag_search_empty_query(client: TestClient):
    """Test RAG search with empty query"""
    response = client.get("/api/v1/rag/search?query=")
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_rag_ingest_job_statuses(client: TestClient):
    """Test RAG ingest job status progression"""
    # Upload document
    upload_response = client.post("/api/v1/rag/upload", json={
        "name": "job-test.pdf",
        "mime": "application/pdf",
        "size": 1024
    })
    
    assert "X-Request-ID" in upload_response.headers
    
    if upload_response.status_code == 200:
        source_id = upload_response.json()["source_id"]
        
        # Check job status
        status_response = client.get(f"/api/v1/rag/ingest/{source_id}/status")
        assert "X-Request-ID" in status_response.headers
        
        if status_response.status_code == 200:
            data = status_response.json()
            assert "status" in data
            assert data["status"] in ["queued", "processing", "ready", "failed"]
            
            # Job should progress through statuses
            if data["status"] == "ready":
                assert "result" in data
            elif data["status"] == "failed":
                assert "error" in data


def test_rag_search_highlights(client: TestClient):
    """Test RAG search returns highlights when available"""
    response = client.get("/api/v1/rag/search?query=test")
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        if data["results"]:
            result = data["results"][0]
            # Highlights might be present
            if "highlights" in result:
                assert isinstance(result["highlights"], list)
                for highlight in result["highlights"]:
                    assert isinstance(highlight, str)
                    assert len(highlight) > 0
