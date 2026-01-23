"""
RoutingLog Repository
"""
from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.routing_log import RoutingLog


class RoutingLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, log: RoutingLog) -> RoutingLog:
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def get_by_id(self, log_id: UUID) -> Optional[RoutingLog]:
        stmt = select(RoutingLog).where(RoutingLog.id == log_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_run_id(self, run_id: UUID) -> Optional[RoutingLog]:
        stmt = select(RoutingLog).where(RoutingLog.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_logs(
        self,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Tuple[List[RoutingLog], int]:
        """List routing logs with filters"""
        stmt = select(RoutingLog)
        
        conditions = []
        if user_id:
            conditions.append(RoutingLog.user_id == user_id)
        if tenant_id:
            conditions.append(RoutingLog.tenant_id == tenant_id)
        if agent_slug:
            conditions.append(RoutingLog.selected_agent_slug == agent_slug)
        if status:
            conditions.append(RoutingLog.status == status)
        if since:
            conditions.append(RoutingLog.routed_at >= since)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.session.scalar(count_stmt) or 0
        
        stmt = stmt.order_by(RoutingLog.routed_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def delete_older_than(self, days: int) -> int:
        """Delete logs older than specified days. Returns count of deleted rows."""
        from sqlalchemy import delete
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = delete(RoutingLog).where(RoutingLog.routed_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_stats(
        self,
        tenant_id: Optional[UUID] = None,
        since: Optional[datetime] = None,
    ) -> dict:
        """Get routing statistics"""
        conditions = []
        if tenant_id:
            conditions.append(RoutingLog.tenant_id == tenant_id)
        if since:
            conditions.append(RoutingLog.routed_at >= since)
        
        base_stmt = select(RoutingLog)
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))
        
        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = await self.session.scalar(total_stmt) or 0
        
        success_stmt = select(func.count()).where(
            and_(
                RoutingLog.status == "success",
                *conditions
            )
        )
        success = await self.session.scalar(success_stmt) or 0
        
        avg_duration_stmt = select(func.avg(RoutingLog.routing_duration_ms)).where(
            and_(*conditions) if conditions else True
        )
        avg_duration = await self.session.scalar(avg_duration_stmt)
        
        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "success_rate": (success / total * 100) if total > 0 else 0,
            "avg_duration_ms": round(avg_duration, 2) if avg_duration else None,
        }
