"""
Enhanced RAG service with comprehensive business logic
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import hashlib
import mimetypes
import os

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services._base import BaseService, AsyncBaseService, RepositoryService, AsyncRepositoryService
from app.repositories.rag_repo import (
    RAGDocumentsRepository, RAGChunksRepository,
    create_rag_documents_repository, create_rag_chunks_repository,
    create_async_rag_documents_repository, create_async_rag_chunks_repository
)
from app.models.rag import RAGDocument, RAGChunk
from app.adapters.s3_client import s3_manager
from app.core.logging import get_logger

logger = get_logger(__name__)

# Allowed file extensions for RAG documents
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.rtf', '.odt', '.html', '.htm'}

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

class RAGDocumentsService(RepositoryService[RAGDocument]):
    """Enhanced RAG documents service with comprehensive business logic"""
    
    def __init__(self, session: Session):
        self.documents_repo = create_rag_documents_repository(session)
        self.chunks_repo = create_rag_chunks_repository(session)
        super().__init__(session, self.documents_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for document creation"""
        return ["filename", "title", "user_id"]
    
    def _process_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process document creation data"""
        processed = data.copy()
        
        # Sanitize filename
        if "filename" in processed:
            processed["filename"] = self._sanitize_string(processed["filename"], 255)
        
        # Sanitize title
        if "title" in processed:
            processed["title"] = self._sanitize_string(processed["title"], 500)
        
        # Sanitize tags
        if "tags" in processed and processed["tags"]:
            if not isinstance(processed["tags"], list):
                raise ValueError("Tags must be a list")
            processed["tags"] = [self._sanitize_string(tag, 50) for tag in processed["tags"]]
        
        # Set default values
        processed.setdefault("status", "uploading")
        processed.setdefault("tags", [])
        processed.setdefault("created_at", self._get_current_time())
        processed.setdefault("updated_at", self._get_current_time())
        
        return processed
    
    def _process_update_data(self, data: Dict[str, Any], existing_entity: RAGDocument) -> Dict[str, Any]:
        """Process document update data"""
        processed = data.copy()
        
        # Sanitize title if provided
        if "title" in processed and processed["title"]:
            processed["title"] = self._sanitize_string(processed["title"], 500)
        
        # Sanitize tags if provided
        if "tags" in processed and processed["tags"]:
            if not isinstance(processed["tags"], list):
                raise ValueError("Tags must be a list")
            processed["tags"] = [self._sanitize_string(tag, 50) for tag in processed["tags"]]
        
        # Update timestamp
        processed["updated_at"] = self._get_current_time()
        
        return processed
    
    def _can_delete(self, entity: RAGDocument) -> bool:
        """Check if document can be deleted"""
        # Documents can always be deleted (chunks will be cascade deleted)
        return True
    
    def create_document(self, filename: str, title: str, user_id: str,
                       content_type: Optional[str] = None, size: Optional[int] = None,
                       tags: Optional[List[str]] = None) -> RAGDocument:
        """Create a new RAG document"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            # Validate filename
            if not filename or len(filename.strip()) < 1:
                raise ValueError("Filename cannot be empty")
            
            if len(filename) > 255:
                raise ValueError("Filename too long (max 255 characters)")
            
            # Validate title
            if not title or len(title.strip()) < 1:
                raise ValueError("Title cannot be empty")
            
            if len(title) > 500:
                raise ValueError("Title too long (max 500 characters)")
            
            # Validate file extension
            file_ext = self._get_file_extension(filename)
            if file_ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
            
            # Validate file size
            if size and size > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")
            
            # Validate tags
            if tags:
                if not isinstance(tags, list):
                    raise ValueError("Tags must be a list")
                if len(tags) > 20:
                    raise ValueError("Too many tags (max 20)")
                for tag in tags:
                    if not isinstance(tag, str) or len(tag) > 50:
                        raise ValueError("Invalid tag format")
            
            # Determine content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                content_type = content_type or "application/octet-stream"
            
            # Create document
            document = self.documents_repo.create_document(
                filename=filename,
                title=title,
                user_id=user_id,
                content_type=content_type,
                size=size,
                tags=tags or []
            )
            
            self._log_operation("create_document", str(document.id), {
                "user_id": user_id,
                "filename": filename,
                "title": title
            })
            
            return document
            
        except Exception as e:
            self._handle_error("create_document", e, {
                "user_id": user_id,
                "filename": filename,
                "title": title
            })
            raise
    
    def get_user_documents(self, user_id: str, status: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get documents for a user"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            documents = self.documents_repo.get_user_documents(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset
            )
            
            self._log_operation("get_user_documents", user_id, {
                "status": status,
                "count": len(documents)
            })
            
            return documents
            
        except Exception as e:
            self._handle_error("get_user_documents", e, {"user_id": user_id, "status": status})
            raise
    
    def get_document(self, document_id: str, user_id: str) -> Optional[RAGDocument]:
        """Get document by ID, ensuring user has access"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            document = self.documents_repo.get_by_id(document_id)
            if not document:
                return None
            
            # Check ownership
            if str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            self._log_operation("get_document", document_id, {"user_id": user_id})
            return document
            
        except Exception as e:
            self._handle_error("get_document", e, {"document_id": document_id, "user_id": user_id})
            raise
    
    def update_document_status(self, document_id: str, user_id: str, status: str,
                              error_message: Optional[str] = None) -> Optional[RAGDocument]:
        """Update document status"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            # Validate status
            valid_statuses = ["uploading", "processing", "processed", "failed", "archived"]
            if status not in valid_statuses:
                raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
            
            updated_document = self.documents_repo.update_document_status(
                document_id, status, error_message
            )
            
            if updated_document:
                self._log_operation("update_document_status", document_id, {
                    "user_id": user_id,
                    "status": status,
                    "has_error": error_message is not None
                })
            
            return updated_document
            
        except Exception as e:
            self._handle_error("update_document_status", e, {
                "document_id": document_id,
                "user_id": user_id,
                "status": status
            })
            raise
    
    def search_documents(self, user_id: str, query: str, status: Optional[str] = None,
                        limit: int = 50) -> List[RAGDocument]:
        """Search user's documents"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            if not query or len(query.strip()) < 2:
                raise ValueError("Search query too short (min 2 characters)")
            
            documents = self.documents_repo.search_documents(
                user_id=user_id,
                query=query,
                status=status,
                limit=limit
            )
            
            self._log_operation("search_documents", user_id, {
                "query": query,
                "status": status,
                "count": len(documents)
            })
            
            return documents
            
        except Exception as e:
            self._handle_error("search_documents", e, {
                "user_id": user_id,
                "query": query,
                "status": status
            })
            raise
    
    def get_documents_by_tag(self, user_id: str, tag: str, limit: int = 50) -> List[RAGDocument]:
        """Get documents by tag"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            if not tag or len(tag.strip()) < 1:
                raise ValueError("Tag cannot be empty")
            
            documents = self.documents_repo.get_documents_by_tag(user_id, tag, limit)
            
            self._log_operation("get_documents_by_tag", user_id, {
                "tag": tag,
                "count": len(documents)
            })
            
            return documents
            
        except Exception as e:
            self._handle_error("get_documents_by_tag", e, {"user_id": user_id, "tag": tag})
            raise
    
    def get_document_stats(self, user_id: str) -> Dict[str, Any]:
        """Get document statistics for a user"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            stats = self.documents_repo.get_document_stats(user_id)
            
            self._log_operation("get_document_stats", user_id, stats)
            return stats
            
        except Exception as e:
            self._handle_error("get_document_stats", e, {"user_id": user_id})
            raise
    
    def delete_document(self, document_id: str, user_id: str, hard: bool = False) -> bool:
        """Delete document (soft or hard delete)"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            if hard:
                # Hard delete: remove from database and S3
                result = self.documents_repo.delete_document(document_id)
                
                # TODO: Delete from S3 and vector database
                # This would require integration with S3 and Qdrant services
                
                self._log_operation("delete_document_hard", document_id, {"user_id": user_id})
            else:
                # Soft delete: mark as archived
                self.documents_repo.update_document_status(document_id, "archived")
                result = True
                
                self._log_operation("delete_document_soft", document_id, {"user_id": user_id})
            
            return result
            
        except Exception as e:
            self._handle_error("delete_document", e, {
                "document_id": document_id,
                "user_id": user_id,
                "hard": hard
            })
            raise
    
    def generate_upload_url(self, document_id: str, user_id: str, filename: str) -> Dict[str, Any]:
        """Generate presigned URL for document upload"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            # Generate S3 key
            file_ext = self._get_file_extension(filename)
            s3_key = f"rag/{document_id}/origin{file_ext}"
            
            # Generate presigned URL
            upload_url = s3_manager.presign_put(
                bucket="rag-documents",
                key=s3_key,
                expires_in=3600  # 1 hour
            )
            
            # Update document with S3 key
            self.documents_repo.update(document_id, s3_key_raw=s3_key)
            
            self._log_operation("generate_upload_url", document_id, {
                "user_id": user_id,
                "filename": filename,
                "s3_key": s3_key
            })
            
            return {
                "document_id": document_id,
                "upload_url": upload_url,
                "s3_key": s3_key,
                "expires_in": 3600
            }
            
        except Exception as e:
            self._handle_error("generate_upload_url", e, {
                "document_id": document_id,
                "user_id": user_id,
                "filename": filename
            })
            raise
    
    def _get_file_extension(self, filename: str) -> str:
        """Get file extension in lowercase"""
        if not filename or '.' not in filename:
            return ''
        return '.' + filename.rsplit('.', 1)[-1].lower()


class RAGChunksService(BaseService):
    """Service for RAG chunks"""
    
    def __init__(self, session: Session):
        super().__init__(session)
        self.chunks_repo = create_rag_chunks_repository(session)
        self.documents_repo = create_rag_documents_repository(session)
    
    def create_chunk(self, document_id: str, user_id: str, content: str, chunk_index: int,
                    embedding: Optional[List[float]] = None, vector_id: Optional[str] = None,
                    chunk_metadata: Optional[Dict[str, Any]] = None) -> RAGChunk:
        """Create a new RAG chunk"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check document ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            # Validate content
            if not content or len(content.strip()) < 1:
                raise ValueError("Content cannot be empty")
            
            if len(content) > 10000:  # Max chunk size
                raise ValueError("Content too long (max 10000 characters)")
            
            # Validate chunk index
            if chunk_index < 0:
                raise ValueError("Chunk index must be non-negative")
            
            # Create chunk
            chunk = self.chunks_repo.create_chunk(
                document_id=document_id,
                content=content,
                chunk_index=chunk_index,
                embedding=embedding,
                vector_id=vector_id,
                chunk_metadata=chunk_metadata or {}
            )
            
            self._log_operation("create_chunk", str(chunk.id), {
                "document_id": document_id,
                "user_id": user_id,
                "chunk_index": chunk_index
            })
            
            return chunk
            
        except Exception as e:
            self._handle_error("create_chunk", e, {
                "document_id": document_id,
                "user_id": user_id,
                "chunk_index": chunk_index
            })
            raise
    
    def get_document_chunks(self, document_id: str, user_id: str, limit: int = 1000) -> List[RAGChunk]:
        """Get chunks for a document"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check document ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            chunks = self.chunks_repo.get_document_chunks(document_id, limit)
            
            self._log_operation("get_document_chunks", document_id, {
                "user_id": user_id,
                "count": len(chunks)
            })
            
            return chunks
            
        except Exception as e:
            self._handle_error("get_document_chunks", e, {
                "document_id": document_id,
                "user_id": user_id
            })
            raise
    
    def search_chunks(self, document_id: str, user_id: str, query: str,
                     limit: int = 50) -> List[RAGChunk]:
        """Search chunks in a document"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check document ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            if not query or len(query.strip()) < 2:
                raise ValueError("Search query too short (min 2 characters)")
            
            chunks = self.chunks_repo.search_chunks(document_id, query, limit)
            
            self._log_operation("search_chunks", document_id, {
                "user_id": user_id,
                "query": query,
                "count": len(chunks)
            })
            
            return chunks
            
        except Exception as e:
            self._handle_error("search_chunks", e, {
                "document_id": document_id,
                "user_id": user_id,
                "query": query
            })
            raise
    
    def get_chunk_stats(self, document_id: str, user_id: str) -> Dict[str, Any]:
        """Get chunk statistics for a document"""
        try:
            if not self._validate_uuid(document_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check document ownership
            document = self.documents_repo.get_by_id(document_id)
            if not document or str(document.user_id) != user_id:
                raise ValueError("Access denied")
            
            # Get chunk counts
            total_chunks = self.chunks_repo.count_document_chunks(document_id)
            chunks_with_embeddings = len(self.chunks_repo.get_chunks_without_embeddings(1))  # Just check if any exist
            
            stats = {
                "document_id": document_id,
                "total_chunks": total_chunks,
                "chunks_with_embeddings": total_chunks - chunks_with_embeddings,
                "chunks_without_embeddings": chunks_with_embeddings
            }
            
            return stats
            
        except Exception as e:
            self._handle_error("get_chunk_stats", e, {
                "document_id": document_id,
                "user_id": user_id
            })
            raise


# Async versions
class AsyncRAGDocumentsService(AsyncRepositoryService[RAGDocument]):
    """Async RAG documents service"""
    
    def __init__(self, session: AsyncSession):
        self.documents_repo = create_async_rag_documents_repository(session)
        super().__init__(session, self.documents_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for document creation"""
        return ["filename", "title", "user_id"]
    
    async def create_document(self, filename: str, title: str, user_id: str,
                             content_type: Optional[str] = None, size: Optional[int] = None,
                             tags: Optional[List[str]] = None) -> RAGDocument:
        """Create a new RAG document"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            if not filename or len(filename.strip()) < 1:
                raise ValueError("Filename cannot be empty")
            
            if not title or len(title.strip()) < 1:
                raise ValueError("Title cannot be empty")
            
            # Validate file extension
            file_ext = self._get_file_extension(filename)
            if file_ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
            
            document = await self.documents_repo.create_document(
                filename=filename,
                title=title,
                user_id=user_id,
                content_type=content_type,
                size=size,
                tags=tags or []
            )
            
            self._log_operation("create_document", str(document.id), {
                "user_id": user_id,
                "filename": filename,
                "title": title
            })
            
            return document
            
        except Exception as e:
            self._handle_error("create_document", e, {
                "user_id": user_id,
                "filename": filename,
                "title": title
            })
            raise
    
    def _get_file_extension(self, filename: str) -> str:
        """Get file extension in lowercase"""
        if not filename or '.' not in filename:
            return ''
        return '.' + filename.rsplit('.', 1)[-1].lower()


# Factory functions
def create_rag_documents_service(session: Session) -> RAGDocumentsService:
    """Create RAG documents service"""
    return RAGDocumentsService(session)

def create_rag_chunks_service(session: Session) -> RAGChunksService:
    """Create RAG chunks service"""
    return RAGChunksService(session)

def create_async_rag_documents_service(session: AsyncSession) -> AsyncRAGDocumentsService:
    """Create async RAG documents service"""
    return AsyncRAGDocumentsService(session)
