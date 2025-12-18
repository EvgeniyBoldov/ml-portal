"""
Worker helpers and utilities
"""
import hashlib
import json
from app.core.logging import get_logger
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.common import ChunkProfile, Step
from app.storage.paths import get_idempotency_key, get_lock_key

logger = get_logger(__name__)


def generate_content_hash(content: str) -> str:
    """Generate content hash for idempotency"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def chunk_text_by_tokens(text: str, chunk_size: int = 512, overlap: int = 50) -> List[Dict[str, Any]]:
    """Chunk text by tokens with overlap"""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        chunk = {
            "text": chunk_text,
            "start_pos": i,
            "end_pos": i + len(chunk_words),
            "word_count": len(chunk_words),
            "char_count": len(chunk_text)
        }
        chunks.append(chunk)
    
    return chunks


def chunk_text_by_sentences(text: str, max_chunk_size: int = 512) -> List[Dict[str, Any]]:
    """Chunk text by sentences"""
    import re
    
    # Simple sentence splitting
    sentences = re.split(r'[.!?]+', text)
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_words = sentence.split()
        sentence_size = len(sentence_words)
        
        if current_size + sentence_size > max_chunk_size and current_chunk:
            # Create chunk from current sentences
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "text": chunk_text,
                "start_pos": 0,  # Will be calculated properly
                "end_pos": len(chunk_text.split()),
                "word_count": len(chunk_text.split()),
                "char_count": len(chunk_text)
            })
            current_chunk = [sentence]
            current_size = sentence_size
        else:
            current_chunk.append(sentence)
            current_size += sentence_size
    
    # Add remaining chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        chunks.append({
            "text": chunk_text,
            "start_pos": 0,
            "end_pos": len(chunk_text.split()),
            "word_count": len(chunk_text.split()),
            "char_count": len(chunk_text)
        })
    
    return chunks


def chunk_text_by_paragraphs(text: str, max_chunk_size: int = 512) -> List[Dict[str, Any]]:
    """Chunk text by paragraphs"""
    paragraphs = text.split('\n\n')
    chunks = []
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        words = paragraph.split()
        if len(words) > max_chunk_size:
            # Split long paragraph by tokens
            sub_chunks = chunk_text_by_tokens(paragraph, max_chunk_size)
            chunks.extend(sub_chunks)
        else:
            chunks.append({
                "text": paragraph,
                "start_pos": 0,
                "end_pos": len(words),
                "word_count": len(words),
                "char_count": len(paragraph)
            })
    
    return chunks


def chunk_text_by_markdown(text: str, max_chunk_size: int = 512) -> List[Dict[str, Any]]:
    """
    Chunk text by Markdown headers (#, ##, ###).
    Retains headers in the text for context.
    """
    import re
    
    # Split by headers (looking for # at start of line)
    # Using lookahead to keep the delimiter
    # Regex finds newlines followed by #
    parts = re.split(r'(?=\n#{1,3} )', text)
    
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        # Check size
        words = part.split()
        if len(words) > max_chunk_size:
            # Fallback to paragraph splitting for large sections
            sub_chunks = chunk_text_by_paragraphs(part, max_chunk_size)
            chunks.extend(sub_chunks)
        else:
             chunks.append({
                "text": part,
                "start_pos": 0,
                "end_pos": len(words),
                "word_count": len(words),
                "char_count": len(part)
            })
            
    return chunks


def chunker(text: str, profile: ChunkProfile = ChunkProfile.BY_TOKENS, **kwargs) -> List[Dict[str, Any]]:
    """Main chunking function"""
    if profile == ChunkProfile.BY_TOKENS:
        chunk_size = kwargs.get('chunk_size', 512)
        overlap = kwargs.get('overlap', 50)
        return chunk_text_by_tokens(text, chunk_size, overlap)
    elif profile == ChunkProfile.BY_SENTENCES:
        max_chunk_size = kwargs.get('max_chunk_size', 512)
        return chunk_text_by_sentences(text, max_chunk_size)
    elif profile == ChunkProfile.BY_PARAGRAPHS:
        max_chunk_size = kwargs.get('max_chunk_size', 512)
        return chunk_text_by_paragraphs(text, max_chunk_size)
    elif profile == ChunkProfile.BY_MARKDOWN:
        max_chunk_size = kwargs.get('max_chunk_size', 512)
        return chunk_text_by_markdown(text, max_chunk_size)
    else:
        raise ValueError(f"Unknown chunking profile: {profile}")


def generate_chunk_id(document_id: UUID, start_pos: int, end_pos: int) -> str:
    """Generate deterministic chunk ID"""
    return f"{document_id}:{start_pos}-{end_pos}"


def create_chunk_payload(
    tenant_id: UUID,
    document_id: UUID,
    chunk_id: str,
    text: str,
    start_pos: int,
    end_pos: int,
    page: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create chunk payload for Qdrant"""
    return {
        "tenant_id": str(tenant_id),
        "document_id": str(document_id),
        "chunk_id": chunk_id,
        "text": text,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "page": page,
        "language": metadata.get("language", "en") if metadata else "en",
        "mime_type": metadata.get("mime_type", "text/plain") if metadata else "text/plain",
        "version": metadata.get("version", "v1") if metadata else "v1",
        "embed_model_alias": metadata.get("embed_model_alias", "all-MiniLM-L6-v2") if metadata else "all-MiniLM-L6-v2",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tags": metadata.get("tags", []) if metadata else []
    }


def log_step_progress(
    document_id: UUID,
    step: Step,
    progress: float,
    message: str = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log step progress"""
    log_data = {
        "document_id": str(document_id),
        "step": step.value,
        "progress": progress,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if message:
        log_data["message"] = message
    
    if metadata:
        log_data["metadata"] = metadata
    
    logger.info(f"Step progress: {json.dumps(log_data)}")


def calculate_progress(completed_steps: List[Step], current_step: Step, step_progress: float = 0.0) -> float:
    """Calculate overall progress"""
    total_steps = len(Step)
    completed_count = len(completed_steps)
    
    if current_step in completed_steps:
        return 100.0
    
    base_progress = (completed_count / total_steps) * 100
    step_progress_weight = (1 / total_steps) * 100
    
    return min(base_progress + (step_progress * step_progress_weight), 100.0)