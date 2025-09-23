"""
RAG API controller
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.api.controllers._base import BaseController, PaginatedResponse
from app.api.schemas.rag import (
    RAGDocumentCreateRequest, RAGDocumentUpdateRequest, RAGDocumentSearchRequest,
    RAGDocumentListRequest, RAGDocumentResponse, RAGDocumentListResponse,
    RAGDocumentStatsResponse, RAGUploadResponse, RAGSearchRequest, RAGSearchResponse,
    RAGChunkCreateRequest, RAGChunkSearchRequest, RAGChunkResponse, RAGChunkListResponse,
    RAGChunkStatsResponse
)
from app.services.rag_service_enhanced import RAGDocumentsService, RAGChunksService, create_rag_documents_service, create_rag_chunks_service
from app.api.deps import db_session, get_current_user

router = APIRouter(prefix="/rag", tags=["rag"])

def get_rag_documents_service(session: Session = Depends(db_session)) -> RAGDocumentsService:
    """Get RAG documents service"""
    return create_rag_documents_service(session)

def get_rag_chunks_service(session: Session = Depends(db_session)) -> RAGChunksService:
    """Get RAG chunks service"""
    return create_rag_chunks_service(session)

class RAGDocumentsController(BaseController):
    """RAG documents API controller"""
    
    def __init__(self, service: RAGDocumentsService):
        super().__init__(service)
    
    async def create_document(self, request: RAGDocumentCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new RAG document"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            document = self.service.create_document(
                filename=request.filename,
                title=request.title,
                user_id=user_info["user_id"],
                content_type=request.content_type,
                size=request.size,
                tags=request.tags
            )
            
            self._log_api_operation("create_document", user_info, request_id, {
                "document_id": str(document.id),
                "file_name": request.filename,
                "title": request.title
            })
            
            return self._create_success_response(
                data=RAGDocumentResponse.from_orm(document).dict(),
                message="Document created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_document", e, request_id)
    
    async def get_document(self, document_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get document by ID"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            document = self.service.get_document(document_id, user_info["user_id"])
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "document_not_found", "Document not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("get_document", user_info, request_id, {"document_id": document_id})
            
            return self._create_success_response(
                data=RAGDocumentResponse.from_orm(document).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_document", e, request_id)
    
    async def update_document(self, document_id: str, request: RAGDocumentUpdateRequest, 
                             current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Update document"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            # Prepare update data
            update_data = {}
            if request.title is not None:
                update_data["title"] = request.title
            if request.tags is not None:
                update_data["tags"] = request.tags
            
            if not update_data:
                raise ValueError("No fields to update")
            
            document = self.service.update(document_id, **update_data)
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "document_not_found", "Document not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("update_document", user_info, request_id, {
                "document_id": document_id,
                "updated_fields": list(update_data.keys())
            })
            
            return self._create_success_response(
                data=RAGDocumentResponse.from_orm(document).dict(),
                message="Document updated successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("update_document", e, request_id)
    
    async def delete_document(self, document_id: str, hard: bool, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Delete document"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            result = self.service.delete_document(document_id, user_info["user_id"], hard)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "document_not_found", "Document not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("delete_document", user_info, request_id, {
                "document_id": document_id,
                "hard_delete": hard
            })
            
            return self._create_success_response(
                data={"deleted": True, "hard": hard},
                message="Document deleted successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("delete_document", e, request_id)
    
    async def get_user_documents(self, request: RAGDocumentListRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get user's documents"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_pagination_params(request.limit, request.offset)
            
            documents = self.service.get_user_documents(
                user_id=user_info["user_id"],
                status=request.status.value if request.status else None,
                limit=request.limit,
                offset=request.offset
            )
            
            total = self.service.count()  # This is approximate, in real implementation we'd count properly
            
            self._log_api_operation("get_user_documents", user_info, request_id, {
                "status": request.status.value if request.status else None,
                "results_count": len(documents)
            })
            
            return self._create_success_response(
                data=RAGDocumentListResponse(
                    documents=[RAGDocumentResponse.from_orm(doc).dict() for doc in documents],
                    total=total,
                    limit=request.limit,
                    offset=request.offset,
                    has_more=request.offset + request.limit < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_user_documents", e, request_id)
    
    async def search_documents(self, request: RAGDocumentSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Search documents"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_pagination_params(request.limit, request.offset)
            
            documents = self.service.search_documents(
                user_id=user_info["user_id"],
                query=request.query,
                status=request.status.value if request.status else None,
                limit=request.limit
            )
            
            # Filter by tag if specified
            if request.tag:
                documents = [doc for doc in documents if request.tag in doc.tags]
            
            total = len(documents)  # This is approximate
            
            self._log_api_operation("search_documents", user_info, request_id, {
                "query": request.query,
                "status": request.status.value if request.status else None,
                "tag": request.tag,
                "results_count": len(documents)
            })
            
            return self._create_success_response(
                data=RAGDocumentListResponse(
                    documents=[RAGDocumentResponse.from_orm(doc).dict() for doc in documents],
                    total=total,
                    limit=request.limit,
                    offset=request.offset,
                    has_more=request.offset + request.limit < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("search_documents", e, request_id)
    
    async def get_document_stats(self, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get document statistics"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            stats = self.service.get_document_stats(user_info["user_id"])
            
            self._log_api_operation("get_document_stats", user_info, request_id)
            
            return self._create_success_response(
                data=stats,
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_document_stats", e, request_id)
    
    async def generate_upload_url(self, document_id: str, filename: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Generate upload URL for document"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            upload_info = self.service.generate_upload_url(document_id, user_info["user_id"], filename)
            
            self._log_api_operation("generate_upload_url", user_info, request_id, {
                "document_id": document_id,
                "filename": filename
            })
            
            return self._create_success_response(
                data=upload_info,
                message="Upload URL generated successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("generate_upload_url", e, request_id)

class RAGChunksController(BaseController):
    """RAG chunks API controller"""
    
    def __init__(self, service: RAGChunksService):
        super().__init__(service)
    
    async def create_chunk(self, document_id: str, request: RAGChunkCreateRequest, 
                          current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new RAG chunk"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            chunk = self.service.create_chunk(
                document_id=document_id,
                user_id=user_info["user_id"],
                content=request.content,
                chunk_index=request.chunk_index,
                embedding=request.embedding,
                vector_id=request.vector_id,
                chunk_metadata=request.chunk_metadata
            )
            
            self._log_api_operation("create_chunk", user_info, request_id, {
                "document_id": document_id,
                "chunk_id": str(chunk.id),
                "chunk_index": request.chunk_index
            })
            
            return self._create_success_response(
                data=RAGChunkResponse.from_orm(chunk).dict(),
                message="Chunk created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_chunk", e, request_id)
    
    async def get_document_chunks(self, document_id: str, limit: int, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get document chunks"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            self._validate_pagination_params(limit, 0)
            
            chunks = self.service.get_document_chunks(document_id, user_info["user_id"], limit)
            
            self._log_api_operation("get_document_chunks", user_info, request_id, {
                "document_id": document_id,
                "results_count": len(chunks)
            })
            
            return self._create_success_response(
                data=RAGChunkListResponse(
                    chunks=[RAGChunkResponse.from_orm(chunk).dict() for chunk in chunks],
                    total=len(chunks),
                    limit=limit,
                    offset=0,
                    has_more=False  # This would need proper pagination in real implementation
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_document_chunks", e, request_id)
    
    async def search_chunks(self, document_id: str, request: RAGChunkSearchRequest, 
                           current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Search chunks in document"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            self._validate_pagination_params(request.limit, request.offset)
            
            chunks = self.service.search_chunks(
                document_id=document_id,
                user_id=user_info["user_id"],
                query=request.query
            )
            
            # Apply pagination
            total = len(chunks)
            start = request.offset
            end = start + request.limit
            chunks = chunks[start:end]
            
            self._log_api_operation("search_chunks", user_info, request_id, {
                "document_id": document_id,
                "query": request.query,
                "results_count": len(chunks)
            })
            
            return self._create_success_response(
                data=RAGChunkListResponse(
                    chunks=[RAGChunkResponse.from_orm(chunk).dict() for chunk in chunks],
                    total=total,
                    limit=request.limit,
                    offset=request.offset,
                    has_more=end < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("search_chunks", e, request_id)
    
    async def get_chunk_stats(self, document_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get chunk statistics"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(document_id, "document_id")
            
            stats = self.service.get_chunk_stats(document_id, user_info["user_id"])
            
            self._log_api_operation("get_chunk_stats", user_info, request_id, {"document_id": document_id})
            
            return self._create_success_response(
                data=stats,
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_chunk_stats", e, request_id)

# API endpoints
@router.post("/documents", response_model=Dict[str, Any])
async def create_document(
    request: RAGDocumentCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Create a new RAG document"""
    controller = RAGDocumentsController(service)
    return await controller.create_document(request, current_user)

@router.get("/documents/{document_id}", response_model=Dict[str, Any])
async def get_document(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Get document by ID"""
    controller = RAGDocumentsController(service)
    return await controller.get_document(document_id, current_user)

@router.put("/documents/{document_id}", response_model=Dict[str, Any])
async def update_document(
    document_id: str,
    request: RAGDocumentUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Update document"""
    controller = RAGDocumentsController(service)
    return await controller.update_document(document_id, request, current_user)

@router.delete("/documents/{document_id}", response_model=Dict[str, Any])
async def delete_document(
    document_id: str,
    hard: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Delete document"""
    controller = RAGDocumentsController(service)
    return await controller.delete_document(document_id, hard, current_user)

@router.post("/documents/search", response_model=Dict[str, Any])
async def search_documents(
    request: RAGDocumentSearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Search documents"""
    controller = RAGDocumentsController(service)
    return await controller.search_documents(request, current_user)

@router.get("/documents", response_model=Dict[str, Any])
async def get_user_documents(
    request: RAGDocumentListRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Get user's documents"""
    controller = RAGDocumentsController(service)
    return await controller.get_user_documents(request, current_user)

@router.get("/documents/stats", response_model=Dict[str, Any])
async def get_document_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Get document statistics"""
    controller = RAGDocumentsController(service)
    return await controller.get_document_stats(current_user)

@router.post("/documents/{document_id}/upload-url", response_model=Dict[str, Any])
async def generate_upload_url(
    document_id: str,
    filename: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGDocumentsService = Depends(get_rag_documents_service)
):
    """Generate upload URL for document"""
    controller = RAGDocumentsController(service)
    return await controller.generate_upload_url(document_id, filename, current_user)

# Chunk endpoints
@router.post("/documents/{document_id}/chunks", response_model=Dict[str, Any])
async def create_chunk(
    document_id: str,
    request: RAGChunkCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGChunksService = Depends(get_rag_chunks_service)
):
    """Create a new RAG chunk"""
    controller = RAGChunksController(service)
    return await controller.create_chunk(document_id, request, current_user)

@router.get("/documents/{document_id}/chunks", response_model=Dict[str, Any])
async def get_document_chunks(
    document_id: str,
    limit: int = 100,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGChunksService = Depends(get_rag_chunks_service)
):
    """Get document chunks"""
    controller = RAGChunksController(service)
    return await controller.get_document_chunks(document_id, limit, current_user)

@router.post("/documents/{document_id}/chunks/search", response_model=Dict[str, Any])
async def search_chunks(
    document_id: str,
    request: RAGChunkSearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGChunksService = Depends(get_rag_chunks_service)
):
    """Search chunks in document"""
    controller = RAGChunksController(service)
    return await controller.search_chunks(document_id, request, current_user)

@router.get("/documents/{document_id}/chunks/stats", response_model=Dict[str, Any])
async def get_chunk_stats(
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: RAGChunksService = Depends(get_rag_chunks_service)
):
    """Get chunk statistics"""
    controller = RAGChunksController(service)
    return await controller.get_chunk_stats(document_id, current_user)
