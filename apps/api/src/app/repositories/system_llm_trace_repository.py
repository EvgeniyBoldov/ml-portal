"""
Repository for SystemLLMTrace operations.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_llm_trace import SystemLLMTrace, SystemLLMTraceType


class SystemLLMTraceRepository:
    """Repository for SystemLLMTrace data access."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, trace: SystemLLMTrace) -> SystemLLMTrace:
        """Create a new trace record."""
        self.session.add(trace)
        await self.session.flush()
        return trace
    
    async def get_by_id(self, trace_id: uuid.UUID) -> Optional[SystemLLMTrace]:
        """Get a trace by ID."""
        result = await self.session.execute(
            select(SystemLLMTrace).where(SystemLLMTrace.id == trace_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_chat_id(
        self,
        chat_id: str,
        trace_type: Optional[str] = None,
        limit: int = 50
    ) -> List[SystemLLMTrace]:
        """Get traces for a specific chat."""
        stmt = select(SystemLLMTrace).where(SystemLLMTrace.chat_id == chat_id)
        
        if trace_type:
            stmt = stmt.where(SystemLLMTrace.trace_type == trace_type)
        
        stmt = stmt.order_by(SystemLLMTrace.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_recent_by_tenant_id(
        self,
        tenant_id: str,
        trace_type: Optional[str] = None,
        limit: int = 50
    ) -> List[SystemLLMTrace]:
        """Get recent traces for a tenant."""
        stmt = select(SystemLLMTrace).where(SystemLLMTrace.tenant_id == tenant_id)
        
        if trace_type:
            stmt = stmt.where(SystemLLMTrace.trace_type == trace_type)
        
        stmt = stmt.order_by(SystemLLMTrace.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_agent_run_id(
        self,
        agent_run_id: uuid.UUID,
        trace_type: Optional[str] = None
    ) -> List[SystemLLMTrace]:
        """Get traces for a specific agent run."""
        query = select(SystemLLMTrace).where(
            SystemLLMTrace.agent_run_id == agent_run_id
        )
        
        if trace_type:
            query = query.where(SystemLLMTrace.trace_type == trace_type)
        
        query = query.order_by(SystemLLMTrace.created_at)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        validation_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SystemLLMTrace]:
        """Get traces for a tenant with filters."""
        query = select(SystemLLMTrace).where(SystemLLMTrace.tenant_id == tenant_id)
        
        if trace_type:
            query = query.where(SystemLLMTrace.trace_type == trace_type)
        
        if validation_status:
            query = query.where(SystemLLMTrace.validation_status == validation_status)
        
        if from_date:
            query = query.where(SystemLLMTrace.created_at >= from_date)
        
        if to_date:
            query = query.where(SystemLLMTrace.created_at <= to_date)
        
        query = query.order_by(desc(SystemLLMTrace.created_at))
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        validation_status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> int:
        """Count traces for a tenant with filters."""
        from sqlalchemy import func
        
        query = select(func.count()).select_from(SystemLLMTrace).where(
            SystemLLMTrace.tenant_id == tenant_id
        )
        
        if trace_type:
            query = query.where(SystemLLMTrace.trace_type == trace_type)
        
        if validation_status:
            query = query.where(SystemLLMTrace.validation_status == validation_status)
        
        if from_date:
            query = query.where(SystemLLMTrace.created_at >= from_date)
        
        if to_date:
            query = query.where(SystemLLMTrace.created_at <= to_date)
        
        result = await self.session.execute(query)
        return result.scalar() or 0
    
    async def delete_by_id(self, trace_id: uuid.UUID) -> bool:
        """Delete a trace by ID."""
        result = await self.session.execute(
            delete(SystemLLMTrace).where(SystemLLMTrace.id == trace_id)
        )
        await self.session.flush()
        return result.rowcount > 0
    
    async def delete_older_than(self, before_date: datetime, tenant_id: Optional[uuid.UUID] = None) -> int:
        """Delete traces older than a given date. Returns count of deleted traces."""
        query = delete(SystemLLMTrace).where(SystemLLMTrace.created_at < before_date)
        
        if tenant_id:
            query = query.where(SystemLLMTrace.tenant_id == tenant_id)
        
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount
    
    async def get_traces_with_prompt_hash(
        self,
        prompt_hash: str,
        tenant_id: uuid.UUID,
        limit: int = 10
    ) -> List[SystemLLMTrace]:
        """Get traces with a specific compiled prompt hash."""
        result = await self.session.execute(
            select(SystemLLMTrace)
            .where(
                and_(
                    SystemLLMTrace.compiled_prompt_hash == prompt_hash,
                    SystemLLMTrace.tenant_id == tenant_id
                )
            )
            .order_by(desc(SystemLLMTrace.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_failed_traces(
        self,
        tenant_id: uuid.UUID,
        trace_type: Optional[str] = None,
        hours: int = 24
    ) -> List[SystemLLMTrace]:
        """Get failed traces from the last N hours."""
        from_date = datetime.now(timezone.utc) - datetime.timedelta(hours=hours)
        
        query = select(SystemLLMTrace).where(
            and_(
                SystemLLMTrace.tenant_id == tenant_id,
                SystemLLMTrace.created_at >= from_date,
                or_(
                    SystemLLMTrace.validation_status == "failed",
                    SystemLLMTrace.error.isnot(None)
                )
            )
        )
        
        if trace_type:
            query = query.where(SystemLLMTrace.trace_type == trace_type)
        
        query = query.order_by(desc(SystemLLMTrace.created_at))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_trace_statistics(
        self,
        tenant_id: uuid.UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get trace statistics for a tenant."""
        from sqlalchemy import func
        
        query = select(
            SystemLLMTrace.trace_type,
            SystemLLMTrace.validation_status,
            func.count(SystemLLMTrace.id).label('count'),
            func.avg(SystemLLMTrace.duration_ms).label('avg_duration_ms'),
            func.sum(SystemLLMTrace.tokens_in).label('total_tokens_in'),
            func.sum(SystemLLMTrace.tokens_out).label('total_tokens_out')
        ).where(SystemLLMTrace.tenant_id == tenant_id)
        
        if from_date:
            query = query.where(SystemLLMTrace.created_at >= from_date)
        
        if to_date:
            query = query.where(SystemLLMTrace.created_at <= to_date)
        
        query = query.group_by(
            SystemLLMTrace.trace_type,
            SystemLLMTrace.validation_status
        )
        
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        stats = {}
        for row in rows:
            key = f"{row.trace_type}_{row.validation_status}"
            stats[key] = {
                "count": row.count,
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                "total_tokens_in": row.total_tokens_in or 0,
                "total_tokens_out": row.total_tokens_out or 0
            }
        
        return stats
