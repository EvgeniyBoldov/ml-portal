"""
Mixin for services that need idempotency support
"""
from __future__ import annotations
from typing import Optional, Dict, Any, Callable, TypeVar, Generic
from abc import ABC, abstractmethod
import uuid

from app.services.idempotency_service import IdempotencyService
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class IdempotentServiceMixin(ABC):
    """Mixin for services that support idempotency"""
    
    def __init__(self, idempotency_service: Optional[IdempotencyService] = None):
        self.idempotency_service = idempotency_service
    
    def execute_with_idempotency(
        self,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        idempotency_key: Optional[str],
        operation: Callable[[], T],
        method: str = "POST",
        path: str = "/api/v1/operation",
        request_body: Optional[Dict[str, Any]] = None
    ) -> T:
        """
        Execute operation with idempotency support
        
        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            idempotency_key: Optional idempotency key
            operation: Function to execute
            method: HTTP method
            path: API path
            request_body: Request body for hashing
            
        Returns:
            Result of operation or cached result
        """
        if not idempotency_key or not self.idempotency_service:
            # No idempotency support, execute directly
            return operation()
        
        try:
            # Try to reserve the key
            is_reserved, cached_response = self.idempotency_service.try_reserve_key(
                tenant_id, user_id, idempotency_key, method, path, request_body
            )
            
            if not is_reserved and cached_response:
                # Return cached response
                logger.info(f"Returning cached response for idempotency key {idempotency_key}")
                return self._deserialize_cached_response(cached_response)
            
            # Execute the operation
            result = operation()
            
            # Store the result
            self._store_operation_result(
                tenant_id, user_id, idempotency_key, method, path, request_body, result
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in idempotent operation: {e}")
            # If idempotency fails, still execute the operation
            return operation()
    
    def _store_operation_result(
        self,
        tenant_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        idempotency_key: str,
        method: str,
        path: str,
        request_body: Optional[Dict[str, Any]],
        result: Any
    ):
        """Store operation result for idempotency"""
        try:
            # Serialize result
            serialized_result = self._serialize_result(result)
            
            # Store in idempotency service
            self.idempotency_service.store_response(
                tenant_id, user_id, idempotency_key, method, path, request_body,
                response_status=200,
                response_body=serialized_result,
                response_headers={'Content-Type': 'application/json'}
            )
            
        except Exception as e:
            logger.error(f"Error storing operation result: {e}")
    
    @abstractmethod
    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        """Serialize result for storage"""
        pass
    
    @abstractmethod
    def _deserialize_cached_response(self, cached_response: Dict[str, Any]) -> Any:
        """Deserialize cached response"""
        pass


class ChatServiceWithIdempotency(IdempotentServiceMixin):
    """Chat service with idempotency support"""
    
    def create_chat_message_with_idempotency(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        **kwargs
    ):
        """Create chat message with idempotency"""
        
        def create_message():
            # This would call the actual chat message creation logic
            # For now, return a mock result
            return {
                'message_id': str(uuid.uuid4()),
                'chat_id': str(chat_id),
                'content': content,
                'created_at': '2024-01-01T00:00:00Z'
            }
        
        return self.execute_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=create_message,
            method="POST",
            path=f"/api/v1/chats/{chat_id}/messages",
            request_body={'content': content}
        )
    
    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        """Serialize chat message result"""
        if isinstance(result, dict):
            return result
        else:
            return {'result': str(result)}
    
    def _deserialize_cached_response(self, cached_response: Dict[str, Any]) -> Any:
        """Deserialize cached chat message response"""
        return cached_response.get('body', {})


class RAGServiceWithIdempotency(IdempotentServiceMixin):
    """RAG service with idempotency support"""
    
    def register_document_with_idempotency(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        document_data: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ):
        """Register document with idempotency"""
        
        def register_document():
            # This would call the actual document registration logic
            # For now, return a mock result
            return {
                'document_id': str(uuid.uuid4()),
                'status': 'registered',
                'created_at': '2024-01-01T00:00:00Z'
            }
        
        return self.execute_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=register_document,
            method="POST",
            path="/api/v1/rag/documents",
            request_body=document_data
        )
    
    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        """Serialize RAG document result"""
        if isinstance(result, dict):
            return result
        else:
            return {'result': str(result)}
    
    def _deserialize_cached_response(self, cached_response: Dict[str, Any]) -> Any:
        """Deserialize cached RAG document response"""
        return cached_response.get('body', {})


class AnalyzeServiceWithIdempotency(IdempotentServiceMixin):
    """Analyze service with idempotency support"""
    
    def run_analysis_with_idempotency(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        analyze_id: uuid.UUID,
        question: str,
        idempotency_key: Optional[str] = None,
        **kwargs
    ):
        """Run analysis with idempotency"""
        
        def run_analysis():
            # This would call the actual analysis logic
            # For now, return a mock result
            return {
                'analysis_id': str(analyze_id),
                'question': question,
                'answer': 'Mock analysis result',
                'citations': [],
                'status': 'completed'
            }
        
        return self.execute_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=run_analysis,
            method="POST",
            path=f"/api/v1/analyze/{analyze_id}/run",
            request_body={'question': question}
        )
    
    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        """Serialize analysis result"""
        if isinstance(result, dict):
            return result
        else:
            return {'result': str(result)}
    
    def _deserialize_cached_response(self, cached_response: Dict[str, Any]) -> Any:
        """Deserialize cached analysis response"""
        return cached_response.get('body', {})
