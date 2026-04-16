"""
Repository for Plan model operations.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, desc

from app.models.plan import Plan, PlanStatus


class PlanRepository:
    """Repository for Plan operations."""
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
    
    async def create(self, plan: Plan) -> Plan:
        """Create a new plan."""
        self.session.add(plan)
        await self.session.flush()
        return plan
    
    async def get_by_id(self, plan_id: UUID) -> Optional[Plan]:
        """Get plan by ID."""
        result = await self.session.execute(
            select(Plan).where(Plan.id == plan_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_chat_id(self, chat_id: UUID, status: Optional[PlanStatus] = None) -> List[Plan]:
        """Get plans for chat, optionally filtered by status."""
        query = select(Plan).where(Plan.chat_id == chat_id)
        
        if status:
            query = query.where(Plan.status == status.value)
        
        query = query.order_by(desc(Plan.created_at))
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_agent_run_id(self, agent_run_id: UUID) -> Optional[Plan]:
        """Get plan for agent run."""
        result = await self.session.execute(
            select(Plan).where(Plan.agent_run_id == agent_run_id)
        )
        return result.scalar_one_or_none()
    
    async def get_active_plan(self, chat_id: UUID) -> Optional[Plan]:
        """Get currently active plan for chat."""
        result = await self.session.execute(
            select(Plan).where(
                and_(
                    Plan.chat_id == chat_id,
                    Plan.status == PlanStatus.ACTIVE.value
                )
            ).order_by(desc(Plan.created_at))
        )
        return result.scalar_one_or_none()
    
    async def get_paused_plan(self, chat_id: UUID) -> Optional[Plan]:
        """Get paused plan for chat for resume."""
        result = await self.session.execute(
            select(Plan).where(
                and_(
                    Plan.chat_id == chat_id,
                    Plan.status == PlanStatus.PAUSED.value
                )
            ).order_by(desc(Plan.created_at))
        )
        return result.scalar_one_or_none()
    
    async def update(self, plan: Plan) -> Plan:
        """Update plan."""
        self.session.add(plan)
        await self.session.flush()
        return plan
    
    async def update_status(self, plan_id: UUID, status: PlanStatus, current_step: Optional[int] = None) -> Optional[Plan]:
        """Update plan status and optionally current step."""
        stmt = update(Plan).where(Plan.id == plan_id).values(status=status.value)
        
        if current_step is not None:
            stmt = stmt.values(current_step=current_step)
        
        stmt = stmt.returning(Plan)
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def increment_step(self, plan_id: UUID) -> Optional[Plan]:
        """Increment current step for plan."""
        result = await self.session.execute(
            update(Plan)
            .where(Plan.id == plan_id)
            .values(current_step=Plan.current_step + 1)
            .returning(Plan)
        )
        return result.scalar_one_or_none()
    
    async def delete(self, plan_id: UUID) -> bool:
        """Delete plan by ID."""
        result = await self.session.execute(
            delete(Plan).where(Plan.id == plan_id)
        )
        return result.rowcount > 0
    
    async def list_by_status(self, status: PlanStatus, limit: int = 50) -> List[Plan]:
        """List plans by status."""
        result = await self.session.execute(
            select(Plan)
            .where(Plan.status == status.value)
            .order_by(desc(Plan.created_at))
            .limit(limit)
        )
        return result.scalars().all()
    
    async def cleanup_old_plans(self, chat_id: UUID, keep_count: int = 5) -> int:
        """Clean up old completed/failed plans, keeping only the most recent ones."""
        # Get completed/failed plans ordered by creation date
        result = await self.session.execute(
            select(Plan.id)
            .where(
                and_(
                    Plan.chat_id == chat_id,
                    Plan.status.in_([PlanStatus.COMPLETED.value, PlanStatus.FAILED.value])
                )
            )
            .order_by(desc(Plan.created_at))
            .offset(keep_count)
        )
        old_plan_ids = [row[0] for row in result.all()]
        
        if old_plan_ids:
            await self.session.execute(
                delete(Plan).where(Plan.id.in_(old_plan_ids))
            )
        
        return len(old_plan_ids)
    
    async def get_chat_plans(
        self, 
        chat_id: UUID, 
        tenant_id: UUID,
        status: Optional[PlanStatus] = None
    ) -> List[Plan]:
        """Get all plans for a chat."""
        query = select(Plan).where(
            and_(
                Plan.chat_id == chat_id,
                Plan.tenant_id == tenant_id
            )
        )
        
        if status:
            query = query.where(Plan.status == status.value)
        
        query = query.order_by(desc(Plan.created_at))
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_run_plans(
        self, 
        run_id: UUID, 
        tenant_id: UUID,
        status: Optional[PlanStatus] = None
    ) -> List[Plan]:
        """Get all plans for an agent run."""
        query = select(Plan).where(
            and_(
                Plan.agent_run_id == run_id,
                Plan.tenant_id == tenant_id
            )
        )
        
        if status:
            query = query.where(Plan.status == status.value)
        
        query = query.order_by(desc(Plan.created_at))
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def update(self, plan_id: UUID, update_data: Dict[str, Any]) -> Plan:
        """Update plan fields."""
        result = await self.session.execute(
            update(Plan)
            .where(Plan.id == plan_id)
            .values(**update_data)
            .returning(Plan)
        )
        await self.session.flush()
        
        updated_plan = result.scalar_one_or_none()
        if not updated_plan:
            raise ValueError(f"Plan {plan_id} not found")
        
        return updated_plan
