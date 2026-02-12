"""
AgentSeedService — ensures default agents exist at startup.

Creates:
- assistant: universal agent with system.router (auto-routes to all tools)
- rag-search: specialized RAG knowledge base search agent
- data-analyst: specialized collection search/aggregate agent
"""
from __future__ import annotations
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.agent_version import AgentVersion, AgentVersionStatus
from app.models.agent_binding import AgentBinding, CredentialStrategy
from app.models.tool import Tool

logger = get_logger(__name__)


ASSISTANT_PROMPT = """You are a helpful AI assistant with access to various tools.

When the user asks a question, use the Tool Router to automatically find the best tools and data sources to answer it. The Tool Router will analyze the query and call appropriate tools (knowledge base search, collection search, aggregation, etc.).

Guidelines:
- Always use the Tool Router for questions that require data lookup or search
- For general conversation, respond directly without tools
- Cite sources when providing information from tools
- If a tool returns no results, let the user know and suggest alternatives
- Be concise and accurate in your responses
- Respond in the same language as the user's query"""

RAG_SEARCH_PROMPT = """You are a knowledge base search assistant.

Your primary function is to search the company knowledge base (RAG) to find relevant documents, policies, guides, and other stored knowledge.

Guidelines:
- Use the rag.search tool to find relevant information
- Always cite the source documents in your response
- If no results are found, suggest the user rephrase their query
- Summarize findings clearly and concisely
- Respond in the same language as the user's query"""

DATA_ANALYST_PROMPT = """You are a data analyst assistant.

Your primary function is to search, filter, and aggregate data from collections (structured data tables).

Available operations:
- collection.search: Search and filter records with DSL conditions
- collection.get: Get a specific record by ID
- collection.aggregate: Calculate statistics (count, sum, avg, min, max) with grouping

Guidelines:
- Ask clarifying questions if the collection or filters are unclear
- Use appropriate tool based on the request (search vs aggregate)
- Present data in a clear, structured format
- Respond in the same language as the user's query"""


SEED_AGENTS = [
    {
        "slug": "assistant",
        "name": "Universal Assistant",
        "description": "Universal AI assistant with automatic tool routing. Routes queries to the best available tools.",
        "prompt": ASSISTANT_PROMPT,
        "tools": ["system.router"],
    },
    {
        "slug": "rag-search",
        "name": "Knowledge Base Search",
        "description": "Specialized agent for searching the company knowledge base (RAG).",
        "prompt": RAG_SEARCH_PROMPT,
        "tools": ["rag.search"],
    },
    {
        "slug": "data-analyst",
        "name": "Data Analyst",
        "description": "Specialized agent for searching and analyzing data in collections.",
        "prompt": DATA_ANALYST_PROMPT,
        "tools": ["collection.search", "collection.get", "collection.aggregate"],
    },
]


class AgentSeedService:
    """Service for seeding default agents at startup."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def seed_all(self) -> dict:
        """Seed all default agents. Returns stats."""
        stats = {"created": 0, "skipped": 0, "errors": 0}

        for agent_def in SEED_AGENTS:
            try:
                created = await self._ensure_agent(agent_def)
                if created:
                    stats["created"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(f"Failed to seed agent '{agent_def['slug']}': {e}")
                stats["errors"] += 1

        return stats

    async def _ensure_agent(self, agent_def: dict) -> bool:
        """Ensure agent exists. Returns True if created, False if already exists."""
        slug = agent_def["slug"]

        # Check if agent already exists
        stmt = select(Agent).where(Agent.slug == slug)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.debug(f"Agent '{slug}' already exists, skipping")
            return False

        # Create agent container
        agent = Agent(
            slug=slug,
            name=agent_def["name"],
            description=agent_def["description"],
        )
        self.session.add(agent)
        await self.session.flush()

        # Create initial version (active)
        version = AgentVersion(
            agent_id=agent.id,
            version=1,
            status=AgentVersionStatus.ACTIVE.value,
            prompt=agent_def["prompt"],
            notes="Auto-seeded initial version",
        )
        self.session.add(version)
        await self.session.flush()

        # Set current_version_id
        agent.current_version_id = version.id
        await self.session.flush()

        # Create tool bindings
        for tool_slug in agent_def.get("tools", []):
            tool = await self._get_tool_by_slug(tool_slug)
            if tool:
                binding = AgentBinding(
                    agent_version_id=version.id,
                    tool_id=tool.id,
                    credential_strategy=CredentialStrategy.ANY.value,
                )
                self.session.add(binding)
            else:
                logger.warning(
                    f"Tool '{tool_slug}' not found for agent '{slug}'. "
                    f"Binding will be created when tool is synced."
                )

        await self.session.flush()
        logger.info(f"Seeded agent '{slug}' with {len(agent_def.get('tools', []))} tool bindings")
        return True

    async def _get_tool_by_slug(self, slug: str) -> Optional[Tool]:
        """Get tool by slug."""
        stmt = select(Tool).where(Tool.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
