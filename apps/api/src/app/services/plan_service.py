"""
Service for managing execution plans with pause/resume functionality.
"""
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan, PlanStatus
from app.repositories.plan_repository import PlanRepository
from app.schemas.system_llm_roles import PlannerPlan
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlanService:
    """Service for plan operations."""
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PlanRepository(session)
    
    async def create_plan(
        self,
        plan_data: PlannerPlan,
        chat_id: Optional[uuid.UUID] = None,
        agent_run_id: Optional[uuid.UUID] = None,
        tenant_id: Optional[uuid.UUID] = None
    ) -> Plan:
        """Create a new plan."""
        plan = Plan(
            chat_id=chat_id,
            agent_run_id=agent_run_id,
            tenant_id=tenant_id or uuid.UUID('fb983a10-c5f8-4840-a9d3-856eea0dc729'),  # Default tenant
            plan_data=plan_data.model_dump(),
            status=PlanStatus.DRAFT.value,
            current_step=0
        )
        
        return await self.repo.create(plan)
    
    async def activate_plan(self, plan_id: uuid.UUID) -> Optional[Plan]:
        """Activate a plan for execution."""
        return await self.repo.update_status(plan_id, PlanStatus.ACTIVE)

    async def complete_plan(self, plan_id: uuid.UUID) -> Optional[Plan]:
        """Mark plan as completed."""
        return await self.repo.update_status(plan_id, PlanStatus.COMPLETED)

    async def fail_plan(self, plan_id: uuid.UUID) -> Optional[Plan]:
        """Mark plan as failed."""
        return await self.repo.update_status(plan_id, PlanStatus.FAILED)

    async def get_plan(self, plan_id: uuid.UUID) -> Optional[Plan]:
        """Get plan by ID."""
        return await self.repo.get_by_id(plan_id)

    async def increment_step(self, plan_id: uuid.UUID) -> Optional[Plan]:
        """Increment current step in plan."""
        return await self.repo.increment_step(plan_id)

    async def get_current_step(self, plan_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get current step data from plan."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return None
        return plan.current_step_data

    async def cleanup_old_plans(self, chat_id: uuid.UUID, keep_count: int = 5) -> int:
        """Clean up old completed/failed plans."""
        return await self.repo.cleanup_old_plans(chat_id, keep_count)

    async def get_plan_progress(self, plan_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get plan progress information."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return None
        
        return {
            "plan_id": str(plan.id),
            "status": plan.status,
            "current_step": plan.current_step,
            "total_steps": len(plan.steps),
            "progress_percentage": plan.progress_percentage,
            "current_step_data": plan.current_step_data,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat()
        }

    async def validate_plan_resume(self, plan_id: uuid.UUID) -> Optional[str]:
        """Validate if plan can be resumed."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            return "Plan not found"
        
        if plan.status != PlanStatus.PAUSED.value:
            return f"Plan cannot be resumed from status: {plan.status}"
        
        if plan.current_step >= len(plan.steps):
            return "Plan already completed"

        return None  # Can be resumed

    async def get_chat_plans(
        self, 
        chat_id: uuid.UUID, 
        tenant_id: str,
        status: Optional[PlanStatus] = None
    ) -> List[Plan]:
        """Get all plans for a chat."""
        return await self.repo.get_chat_plans(chat_id, uuid.UUID(tenant_id), status)
    
    async def get_run_plans(
        self, 
        run_id: uuid.UUID, 
        tenant_id: str,
        status: Optional[PlanStatus] = None
    ) -> List[Plan]:
        """Get all plans for an agent run."""
        return await self.repo.get_run_plans(run_id, uuid.UUID(tenant_id), status)
    
    async def update_plan_status(
        self, 
        plan_id: uuid.UUID, 
        status: PlanStatus,
        current_step: Optional[int] = None
    ) -> Plan:
        """Update plan status and optionally current step."""
        update_data = {"status": status}
        if current_step is not None:
            update_data["current_step"] = current_step

        return await self.repo.update(plan_id, update_data)

    async def resume_plan(self, plan_id: uuid.UUID) -> Plan:
        """Resume a paused plan."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found")

        if plan.status != PlanStatus.PAUSED.value:
            raise ValueError(f"Cannot resume plan with status {plan.status}")

        return await self.update_plan_status(plan_id, PlanStatus.ACTIVE)

    async def pause_plan(self, plan_id: uuid.UUID, current_step: Optional[int] = None) -> Plan:
        """Pause an active plan."""
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found")

        if plan.status != PlanStatus.ACTIVE.value:
            raise ValueError(f"Cannot pause plan with status {plan.status}")

        return await self.update_plan_status(plan_id, PlanStatus.PAUSED, current_step=current_step)
