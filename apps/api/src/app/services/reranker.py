from __future__ import annotations

from typing import List, Dict, Any, Tuple
import json
import logging

logger = logging.getLogger(__name__)

class Reranker:
    """
    Reranker using cross-encoder for better search results
    """
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        """Lazy load the cross-encoder model"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Loaded reranker model: {self.model_name}")
            except ImportError:
                logger.warning("sentence-transformers not available, reranking disabled")
                self._model = None
            except Exception as e:
                logger.error(f"Failed to load reranker model: {e}")
                self._model = None
    
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Rerank documents based on query relevance
        
        Args:
            query: Search query
            documents: List of documents with 'text' field
            top_k: Number of top results to return
            
        Returns:
            Reranked list of documents with relevance scores
        """
        if not documents:
            return []
        
        self._load_model()
        
        if self._model is None:
            # Fallback: return original order with dummy scores
            return [{"document": doc, "score": 1.0} for doc in documents[:top_k]]
        
        try:
            # Prepare query-document pairs
            pairs = [(query, doc.get('text', '')) for doc in documents]
            
            # Get relevance scores
            scores = self._model.predict(pairs)
            
            # Combine documents with scores
            scored_docs = []
            for doc, score in zip(documents, scores):
                scored_docs.append({
                    "document": doc,
                    "score": float(score)
                })
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x["score"], reverse=True)
            
            return scored_docs[:top_k]
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Fallback: return original order
            return [{"document": doc, "score": 1.0} for doc in documents[:top_k]]

class SemanticReranker:
    """
    Semantic reranker using embedding similarity
    """
    
    def __init__(self, embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.embedding_model = embedding_model
        self._model = None
    
    def _load_model(self):
        """Lazy load the embedding model"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.embedding_model)
                logger.info(f"Loaded semantic reranker model: {self.embedding_model}")
            except ImportError:
                logger.warning("sentence-transformers not available, semantic reranking disabled")
                self._model = None
            except Exception as e:
                logger.error(f"Failed to load semantic reranker model: {e}")
                self._model = None
    
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Rerank documents using semantic similarity
        """
        if not documents:
            return []
        
        self._load_model()
        
        if self._model is None:
            # Fallback: return original order
            return [{"document": doc, "score": 1.0} for doc in documents[:top_k]]
        
        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
            
            # Encode query and documents
            query_embedding = self._model.encode([query])
            doc_texts = [doc.get('text', '') for doc in documents]
            doc_embeddings = self._model.encode(doc_texts)
            
            # Calculate similarities
            similarities = cosine_similarity(query_embedding, doc_embeddings)[0]
            
            # Combine documents with scores
            scored_docs = []
            for doc, score in zip(documents, similarities):
                scored_docs.append({
                    "document": doc,
                    "score": float(score)
                })
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x["score"], reverse=True)
            
            return scored_docs[:top_k]
            
        except Exception as e:
            logger.error(f"Semantic reranking failed: {e}")
            # Fallback: return original order
            return [{"document": doc, "score": 1.0} for doc in documents[:top_k]]

def rerank_search_results(query: str, results: List[Dict[str, Any]], method: str = "cross-encoder", top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Convenience function for reranking search results
    
    Args:
        query: Search query
        results: List of search results from Qdrant
        method: Reranking method ("cross-encoder" or "semantic")
        top_k: Number of top results to return
        
    Returns:
        Reranked results with relevance scores
    """
    if method == "cross-encoder":
        reranker = Reranker()
    elif method == "semantic":
        reranker = SemanticReranker()
    else:
        logger.warning(f"Unknown reranking method: {method}, using cross-encoder")
        reranker = Reranker()
    
    return reranker.rerank(query, results, top_k)
