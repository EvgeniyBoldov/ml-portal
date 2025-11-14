#!/usr/bin/env python3
"""
Script to migrate old RAG document statuses to new status system
"""
import asyncio
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "api" / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, update
from app.core.config import get_settings
from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus
from app.services.status_aggregator import calculate_aggregate_status


async def migrate_statuses():
    """Migrate old statuses to new status system"""
    settings = get_settings()
    
    # Create database connection
    engine = create_async_engine(
        settings.ASYNC_DB_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    async with session_factory() as session:
        # Get all documents with old status
        result = await session.execute(
            select(RAGDocument).where(RAGDocument.status.isnot(None))
        )
        documents = result.scalars().all()
        
        print(f"Found {len(documents)} documents to migrate")
        
        migrated_count = 0
        error_count = 0
        
        for doc in documents:
            try:
                print(f"Migrating document {doc.id} (status: {doc.status})")
                
                # Create initial pipeline nodes based on old status
                pipeline_nodes = []
                
                # Upload node is always ok for existing documents
                upload_node = RAGStatus(
                    doc_id=doc.id,
                    node_type='pipeline',
                    node_key='upload',
                    status='ok',
                    started_at=doc.created_at,
                    finished_at=doc.created_at
                )
                pipeline_nodes.append(upload_node)
                
                # Create other pipeline nodes based on old status
                if doc.status in ['processing', 'processed', 'ready']:
                    # Extract node
                    extract_node = RAGStatus(
                        doc_id=doc.id,
                        node_type='pipeline',
                        node_key='extract',
                        status='ok',
                        started_at=doc.created_at,
                        finished_at=doc.created_at
                    )
                    pipeline_nodes.append(extract_node)
                    
                    # Chunk node
                    chunk_node = RAGStatus(
                        doc_id=doc.id,
                        node_type='pipeline',
                        node_key='chunk',
                        status='ok',
                        started_at=doc.created_at,
                        finished_at=doc.created_at
                    )
                    pipeline_nodes.append(chunk_node)
                    
                    # Index node
                    index_node = RAGStatus(
                        doc_id=doc.id,
                        node_type='pipeline',
                        node_key='index',
                        status='ok',
                        started_at=doc.created_at,
                        finished_at=doc.created_at
                    )
                    pipeline_nodes.append(index_node)
                    
                elif doc.status == 'failed':
                    # Extract node failed
                    extract_node = RAGStatus(
                        doc_id=doc.id,
                        node_type='pipeline',
                        node_key='extract',
                        status='error',
                        error_short=doc.error_message or 'Migration: Unknown error',
                        started_at=doc.created_at,
                        finished_at=doc.updated_at
                    )
                    pipeline_nodes.append(extract_node)
                    
                    # Other nodes pending
                    for stage in ['chunk', 'index']:
                        pending_node = RAGStatus(
                            doc_id=doc.id,
                            node_type='pipeline',
                            node_key=stage,
                            status='pending'
                        )
                        pipeline_nodes.append(pending_node)
                        
                else:
                    # Other statuses - create pending nodes
                    for stage in ['extract', 'chunk', 'index']:
                        pending_node = RAGStatus(
                            doc_id=doc.id,
                            node_type='pipeline',
                            node_key=stage,
                            status='pending'
                        )
                        pipeline_nodes.append(pending_node)
                
                # Add pipeline nodes to session
                for node in pipeline_nodes:
                    session.add(node)
                
                # Calculate aggregate status
                embedding_nodes = []  # No embedding nodes for migration
                target_models = []  # No target models for migration
                
                agg_status, agg_details = calculate_aggregate_status(
                    doc_id=doc.id,
                    pipeline_nodes=pipeline_nodes,
                    embedding_nodes=embedding_nodes,
                    target_models=target_models
                )
                
                # Update document with aggregate status
                await session.execute(
                    update(RAGDocument)
                    .where(RAGDocument.id == doc.id)
                    .values(
                        agg_status=agg_status,
                        agg_details_json=agg_details
                    )
                )
                
                migrated_count += 1
                print(f"  ✓ Migrated to {agg_status}")
                
            except Exception as e:
                error_count += 1
                print(f"  ✗ Error migrating {doc.id}: {e}")
                continue
        
        # Commit all changes
        await session.commit()
        
        print(f"\nMigration completed:")
        print(f"  Successfully migrated: {migrated_count}")
        print(f"  Errors: {error_count}")
        print(f"  Total documents: {len(documents)}")
    
    await engine.dispose()


async def verify_migration():
    """Verify that migration was successful"""
    settings = get_settings()
    
    engine = create_async_engine(
        settings.ASYNC_DB_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    async with session_factory() as session:
        # Count documents with new aggregate status
        result = await session.execute(
            select(RAGDocument).where(RAGDocument.agg_status.isnot(None))
        )
        migrated_docs = result.scalars().all()
        
        # Count status nodes
        result = await session.execute(select(RAGStatus))
        status_nodes = result.scalars().all()
        
        print(f"\nVerification:")
        print(f"  Documents with aggregate status: {len(migrated_docs)}")
        print(f"  Status nodes created: {len(status_nodes)}")
        
        # Show status distribution
        status_counts = {}
        for doc in migrated_docs:
            status = doc.agg_status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"  Status distribution:")
        for status, count in status_counts.items():
            print(f"    {status}: {count}")
    
    await engine.dispose()


if __name__ == "__main__":
    print("RAG Status Migration Script")
    print("=" * 40)
    
    # Check if we should run verification only
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        asyncio.run(verify_migration())
    else:
        # Run migration
        print("Starting migration...")
        asyncio.run(migrate_statuses())
        
        # Run verification
        print("\nRunning verification...")
        asyncio.run(verify_migration())
