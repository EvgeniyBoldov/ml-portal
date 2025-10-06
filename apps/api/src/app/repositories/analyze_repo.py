from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from models.analyze import AnalysisDocuments, AnalysisChunks

class AnalyzeRepo:
    def __init__(self, session: Session):
        self.s = session

    def create_document(self, **kwargs) -> AnalysisDocuments:
        doc = AnalysisDocuments(**kwargs)
        self.s.add(doc)
        self.s.flush()
        return doc

    def get(self, doc_id) -> Optional[AnalysisDocuments]:
        return self.s.get(AnalysisDocuments, doc_id)

    def list(self, limit: int = 50) -> List[AnalysisDocuments]:
        return self.s.execute(select(AnalysisDocuments).order_by(AnalysisDocuments.date_upload.desc()).limit(limit)).scalars().all()

    def delete(self, doc: AnalysisDocuments):
        self.s.delete(doc)

    def add_chunk(self, **kwargs) -> AnalysisChunks:
        chunk = AnalysisChunks(**kwargs)
        self.s.add(chunk)
        self.s.flush()
        return chunk

    def list_chunks(self, doc_id) -> List[AnalysisChunks]:
        return self.s.execute(select(AnalysisChunks).where(AnalysisChunks.document_id == doc_id).order_by(AnalysisChunks.chunk_idx.asc())).scalars().all()
