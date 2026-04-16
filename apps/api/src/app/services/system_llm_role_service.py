"""
Service for SystemLLMRole business logic.
"""
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    SystemLLMRoleNotFoundError,
    SystemLLMRoleValidationError,
    AppError as SystemLLMRoleError,
)
from app.models.system_llm_role import SystemLLMRole, SystemLLMRoleType
from app.repositories.system_llm_role_repository import SystemLLMRoleRepository
from app.schemas.system_llm_roles import (
    SystemLLMRoleCreate, SystemLLMRoleUpdate,
    TriageRoleUpdate, PlannerRoleUpdate, SummaryRoleUpdate, MemoryRoleUpdate
)

logger = logging.getLogger(__name__)


class SystemLLMRoleService:
    """Service for SystemLLMRole business operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SystemLLMRoleRepository(session)
    
    async def create_role(self, data: SystemLLMRoleCreate) -> SystemLLMRole:
        """Create a new SystemLLMRole."""
        # Check if active role already exists for this type
        existing_active = await self.repo.get_active_role(data.role_type)
        if existing_active and data.is_active:
            # If creating an active role, deactivate existing one
            existing_active.is_active = False
        
        role = SystemLLMRole(**data.model_dump())
        return await self.repo.create(role)
    
    async def get_role(self, role_id: UUID) -> SystemLLMRole:
        """Get a role by ID."""
        role = await self.repo.get_by_id(role_id)
        if not role:
            raise SystemLLMRoleNotFoundError(f"Role {role_id} not found")
        return role
    
    async def get_active_role(self, role_type: SystemLLMRoleType) -> Optional[SystemLLMRole]:
        """Get the active role for the specified type."""
        return await self.repo.get_active_role(role_type)
    
    async def get_all_roles(self) -> List[SystemLLMRole]:
        """Get all roles."""
        return await self.repo.get_all_roles()
    
    async def get_roles_by_type(self, role_type: SystemLLMRoleType) -> List[SystemLLMRole]:
        """Get all roles of a specific type."""
        return await self.repo.get_roles_by_type(role_type)
    
    async def update_role(self, role_id: UUID, data: SystemLLMRoleUpdate) -> SystemLLMRole:
        """Update a role."""
        role = await self.get_role(role_id)
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(role, field, value)
        
        return await self.repo.update(role)
    
    async def _update_role_by_type(
        self,
        role_type: SystemLLMRoleType,
        data: TriageRoleUpdate,
    ) -> Optional[SystemLLMRole]:
        """Update the active role of the given type. Creates if not found."""
        role = await self.repo.get_active_role(role_type)
        if not role:
            role = SystemLLMRole(role_type=role_type, is_active=True)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(role, field):
                setattr(role, field, value)

        return await self.repo.update(role)

    async def update_triage_role(self, data: TriageRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Triage role."""
        return await self._update_role_by_type(SystemLLMRoleType.TRIAGE, data)

    async def update_planner_role(self, data: PlannerRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Planner role."""
        return await self._update_role_by_type(SystemLLMRoleType.PLANNER, data)

    async def update_summary_role(self, data: SummaryRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Summary role."""
        return await self._update_role_by_type(SystemLLMRoleType.SUMMARY, data)

    async def update_memory_role(self, data: MemoryRoleUpdate) -> Optional[SystemLLMRole]:
        """Update the active Memory role."""
        return await self._update_role_by_type(SystemLLMRoleType.MEMORY, data)
    
    async def delete_role(self, role_id: UUID) -> bool:
        """Delete a role."""
        return await self.repo.delete(role_id)
    
    async def activate_role(self, role_id: UUID) -> SystemLLMRole:
        """Activate a role and deactivate others of the same type."""
        role = await self.repo.activate_role(role_id)
        if not role:
            raise SystemLLMRoleNotFoundError(f"Role {role_id} not found")
        return role
    
    async def get_role_config(self, role_type: SystemLLMRoleType) -> Dict[str, Any]:
        """Get role configuration as a dictionary for execution."""
        role = await self.repo.get_active_role(role_type)
        if not role:
            raise SystemLLMRoleNotFoundError(f"No active {role_type} role found")
        
        config = {
            'id': str(role.id),
            'role_type': role.role_type,
            'prompt': role.compiled_prompt,
            'model': role.model,
            'temperature': role.temperature,
            'max_tokens': role.max_tokens,
            'timeout_s': role.timeout_s,
            'max_retries': role.max_retries,
            'retry_backoff': role.retry_backoff,
        }
        
        logger.info(f"Role config for {role_type}: model={config['model']}, temperature={config['temperature']}")
        return config
    
    async def ensure_default_roles(self) -> Dict[SystemLLMRoleType, SystemLLMRole]:
        """Ensure default roles exist and return them."""
        default_roles = {}
        
        for role_type in SystemLLMRoleType:
            role = await self.repo.get_active_role(role_type)
            if not role:
                # Create default role
                default_configs = self._get_default_configs()
                config = default_configs.get(role_type, {})
                
                role = SystemLLMRole(
                    role_type=role_type,
                    is_active=True,
                    **config
                )
                role = await self.repo.create(role)
                logger.info(f"Created default {role_type.value} role")
            
            default_roles[role_type] = role
        
        return default_roles
    
    def _get_default_configs(self) -> Dict[SystemLLMRoleType, Dict[str, Any]]:
        """Get default configurations for each role type."""
        return {
            SystemLLMRoleType.TRIAGE: {
                'identity': 'Ты триаж-агент корпоративного AI-портала. Твоя задача — выбрать правильный маршрут обработки запроса.',
                'mission': (
                    'Проанализируй запрос пользователя и контекст диалога, затем выбери одно из действий: '
                    'final (ответить сразу), clarify (уточнить недостающие данные) '
                    'или orchestrate (передать задачу в оркестрацию агентам).'
                ),
                'rules': (
                    'Правила:\n'
                    '1. type="final": простой вопрос, справка, small-talk — ответь в поле "answer".\n'
                    '2. type="clarify": не хватает ключевых данных — задай вопрос в "clarify_prompt".\n'
                    '3. type="orchestrate": нужен поиск в системах, анализ данных, сравнение или многошаговая работа — сформируй "goal" и при необходимости "inputs".\n'
                    '\n'
                    'Критичные подсказки маршрутизации:\n'
                    '- "процесс", "политика", "инструкция", "регламент", "безопасность", "восстановление" → orchestrate\n'
                    '- "тикет", "инцидент", "заявка", "коллекция", "статистика" → orchestrate\n'
                    '- "устройство", "сервер", "IP", "подсеть", "стойка", "NetBox" → orchestrate\n'
                    '- "сравни", "проверь соответствие", "покажи отличия" → orchestrate\n'
                    '- приветствие, small-talk, ответ на уточнение → final\n'
                    '\n'
                    'Никогда не используй значения type, отличные от final, clarify, orchestrate.'
                ),
                'safety': 'Не выбирай "final" для запросов, связанных с внутренними системами, изменениями конфигураций или операционными рисками.',
                'output_requirements': (
                    'Верни ТОЛЬКО валидный JSON (без markdown и без ```).\n'
                    '{\n'
                    '  "type": "final" | "clarify" | "orchestrate",\n'
                    '  "confidence": 0.0-1.0,\n'
                    '  "reason": "краткое объяснение выбора",\n'
                    '  "answer": "текст ответа (только если type=final)",\n'
                    '  "clarify_prompt": "вопрос пользователю (только если type=clarify)",\n'
                    '  "goal": "цель оркестрации (только если type=orchestrate)",\n'
                    '  "inputs": {}\n'
                    '}'
                ),
                'temperature': 0.3,
                'max_tokens': 1000,
                'timeout_s': 10,
                'max_retries': 2,
                'retry_backoff': 'linear',
            },
            SystemLLMRoleType.PLANNER: {
                'model': 'llm.llama.maverick',
                'identity': 'Ты planner-агент корпоративного AI-портала. Ты строишь короткий и выполнимый следующий шаг.',
                'mission': (
                    'Разбивай цель на последовательные действия. '
                    'Каждый рабочий шаг делегируй доступному агенту (kind="agent"). '
                    'Не вызывай инструменты напрямую: инструменты вызывает агент. '
                    'kind="llm" используй в основном для финального синтеза ответа.'
                ),
                'rules': (
                    'Правила:\n'
                    '1. Начинай с делегирования агенту (kind="agent"), если есть подходящий агент.\n'
                    '2. Если дан execution_outline, иди по фазам по порядку; не пропускай must_do=true.\n'
                    '3. Учитывай previous_observations в session_state; не повторяй уже выполненный полезный шаг.\n'
                    '4. Когда обязательные фазы закрыты или фактов достаточно, переходи к kind="llm" для финального ответа.\n'
                    '5. kind="ask_user" — только в крайнем случае, когда без уточнения нельзя двигаться дальше.\n'
                    '6. План должен быть минимальным: один следующий шаг на итерацию.\n'
                    '7. Верни только валидный JSON без markdown и без ```.'
                ),
                'safety': 'Для рискованных действий требуй подтверждение и избегай потенциально опасных операций без явной необходимости.',
                'output_requirements': (
                    'Верни только валидный JSON с полями "goal" и "steps". '
                    'Формат шага: {"step_id":"s1","title":"...","kind":"agent"|"ask_user"|"llm",'
                    '"ref":"<agent_slug>","input":{"query":"...","phase_id":"...","phase_title":"..."}}.'
                ),
                'temperature': 0.2,
                'max_tokens': 4096,
                'timeout_s': 60,
                'max_retries': 2,
                'retry_backoff': 'linear',
            },
            SystemLLMRoleType.SUMMARY: {
                'identity': 'Ты summary-агент корпоративного AI-портала.',
                'mission': 'Собирай краткое и точное резюме диалога и результата выполнения за текущий цикл.',
                'rules': (
                    'Выделяй главное: цель, сделанные шаги, полученные факты, ограничения и открытые вопросы. '
                    'Не добавляй неподтвержденных выводов.'
                ),
                'safety': 'Не включай чувствительные данные, токены, пароли, ключи и внутренние секреты.',
                'output_requirements': 'Верни связный краткий текст на русском языке без markdown-разметки.',
                'temperature': 0.1,
                'max_tokens': 1500,
                'timeout_s': 10,
                'max_retries': 2,
                'retry_backoff': 'linear',
            },
            SystemLLMRoleType.MEMORY: {
                'identity': 'Ты memory-агент корпоративного AI-портала.',
                'mission': 'Формируй и поддерживай рабочую память выполнения: факты, допущения, риски и незакрытые вопросы.',
                'rules': (
                    'Сохраняй только проверяемые факты и полезный контекст для следующих шагов. '
                    'Убирай шум, не дублируй уже известное, отмечай неопределенности явно.'
                ),
                'safety': 'Не сохраняй секреты, персональные данные и чувствительные артефакты в явном виде.',
                'output_requirements': (
                    'Верни JSON-объект с ключами facts, open_questions, risks, next_actions. '
                    'Каждое значение — массив коротких строк на русском.'
                ),
                'temperature': 0.1,
                'max_tokens': 1200,
                'timeout_s': 10,
                'max_retries': 2,
                'retry_backoff': 'linear',
            },
        }
