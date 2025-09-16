from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.rag import RagDocuments, RagChunks

class RagRepo:
    def __init__(self, session: Session):
        self.s = session

    def create_document(self, **kwargs) -> RagDocuments:
        doc = RagDocuments(**kwargs)
        self.s.add(doc)
        self.s.flush()
        return doc

    def get(self, doc_id) -> Optional[RagDocuments]:
        return self.s.get(RagDocuments, doc_id)

    def list(self, limit: int = 50) -> List[RagDocuments]:
        return self.s.execute(select(RagDocuments).order_by(RagDocuments.date_upload.desc()).limit(limit)).scalars().all()

    def delete(self, doc: RagDocuments):
        self.s.delete(doc)

    def add_chunk(self, **kwargs) -> RagChunks:
        chunk = RagChunks(**kwargs)
        self.s.add(chunk)
        self.s.flush()
        return chunk

    def list_chunks(self, doc_id) -> List[RagChunks]:
        return self.s.execute(select(RagChunks).where(RagChunks.document_id == doc_id).order_by(RagChunks.chunk_idx.asc())).scalars().all()
