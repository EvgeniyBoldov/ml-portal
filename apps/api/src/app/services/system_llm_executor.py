"""
SystemLLMExecutor - executes triage, planner, and summary roles.

Handles structured input, prompt compilation, LLM execution, and contract validation.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Union, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.system_llm_trace_service import SystemLLMTraceService
from app.schemas.system_llm_roles import (
    TriageInput, TriageDecision,
    PlannerInput, PlannerPlan,
    SummaryInput
)
from app.core.exceptions import SystemLLMExecutorError
from app.core.logging import get_logger
from app.services.system_llm_executor_helpers import (
    normalize_planner_response,
    planner_plan_to_next_action,
    extract_result_summary,
    extract_json,
    validate_contract,
    validate_field,
    smart_triage_mapping,
)

logger = get_logger(__name__)


class SystemLLMExecutor:
    """Executor for system LLM roles (triage, planner, summary)."""
    
    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClientProtocol
    ):
        self.session = session
        self.llm_client = llm_client
        self.role_service = SystemLLMRoleService(session)
        self.trace_service = SystemLLMTraceService(session)
    
    async def execute_triage(
        self, 
        input_data: TriageInput,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> Tuple[TriageDecision, Optional[UUID]]:
        """Execute triage role to determine next action."""
        role_config = await self.role_service.get_role_config(SystemLLMRoleType.TRIAGE)
        
        # Compile structured input
        structured_input = {
            "user_message": input_data.user_message,
            "conversation_summary": input_data.conversation_summary,
            "session_state": input_data.session_state,
            "available_agents": input_data.available_agents,
            "policies": input_data.policies,
            "active_run": input_data.active_run,
        }
        
        # Execute with retry logic
        response, trace_id = await self._execute_with_retry(
            trace_type=SystemLLMRoleType.TRIAGE,
            role_config=role_config,
            structured_input=structured_input,
            contract_schema=TriageDecision.model_json_schema(),
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return TriageDecision.model_validate(response), trace_id
    
    async def execute_planner(
        self, 
        input_data: PlannerInput,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None
    ) -> Tuple[PlannerPlan, Optional[UUID]]:
        """Execute planner role to create execution plan."""
        role_config = await self.role_service.get_role_config(SystemLLMRoleType.PLANNER)
        
        # Compile structured input
        structured_input = {
            "goal": input_data.goal,
            "conversation_summary": input_data.conversation_summary,
            "session_state": input_data.session_state,
            "available_agents": input_data.available_agents,
            "available_operations": input_data.available_operations,
            "policies": input_data.policies,
        }
        if input_data.execution_outline:
            outline = input_data.execution_outline
            if hasattr(outline, "model_dump"):
                structured_input["execution_outline"] = outline.model_dump()
            elif isinstance(outline, dict):
                structured_input["execution_outline"] = outline
            else:
                structured_input["execution_outline"] = dict(outline)
        
        # Execute with retry logic
        response, trace_id = await self._execute_with_retry(
            trace_type=SystemLLMRoleType.PLANNER,
            role_config=role_config,
            structured_input=structured_input,
            contract_schema=PlannerPlan.model_json_schema(),
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_run_id=agent_run_id
        )
        
        # Normalize LLM response to match PlannerPlan schema
        response = self._normalize_planner_response(response)
        return PlannerPlan.model_validate(response), trace_id
    
    @staticmethod
    def _normalize_planner_response(response: dict) -> dict:
        return normalize_planner_response(response)
    
    async def execute_summary(
        self, 
        input_data: SummaryInput,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> Tuple[str, Optional[UUID]]:
        """Execute summary role to create conversation summary."""
        role_config = await self.role_service.get_role_config(SystemLLMRoleType.SUMMARY)
        
        # Compile structured input
        structured_input = {
            "previous_summary": input_data.previous_summary,
            "recent_messages": input_data.recent_messages,
            "current_user_message": input_data.current_user_message,
            "current_agent_response": input_data.current_agent_response,
            "execution_memory": input_data.execution_memory,
            "session_state": input_data.session_state,
        }
        
        # Execute with retry logic (summary returns plain text)
        response, trace_id = await self._execute_with_retry(
            trace_type=SystemLLMRoleType.SUMMARY,
            role_config=role_config,
            structured_input=structured_input,
            contract_schema=None,  # Plain text response
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return response, trace_id
    
    def _planner_plan_to_next_action(self, plan: 'PlannerPlan') -> 'NextAction':
        return planner_plan_to_next_action(plan)
    
    async def execute_planner_with_fallback(
        self, 
        input_data: 'PlannerInput',
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None
    ) -> 'NextAction':
        """Execute planner role and return NextAction for runtime compatibility."""
        try:
            plan, trace_id = await self.execute_planner(
                input_data, chat_id, tenant_id, user_id, agent_run_id
            )
            return self._planner_plan_to_next_action(plan)
        except Exception as e:
            from app.agents.contracts import (
                ActionType,
                NextAction,
                AskUserPayload,
                ActionMeta,
            )
            logger.error(f"Planner execution failed: {e}", exc_info=True)
            return NextAction(
                type=ActionType.ASK_USER,
                ask_user=AskUserPayload(
                    question="I encountered an error while planning. Could you please clarify what you'd like me to do?"
                ),
                meta=ActionMeta(why=f"Planner error: {str(e)}")
            )
    
    async def _execute_with_retry(
        self,
        trace_type: str,
        role_config: Dict[str, Any],
        structured_input: Dict[str, Any],
        contract_schema: Optional[Dict[str, Any]],
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None
    ) -> Tuple[Union[Dict[str, Any], str], Optional[UUID]]:
        """Execute LLM with retry logic and validation, creating trace records."""
        # Resolve model slug → provider_model_name
        from app.services.model_resolver import ModelResolver
        resolver = ModelResolver(self.session)
        resolved_model = await resolver.resolve(role_config.get('model'))
        role_config = {**role_config, 'model': resolved_model}
        
        max_retries = role_config.get('max_retries', 2)
        retry_backoff = role_config.get('retry_backoff', 'linear')
        
        trace_id: Optional[UUID] = None
        
        for attempt in range(max_retries + 1):
            start_time = time.time()
            
            try:
                # Prepare messages
                messages = [
                    {"role": "system", "content": role_config['prompt']},
                    {"role": "user", "content": json.dumps(structured_input, indent=2)}
                ]
                
                # Prepare LLM parameters
                params = {
                    "temperature": role_config.get('temperature', 0.3),
                    "max_tokens": role_config.get('max_tokens', 2000),
                }
                
                logger.info(f"Executing {role_config['role_type']} role, attempt {attempt + 1}")
                logger.debug(f"Role config: {role_config}")
                
                # Execute LLM call
                response = await self._llm_call(
                    messages=messages,
                    model=role_config.get('model'),
                    params=params,
                    timeout_s=role_config.get('timeout_s', 15)
                )
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                # response is always a string from _llm_call
                content = response
                
                # Validate response
                if contract_schema:
                    # JSON response expected
                    try:
                        import re
                        logger.debug(f"LLM raw content ({len(content)} chars): {content[:500]}")
                        
                        parsed_response = self._extract_json(content)
                        
                        logger.info(f"LLM parsed response: {parsed_response}")
                        
                        # Validate against schema
                        try:
                            self._validate_contract(parsed_response, contract_schema)
                            
                            # Create success trace
                            trace_id = await self.trace_service.create_trace_from_execution(
                                trace_type=trace_type,
                                role_config=role_config,
                                structured_input=structured_input,
                                messages=messages,
                                llm_response=content,
                                parsed_response=parsed_response,
                                validation_status="success",
                                start_time=start_time,
                                model=role_config.get('model'),
                                temperature=role_config.get('temperature', 0.3),
                                max_tokens=role_config.get('max_tokens', 2000),
                                attempt_number=attempt + 1,
                                total_attempts=max_retries + 1,
                                result_type=parsed_response.get("type"),
                                result_summary=self._extract_result_summary(parsed_response),
                                chat_id=chat_id,
                                tenant_id=tenant_id,
                                user_id=user_id,
                                agent_run_id=agent_run_id,
                            )
                            return parsed_response, trace_id
                            
                        except SystemLLMExecutorError as e:
                            # Smart fallback: map common LLM responses to expected schema
                            role_type = role_config['role_type']
                            logger.warning(f"{role_type.title()} validation failed, applying smart fallback: {e}")
                            
                            fallback_applied = False
                            fallback_details = None
                            
                            if role_type == SystemLLMRoleType.TRIAGE:
                                fallback_response = self._smart_triage_mapping(parsed_response)
                                self._validate_contract(fallback_response, contract_schema)
                                fallback_applied = True
                                fallback_details = {"original_response": parsed_response, "error": str(e)}
                                
                                # Create fallback trace
                                trace_id = await self.trace_service.create_trace_from_execution(
                                    trace_type=trace_type,
                                    role_config=role_config,
                                    structured_input=structured_input,
                                    messages=messages,
                                    llm_response=content,
                                    parsed_response=fallback_response,
                                    validation_status="fallback_applied",
                                    start_time=start_time,
                                    model=role_config.get('model'),
                                    temperature=role_config.get('temperature', 0.3),
                                    max_tokens=role_config.get('max_tokens', 2000),
                                    attempt_number=attempt + 1,
                                    total_attempts=max_retries + 1,
                                    validation_error=str(e),
                                    fallback_applied=True,
                                    fallback_details=fallback_details,
                                    result_type=fallback_response.get("type"),
                                    result_summary=self._extract_result_summary(fallback_response),
                                    chat_id=chat_id,
                                    tenant_id=tenant_id,
                                    user_id=user_id,
                                    agent_run_id=agent_run_id,
                                )
                                
                                return fallback_response, trace_id
                            else:
                                # For planner and summary, no smart fallback available
                                # Create failed trace
                                trace_id = await self.trace_service.create_trace_from_execution(
                                    trace_type=trace_type,
                                    role_config=role_config,
                                    structured_input=structured_input,
                                    messages=messages,
                                    llm_response=content,
                                    parsed_response=parsed_response,
                                    validation_status="failed",
                                    start_time=start_time,
                                    model=role_config.get('model'),
                                    temperature=role_config.get('temperature', 0.3),
                                    max_tokens=role_config.get('max_tokens', 2000),
                                    attempt_number=attempt + 1,
                                    total_attempts=max_retries + 1,
                                    validation_error=str(e),
                                    chat_id=chat_id,
                                    tenant_id=tenant_id,
                                    user_id=user_id,
                                    agent_run_id=agent_run_id,
                                    error=str(e),
                                )
                                
                                raise e
                                
                    except (json.JSONDecodeError, TypeError) as e:
                        # Create failed trace for JSON decode error
                        trace_id = await self.trace_service.create_trace_from_execution(
                            trace_type=trace_type,
                            role_config=role_config,
                            structured_input=structured_input,
                            messages=messages,
                            llm_response=content,
                            parsed_response=None,
                            validation_status="failed",
                            start_time=start_time,
                            model=role_config.get('model'),
                            temperature=role_config.get('temperature', 0.3),
                            max_tokens=role_config.get('max_tokens', 2000),
                            attempt_number=attempt + 1,
                            total_attempts=max_retries + 1,
                            validation_error=str(e),
                            chat_id=chat_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            agent_run_id=agent_run_id,
                            error=str(e),
                        )
                        
                        raise SystemLLMExecutorError(f"Invalid JSON response: {e}")
                        
                else:
                    # Plain text response expected
                    content = content.strip()
                    
                    # Create success trace for plain text
                    trace_id = await self.trace_service.create_trace_from_execution(
                        trace_type=trace_type,
                        role_config=role_config,
                        structured_input=structured_input,
                        messages=messages,
                        llm_response=content,
                        parsed_response=None,
                        validation_status="success",
                        start_time=start_time,
                        model=role_config.get('model'),
                        temperature=role_config.get('temperature', 0.3),
                        max_tokens=role_config.get('max_tokens', 2000),
                        attempt_number=attempt + 1,
                        total_attempts=max_retries + 1,
                        result_type="text",
                        result_summary=content[:100] + ("..." if len(content) > 100 else ""),
                        chat_id=chat_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        agent_run_id=agent_run_id,
                    )
                    
                    return content, trace_id
                
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"Attempt {attempt + 1} failed for {role_config['role_type']}: {e}")
                
                # Create failed trace for attempt error
                try:
                    await self.trace_service.create_trace_from_execution(
                        trace_type=trace_type,
                        role_config=role_config,
                        structured_input=structured_input,
                        messages=[],  # Messages might not be ready if error happened early
                        llm_response="",
                        parsed_response=None,
                        validation_status="failed",
                        start_time=start_time,
                        model=role_config.get('model'),
                        temperature=role_config.get('temperature', 0.3),
                        max_tokens=role_config.get('max_tokens', 2000),
                        attempt_number=attempt + 1,
                        total_attempts=max_retries + 1,
                        chat_id=chat_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        agent_run_id=agent_run_id,
                        error=str(e),
                    )
                except Exception as trace_error:
                    logger.error(f"Failed to create trace for failed attempt: {trace_error}")
                
                if attempt == max_retries:
                    raise SystemLLMExecutorError(
                        f"Failed to execute {role_config['role_type']} after {max_retries + 1} attempts: {e}"
                    )
                
                # Calculate backoff delay
                if retry_backoff == 'linear':
                    delay = (attempt + 1) * 2  # 2s, 4s, 6s...
                elif retry_backoff == 'exp':
                    delay = 2 ** attempt  # 1s, 2s, 4s...
                else:  # none
                    delay = 0
                
                if delay > 0:
                    await asyncio.sleep(delay)
        
        # Should not reach here
        raise SystemLLMExecutorError(f"Unexpected error in {role_config['role_type']} execution")
    
    def _extract_result_summary(self, response: Dict[str, Any]) -> str:
        return extract_result_summary(response)
    
    async def _llm_call(
        self,
        messages: list[Dict[str, str]],
        model: Optional[str],
        params: Dict[str, Any],
        timeout_s: int
    ) -> str:
        """Execute LLM call with timeout. Returns content string."""
        import asyncio
        
        try:
            response = await asyncio.wait_for(
                self.llm_client.chat(
                    messages=messages,
                    model=model,
                    params=params
                ),
                timeout=timeout_s
            )
            
            logger.info(f"_llm_call raw response type={type(response).__name__}, keys={list(response.keys()) if isinstance(response, dict) else 'N/A'}")
            
            # Extract content from OpenAI-compatible response
            if isinstance(response, dict):
                # Standard OpenAI format: {"choices": [{"message": {"content": "..."}}]}
                choices = response.get("choices", [])
                if choices and isinstance(choices, list):
                    content = choices[0].get("message", {}).get("content", "")
                    if content:
                        return content
                # Fallback: direct content field
                if "content" in response:
                    return response["content"]
                # Last resort: serialize dict
                return json.dumps(response)
            
            return str(response)
                
        except asyncio.TimeoutError:
            raise SystemLLMExecutorError(f"LLM call timed out after {timeout_s}s")
        except SystemLLMExecutorError:
            raise
        except Exception as e:
            raise SystemLLMExecutorError(f"LLM call failed: {e}")
    
    @staticmethod
    def _extract_json(content: str) -> Dict[str, Any]:
        return extract_json(content)

    def _validate_contract(self, response: Dict[str, Any], schema: Dict[str, Any]) -> None:
        try:
            validate_contract(response, schema)
        except Exception as e:
            raise SystemLLMExecutorError(f"Contract validation failed: {e}")
    
    def _validate_field(self, field: str, value: Any, schema: Dict[str, Any]) -> None:
        validate_field(field, value, schema)
    
    async def ensure_default_roles(self) -> None:
        """Ensure default roles exist in the database."""
        await self.role_service.ensure_default_roles()
        logger.info("Default system LLM roles ensured")

    def _smart_triage_mapping(self, response: Dict[str, Any]) -> Dict[str, Any]:
        return smart_triage_mapping(response)
    
    
