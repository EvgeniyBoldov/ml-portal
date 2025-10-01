"""
Enhanced AnalyzeService with full orchestration logic
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import uuid

from app.services.chat_service import ChatService, ChatResult
from app.services.rag_search_service import RagSearchService
from app.services.rag_ingest_service import RagIngestService
from app.repositories.factory import RepositoryFactory
from app.services.idempotency_service import IdempotencyService
from app.core.logging import get_logger

logger = get_logger(__name__)


class AnalyzeService:
    """Service for orchestrating document analysis workflow"""
    
    def __init__(
        self, 
        ingest_service: RagIngestService,
        search_service: RagSearchService, 
        chat_service: ChatService,
        repository_factory: RepositoryFactory,
        idempotency_service: Optional[IdempotencyService] = None
    ):
        self.ingest_service = ingest_service
        self.search_service = search_service
        self.chat_service = chat_service
        self.repository_factory = repository_factory
        self.idempotency_service = idempotency_service
    
    def analyze(
        self, 
        tenant_id: uuid.UUID, 
        doc_id: uuid.UUID, 
        question: str, 
        k: int = 5, 
        model: str = "default",
        idempotency_key: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> ChatResult:
        """
        Full orchestration: ingest → search → chat
        
        Args:
            tenant_id: Tenant identifier
            doc_id: Document identifier
            question: User question
            k: Number of relevant chunks to retrieve
            model: LLM model to use
            idempotency_key: Optional idempotency key
            user_id: User identifier
            
        Returns:
            ChatResult with answer and citations
        """
        try:
            # Check idempotency if key provided
            if idempotency_key and self.idempotency_service:
                cached_response = self._check_idempotency(
                    tenant_id, user_id, idempotency_key, question
                )
                if cached_response:
                    return cached_response
            
            logger.info(f"Starting analysis for document {doc_id}, question: {question[:50]}...")
            
            # Step 1: Ensure document is ingested
            ingest_result = self._ensure_document_ingested(tenant_id, doc_id)
            if not ingest_result:
                return ChatResult(
                    text="Document processing failed. Please try again later.",
                    citations=[]
                )
            
            # Step 2: Search for relevant chunks
            relevant_chunks = self._search_relevant_chunks(tenant_id, question, k)
            if not relevant_chunks:
                return ChatResult(
                    text="No relevant information found in the document for your question.",
                    citations=[]
                )
            
            # Step 3: Generate answer using LLM
            answer = self._generate_answer(question, relevant_chunks, model)
            
            # Step 4: Format citations
            citations = self._format_citations(relevant_chunks, doc_id)
            
            result = ChatResult(text=answer, citations=citations)
            
            # Store result for idempotency if key provided
            if idempotency_key and self.idempotency_service:
                self._store_idempotency_result(
                    tenant_id, user_id, idempotency_key, question, result
                )
            
            logger.info(f"Analysis completed for document {doc_id}")
            return result
            
        except Exception as e:
            logger.error(f"Analysis failed for document {doc_id}: {e}")
            return ChatResult(
                text="Analysis failed due to an internal error. Please try again.",
                citations=[]
            )
    
    def analyze_stream(
        self, 
        tenant_id: uuid.UUID, 
        doc_id: uuid.UUID, 
        question: str, 
        k: int = 5, 
        model: str = "default"
    ) -> List[str]:
        """
        Streaming version of analysis
        
        Returns:
            List of streaming chunks
        """
        try:
            logger.info(f"Starting streaming analysis for document {doc_id}")
            
            # Step 1: Ensure document is ingested
            ingest_result = self._ensure_document_ingested(tenant_id, doc_id)
            if not ingest_result:
                yield "Document processing failed. Please try again later."
                return
            
            # Step 2: Search for relevant chunks
            relevant_chunks = self._search_relevant_chunks(tenant_id, question, k)
            if not relevant_chunks:
                yield "No relevant information found in the document for your question."
                return
            
            # Step 3: Stream answer generation
            yield from self._generate_answer_stream(question, relevant_chunks, model)
            
        except Exception as e:
            logger.error(f"Streaming analysis failed for document {doc_id}: {e}")
            yield "Analysis failed due to an internal error. Please try again."
    
    def _ensure_document_ingested(self, tenant_id: uuid.UUID, doc_id: uuid.UUID) -> bool:
        """Ensure document is properly ingested"""
        try:
            # Get document from repository
            rag_repo = self.repository_factory.get_rag_documents_repository()
            document = rag_repo.get_by_id(tenant_id, doc_id)
            
            if not document:
                logger.error(f"Document {doc_id} not found")
                return False
            
            # Check if document is already processed
            if document.status == "processed":
                return True
            
            # Check if document needs ingestion
            if document.status in ["uploaded", "pending_upload"]:
                logger.info(f"Ingesting document {doc_id}")
                
                # Trigger ingestion
                ingest_result = self.ingest_service.ingest_document(
                    tenant_id=str(tenant_id),
                    doc_id=str(doc_id),
                    content_type=document.content_type,
                    url_file=document.url_file
                )
                
                if ingest_result > 0:
                    # Update document status
                    rag_repo.update_document_status(
                        tenant_id, doc_id, "processed", document.version
                    )
                    return True
                else:
                    # Mark as failed
                    rag_repo.update_document_status(
                        tenant_id, doc_id, "failed", document.version,
                        error_message="Ingestion failed"
                    )
                    return False
            
            return document.status == "processed"
            
        except Exception as e:
            logger.error(f"Error ensuring document ingestion: {e}")
            return False
    
    def _search_relevant_chunks(
        self, 
        tenant_id: uuid.UUID, 
        question: str, 
        k: int
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using RAG search"""
        try:
            # Use RAG search service
            search_results = self.search_service.search(
                tenant_id=str(tenant_id),
                query=question,
                k=k
            )
            
            # Format results
            chunks = []
            for result in search_results:
                chunk_data = {
                    'content': result.get('content', ''),
                    'metadata': result.get('metadata', {}),
                    'score': result.get('score', 0.0),
                    'chunk_id': result.get('chunk_id', ''),
                    'document_id': result.get('document_id', '')
                }
                chunks.append(chunk_data)
            
            logger.info(f"Found {len(chunks)} relevant chunks for query")
            return chunks
            
        except Exception as e:
            logger.error(f"Error searching chunks: {e}")
            return []
    
    def _generate_answer(
        self, 
        question: str, 
        relevant_chunks: List[Dict[str, Any]], 
        model: str
    ) -> str:
        """Generate answer using LLM with relevant context"""
        try:
            # Prepare context from chunks
            context_parts = []
            for chunk in relevant_chunks:
                context_parts.append(chunk['content'])
            
            context = "\n\n".join(context_parts)
            
            # Prepare messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": f"""You are a helpful assistant that answers questions based on the provided context. 
                    Use only the information from the context to answer the question. 
                    If the context doesn't contain enough information to answer the question, say so.
                    
                    Context:
                    {context}"""
                },
                {
                    "role": "user", 
                    "content": question
                }
            ]
            
            # Generate answer
            answer = self.chat_service.chat(
                tenant_id="",  # Not used in current implementation
                messages=messages,
                model=model
            )
            
            return answer.text if hasattr(answer, 'text') else str(answer)
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return "I apologize, but I encountered an error while generating the answer."
    
    def _generate_answer_stream(
        self, 
        question: str, 
        relevant_chunks: List[Dict[str, Any]], 
        model: str
    ) -> List[str]:
        """Generate streaming answer using LLM"""
        try:
            # Prepare context from chunks
            context_parts = []
            for chunk in relevant_chunks:
                context_parts.append(chunk['content'])
            
            context = "\n\n".join(context_parts)
            
            # Prepare messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": f"""You are a helpful assistant that answers questions based on the provided context. 
                    Use only the information from the context to answer the question. 
                    If the context doesn't contain enough information to answer the question, say so.
                    
                    Context:
                    {context}"""
                },
                {
                    "role": "user", 
                    "content": question
                }
            ]
            
            # Stream answer
            for chunk in self.chat_service.chat_stream(
                tenant_id="",  # Not used in current implementation
                messages=messages,
                model=model
            ):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error generating streaming answer: {e}")
            yield "I apologize, but I encountered an error while generating the answer."
    
    def _format_citations(
        self, 
        relevant_chunks: List[Dict[str, Any]], 
        doc_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Format citations for the answer"""
        citations = []
        
        for i, chunk in enumerate(relevant_chunks):
            citation = {
                'id': f"citation-{i+1}",
                'document_id': str(doc_id),
                'chunk_id': chunk.get('chunk_id', ''),
                'content': chunk['content'][:200] + "..." if len(chunk['content']) > 200 else chunk['content'],
                'score': chunk.get('score', 0.0),
                'metadata': chunk.get('metadata', {})
            }
            citations.append(citation)
        
        return citations
    
    def _check_idempotency(
        self, 
        tenant_id: uuid.UUID, 
        user_id: Optional[uuid.UUID], 
        key: str, 
        question: str
    ) -> Optional[ChatResult]:
        """Check if result is cached for idempotency"""
        try:
            cached_response = self.idempotency_service.get_cached_response(
                tenant_id, user_id, key, "POST", "/api/v1/analyze", {"question": question}
            )
            
            if cached_response and cached_response.get('status') == 200:
                body = cached_response.get('body', {})
                return ChatResult(
                    text=body.get('text', ''),
                    citations=body.get('citations', [])
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking idempotency: {e}")
            return None
    
    def _store_idempotency_result(
        self, 
        tenant_id: uuid.UUID, 
        user_id: Optional[uuid.UUID], 
        key: str, 
        question: str, 
        result: ChatResult
    ):
        """Store result for idempotency"""
        try:
            self.idempotency_service.store_response(
                tenant_id, user_id, key, "POST", "/api/v1/analyze", 
                {"question": question},
                response_status=200,
                response_body={
                    'text': result.text,
                    'citations': result.citations
                }
            )
            
        except Exception as e:
            logger.error(f"Error storing idempotency result: {e}")


# Factory function
def create_analyze_service(
    ingest_service: RagIngestService,
    search_service: RagSearchService,
    chat_service: ChatService,
    repository_factory: RepositoryFactory,
    idempotency_service: Optional[IdempotencyService] = None
) -> AnalyzeService:
    """Create analyze service with dependencies"""
    return AnalyzeService(
        ingest_service, search_service, chat_service, 
        repository_factory, idempotency_service
    )
