# FILE: API_CONTRACT_CURRENT.md
# API Documentation

## Overview

The ML Portal API is a RESTful API built with FastAPI that provides endpoints for chat management, document processing, and AI-powered features.

**Base URL**: `http://localhost:8000/api`

**Authentication**: Bearer Token (JWT)

## Authentication

### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### Register
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password",
  "role": "user"
}
```

## Chats API

### Create Chat
```http
POST /api/chats
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My Chat",
  "tags": ["work", "important"]
}
```

**Response:**
```json
{
  "chat_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### List Chats
```http
GET /api/chats?limit=50&cursor=optional_cursor
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "My Chat",
      "tags": ["work", "important"],
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:00:00Z",
      "last_message_at": "2024-01-01T12:30:00Z"
    }
  ],
  "next_cursor": null
}
```

### Get Chat Messages
```http
GET /api/chats/{chat_id}/messages?limit=50&cursor=optional_cursor
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": "msg-123",
      "role": "user",
      "content": "Hello, AI!",
      "created_at": "2024-01-01T12:00:00Z"
    },
    {
      "id": "msg-124",
      "role": "assistant",
      "content": "Hello! How can I help you today?",
      "created_at": "2024-01-01T12:00:05Z"
    }
  ],
  "next_cursor": null
}
```

### Send Message
```http
POST /api/chats/{chat_id}/messages
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "Hello, AI!",
  "use_rag": false,
  "response_stream": false
}
```

**Response:**
```json
{
  "message_id": "msg-124",
  "content": "Hello! How can I help you today?",
  "answer": "Hello! How can I help you today?"
}
```

### Send Message (Streaming)
```http
POST /api/chats/{chat_id}/messages
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "Hello, AI!",
  "use_rag": false,
  "response_stream": true
}
```

**Response:** Server-Sent Events stream
```
data: {"content": "Hello"}

data: {"content": "! How"}

data: {"content": " can I"}

data: [DONE]
```

### Update Chat Tags
```http
PUT /api/chats/{chat_id}/tags
Authorization: Bearer <token>
Content-Type: application/json

{
  "tags": ["updated", "tags"]
}
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "tags": ["updated", "tags"]
}
```

### Delete Chat
```http
DELETE /api/chats/{chat_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "deleted": true
}
```

## RAG Documents API

### Upload Document
```http
POST /api/rag/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: [binary file]
tags: ["document", "important"]
```

**Response:**
```json
{
  "id": "doc-123",
  "key": "doc-123/origin.pdf",
  "status": "uploaded",
  "tags": ["document", "important"]
}
```

### List Documents
```http
GET /api/rag/?page=1&size=20&status=ready&search=keyword
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": "doc-123",
      "name": "document.pdf",
      "status": "ready",
      "date_upload": "2024-01-01T12:00:00Z",
      "url_file": "doc-123/origin.pdf",
      "url_canonical_file": "doc-123/canonical.txt",
      "tags": ["document", "important"],
      "progress": null,
      "updated_at": "2024-01-01T12:05:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "size": 20,
    "total": 100,
    "total_pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

### Get Document
```http
GET /api/rag/{doc_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "doc-123",
  "name": "document.pdf",
  "status": "ready",
  "date_upload": "2024-01-01T12:00:00Z",
  "url_file": "doc-123/origin.pdf",
  "url_canonical_file": "doc-123/canonical.txt",
  "tags": ["document", "important"],
  "error": null,
  "updated_at": "2024-01-01T12:05:00Z"
}
```

### Search Documents
```http
POST /api/rag/search
Authorization: Bearer <token>
Content-Type: application/json

{
  "text": "search query",
  "top_k": 10,
  "min_score": 0.5
}
```

**Response:**
```json
{
  "items": [
    {
      "id": "chunk-123",
      "document_id": "doc-123",
      "text": "Relevant text content...",
      "score": 0.85,
      "snippet": "Relevant text content..."
    }
  ]
}
```

### Update Document Tags
```http
PUT /api/rag/{doc_id}/tags
Authorization: Bearer <token>
Content-Type: application/json

["updated", "tags"]
```

**Response:**
```json
{
  "id": "doc-123",
  "tags": ["updated", "tags"]
}
```

### Archive Document
```http
POST /api/rag/{doc_id}/archive
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "doc-123",
  "status": "archived"
}
```

### Delete Document
```http
DELETE /api/rag/{doc_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "doc-123",
  "deleted": true
}
```

### Get RAG Metrics
```http
GET /api/rag/metrics
Authorization: Bearer <token>
```

**Response:**
```json
{
  "total_documents": 150,
  "total_chunks": 5000,
  "processing_documents": 5,
  "storage_size_bytes": 1048576000,
  "storage_size_mb": 1000.0,
  "status_breakdown": {
    "ready": 120,
    "processing": 5,
    "error": 10,
    "archived": 15
  },
  "ready_documents": 120,
  "error_documents": 10
}
```

## Analysis API

### Upload Analysis File
```http
POST /api/analyze/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: [binary file]
```

**Response:**
```json
{
  "id": "analysis-123",
  "status": "uploaded"
}
```

### List Analysis Documents
```http
GET /api/analyze/
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": "analysis-123",
      "status": "ready",
      "date_upload": "2024-01-01T12:00:00Z",
      "url_file": "analysis-123/file.pdf",
      "result": "Analysis result...",
      "error": null
    }
  ]
}
```

### Download Analysis File
```http
GET /api/analyze/{doc_id}/download
Authorization: Bearer <token>
```

**Response:** Binary file download

## Error Responses

### Validation Error (422)
```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Not Found (404)
```json
{
  "detail": "not_found"
}
```

### Server Error (500)
```json
{
  "detail": "Internal server error"
}
```

## Rate Limiting
- General: 100 req/min/user
- File upload: 10 req/min/user
- Search: 50 req/min/user

**Headers**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## WebSocket Events

### Chat Message Streaming
Connect to: `ws://localhost:8000/ws/chat/{chat_id}`

**Events:**
- `message` — New message received
- `typing` — User is typing
- `error` — Error occurred
