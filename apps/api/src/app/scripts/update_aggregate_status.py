#!/usr/bin/env python3
"""
Script to update existing RAG documents with aggregate status
"""
import asyncio
import sys
import os
from uuid import UUID

# Add the app directory to Python path
sys.path.insert(0, '/app')

from app.core.db import get_session_factory
from app.repositories.factory import AsyncRepositoryFactory
from app.repositories.rag_status_repo import AsyncRAGStatusRepository
from app.services.status_aggregator import calculate_aggregate_status
from app.services.rag_status_manager import RAGStatusManager
from app.models.rag import RAGDocument
from sqlalchemy import select, update

async def update_document_aggregate_status(session, doc_id: UUID):
    """Update aggregate status for a single document"""
    try:
        # Get document
        result = await session.execute(
            select(RAGDocument).where(RAGDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            print(f"Document {doc_id} not found")
            return False
        
        # Get status repository
        status_repo = AsyncRAGStatusRepository(session)
        
        # Get pipeline and embedding nodes
        pipeline_nodes = await status_repo.get_pipeline_nodes(doc_id)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_id)
        
        # Get target models for tenant
        repo_factory = AsyncRepositoryFactory(session, document.tenant_id, None)
        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_id)
        
        # Calculate aggregate status
        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_id,
            pipeline_nodes=pipeline_nodes,
            embedding_nodes=embedding_nodes,
            target_models=target_models
        )
        
        # Update document
        await session.execute(
            update(RAGDocument)
            .where(RAGDocument.id == doc_id)
            .values(
                agg_status=agg_status,
                agg_details_json=agg_details
            )
        )
        
        print(f"Updated document {doc_id}: {agg_status}")
        return True
        
    except Exception as e:
        print(f"Error updating document {doc_id}: {e}")
        return False

async def main():
    """Update all RAG documents with aggregate status"""
    from app.core.db import lifespan
    
    # Initialize database
    async with lifespan():
        session_factory = get_session_factory()
        
        async with session_factory() as session:
            try:
                # Get all RAG documents
                result = await session.execute(select(RAGDocument))
                documents = result.scalars().all()
                
                print(f"Found {len(documents)} documents to update")
                
                updated_count = 0
                for doc in documents:
                    if await update_document_aggregate_status(session, doc.id):
                        updated_count += 1
                
                await session.commit()
                print(f"Successfully updated {updated_count} documents")
                
            except Exception as e:
                print(f"Error: {e}")
                await session.rollback()
                raise

if __name__ == "__main__":
    asyncio.run(main())
