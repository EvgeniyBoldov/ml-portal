from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.prompt import Prompt
from app.repositories.agent_repository import AgentRepository
from app.repositories.prompt_repository import PromptRepository
from app.schemas.agents import AgentCreate, AgentUpdate


@dataclass
class AgentProfile:
    """Resolved agent profile with prompt template"""
    agent: Agent
    system_prompt: Prompt
    tools: List[str]
    generation_config: Dict[str, Any]


class AgentService:
    """Service for agent operations and profile resolution"""
    
    # Default agent slugs
    DEFAULT_AGENT = "chat-simple"
    RAG_AGENT = "chat-rag"
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentRepository(session)
        self.prompt_repo = PromptRepository(session)

    async def list_agents(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[Agent], int]:
        return await self.repo.list_agents(skip, limit)

    async def get_agent(self, identifier: str) -> Agent:
        """Get agent by ID or slug"""
        agent = None
        try:
            # Try as UUID
            uuid_obj = UUID(identifier)
            agent = await self.repo.get_by_id(uuid_obj)
        except ValueError:
            pass
            
        if not agent:
            # Try as slug
            agent = await self.repo.get_by_slug(identifier)
            
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{identifier}' not found")
            
        return agent

    async def create_agent(self, data: AgentCreate) -> Agent:
        # Check slug uniqueness
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise HTTPException(status_code=400, detail=f"Agent with slug '{data.slug}' already exists")
            
        agent = Agent(**data.model_dump())
        return await self.repo.create(agent)

    async def update_agent(self, identifier: str, data: AgentUpdate) -> Agent:
        agent = await self.get_agent(identifier)
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)
            
        return await self.repo.update(agent)

    async def delete_agent(self, identifier: str) -> None:
        agent = await self.get_agent(identifier)
        await self.repo.delete(agent)

    async def get_agent_profile(
        self, 
        agent_slug: Optional[str] = None,
        use_rag: bool = False
    ) -> AgentProfile:
        """
        Load full agent profile with resolved system prompt.
        
        Args:
            agent_slug: Agent slug to load. If None, uses default based on use_rag.
            use_rag: If True and agent_slug is None, uses RAG agent.
            
        Returns:
            AgentProfile with agent, prompt, tools, and config.
        """
        # Determine which agent to use
        if agent_slug is None:
            agent_slug = self.RAG_AGENT if use_rag else self.DEFAULT_AGENT
        
        # Load agent
        agent = await self.repo.get_by_slug(agent_slug)
        if not agent:
            # Fallback to default if requested agent not found
            agent = await self.repo.get_by_slug(self.DEFAULT_AGENT)
            if not agent:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Default agent '{self.DEFAULT_AGENT}' not found. Run migrations."
                )
        
        # Load system prompt
        system_prompt = await self.prompt_repo.get_by_slug(agent.system_prompt_slug)
        if not system_prompt:
            raise HTTPException(
                status_code=500,
                detail=f"System prompt '{agent.system_prompt_slug}' not found for agent '{agent.slug}'"
            )
        
        return AgentProfile(
            agent=agent,
            system_prompt=system_prompt,
            tools=agent.tools or [],
            generation_config=agent.generation_config or {}
        )

    async def resolve_agent_for_chat(
        self,
        agent_slug: Optional[str] = None,
        use_rag: bool = False
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Convenience method for ChatStreamService.
        
        Returns:
            Tuple of (system_prompt_template, prompt_slug, generation_config)
        """
        profile = await self.get_agent_profile(agent_slug, use_rag)
        return (
            profile.system_prompt.template,
            profile.system_prompt.slug,
            profile.generation_config
        )

    async def get_generated_prompt(self, identifier: str) -> Dict[str, Any]:
        """
        Generate the final system prompt for an agent.
        Shows how the prompt is composed from base prompt + tools instructions.
        
        Returns:
            Dict with base_prompt, tools_section, collections_section, and final_prompt
        """
        from app.agents.registry import ToolRegistry
        
        agent = await self.get_agent(identifier)
        
        # Load system prompt
        system_prompt = await self.prompt_repo.get_by_slug(agent.system_prompt_slug)
        if not system_prompt:
            raise HTTPException(
                status_code=500,
                detail=f"System prompt '{agent.system_prompt_slug}' not found"
            )
        
        base_prompt = system_prompt.template
        
        # Build tools section
        tools_section = ""
        if agent.tools:
            tools_section = "\n\n# Available Tools\n\n"
            tools_section += "You have access to the following tools:\n\n"
            
            for tool_slug in agent.tools:
                handler = ToolRegistry.get(tool_slug)
                if handler:
                    tools_section += f"## {handler.name} ({tool_slug})\n"
                    tools_section += f"{handler.description}\n\n"
                    tools_section += f"Input Schema:\n```json\n{handler.input_schema}\n```\n\n"
                else:
                    tools_section += f"## {tool_slug}\n"
                    tools_section += f"Tool not found in registry\n\n"
        
        # Build collections section
        collections_section = ""
        if agent.available_collections and "collection.search" in agent.tools:
            collections_section = "\n\n# Available Collections\n\n"
            collections_section += "You can search in the following collections:\n"
            for coll_slug in agent.available_collections:
                collections_section += f"- {coll_slug}\n"
        
        # Compose final prompt
        final_prompt = base_prompt
        if tools_section:
            final_prompt += tools_section
        if collections_section:
            final_prompt += collections_section
        
        return {
            "agent_slug": agent.slug,
            "agent_name": agent.name,
            "base_prompt": base_prompt,
            "base_prompt_slug": system_prompt.slug,
            "tools_section": tools_section if tools_section else None,
            "collections_section": collections_section if collections_section else None,
            "final_prompt": final_prompt,
            "tools": agent.tools,
            "available_collections": agent.available_collections,
        }
