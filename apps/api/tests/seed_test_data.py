"""
Seed test data for integration tests
Creates tenants, users, models, agents, prompts, and tools
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session_factory
from app.models.user import User
from app.models.tenant import Tenant
from app.models.model_registry import Model, ModelType, ModelStatus
from app.models.agent import Agent
from app.models.prompt import Prompt
from app.models.tool import Tool
from app.core.security import hash_password


async def seed_tenants(session: AsyncSession) -> dict:
    """Create test tenants"""
    print("📦 Creating test tenants...")
    
    # Check if test tenant exists
    from sqlalchemy import select
    result = await session.execute(
        select(Tenant).where(Tenant.name == "Test Tenant")
    )
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        tenant = Tenant(
            name="Test Tenant",
            description="Tenant for integration tests",
            is_active=True,
            ocr=True,
            layout=False,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        print(f"  ✅ Created tenant: {tenant.name} (ID: {tenant.id})")
    else:
        print(f"  ℹ️  Tenant already exists: {tenant.name}")
    
    return {"test_tenant": tenant}


async def seed_users(session: AsyncSession, tenants: dict) -> dict:
    """Create test users with different roles"""
    print("👥 Creating test users...")
    
    test_tenant = tenants["test_tenant"]
    users = {}
    
    test_users = [
        {
            "login": "test_admin",
            "email": "test_admin@test.com",
            "password": "admin123",
            "role": "admin",
            "is_active": True,
        },
        {
            "login": "test_editor",
            "email": "test_editor@test.com",
            "password": "editor123",
            "role": "editor",
            "is_active": True,
        },
        {
            "login": "test_reader",
            "email": "test_reader@test.com",
            "password": "reader123",
            "role": "reader",
            "is_active": True,
        },
    ]
    
    from sqlalchemy import select
    for user_data in test_users:
        result = await session.execute(
            select(User).where(User.login == user_data["login"])
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                login=user_data["login"],
                email=user_data["email"],
                hashed_password=hash_password(user_data["password"]),
                role=user_data["role"],
                is_active=user_data["is_active"],
                tenant_id=test_tenant.id,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"  ✅ Created user: {user.login} ({user.role})")
        else:
            print(f"  ℹ️  User already exists: {user.login}")
        
        users[user_data["role"]] = user
    
    return users


async def seed_models(session: AsyncSession) -> dict:
    """Create test models"""
    print("🤖 Creating test models...")
    
    models = {}
    
    test_models = [
        {
            "alias": "test-llm-model",
            "type": ModelType.LLM_CHAT,
            "status": ModelStatus.AVAILABLE,
            "provider": "openai",
            "model_version": "gpt-3.5-turbo",
            "default_for_type": True,
            "is_system": True,
            "extra_config": {"max_tokens": 4096, "temperature": 0.7},
        },
        {
            "alias": "test-embedding-model",
            "type": ModelType.EMBEDDING,
            "status": ModelStatus.AVAILABLE,
            "provider": "sentence-transformers",
            "model_version": "all-MiniLM-L6-v2",
            "default_for_type": True,
            "is_system": True,
            "extra_config": {"vector_dim": 384},
        },
        {
            "alias": "test-reranker-model",
            "type": ModelType.RERANKER,
            "status": ModelStatus.AVAILABLE,
            "provider": "cross-encoder",
            "model_version": "ms-marco-MiniLM-L-6-v2",
            "default_for_type": True,
            "is_system": True,
            "extra_config": {},
        },
    ]
    
    from sqlalchemy import select
    for model_data in test_models:
        result = await session.execute(
            select(Model).where(Model.alias == model_data["alias"])
        )
        model = result.scalar_one_or_none()
        
        if not model:
            model = Model(**model_data)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            print(f"  ✅ Created model: {model.alias} ({model.type.value})")
        else:
            print(f"  ℹ️  Model already exists: {model.alias}")
        
        models[model_data["type"].value] = model
    
    return models


async def seed_prompts(session: AsyncSession) -> dict:
    """Create test prompts"""
    print("📝 Creating test prompts...")
    
    prompts = {}
    
    test_prompts = [
        {
            "slug": "test-system-prompt",
            "name": "Test System Prompt",
            "template": "You are a helpful AI assistant for testing purposes. Answer questions concisely.",
            "version": 1,
            "is_active": True,
            "input_variables": [],
        },
        {
            "slug": "test-rag-prompt",
            "name": "Test RAG Prompt",
            "template": "You are a helpful AI assistant. Use the following context to answer the question:\n\nContext: {{context}}\n\nQuestion: {{question}}",
            "version": 1,
            "is_active": True,
            "input_variables": ["context", "question"],
        },
    ]
    
    from sqlalchemy import select
    for prompt_data in test_prompts:
        result = await session.execute(
            select(Prompt).where(
                Prompt.slug == prompt_data["slug"],
                Prompt.version == prompt_data["version"]
            )
        )
        prompt = result.scalar_one_or_none()
        
        if not prompt:
            prompt = Prompt(**prompt_data)
            session.add(prompt)
            await session.commit()
            await session.refresh(prompt)
            print(f"  ✅ Created prompt: {prompt.slug} (v{prompt.version})")
        else:
            print(f"  ℹ️  Prompt already exists: {prompt.slug}")
        
        prompts[prompt_data["slug"]] = prompt
    
    return prompts


async def seed_tools(session: AsyncSession) -> dict:
    """Create test tools"""
    print("🔧 Creating test tools...")
    
    tools = {}
    
    test_tools = [
        {
            "slug": "rag.search",
            "name": "RAG Search",
            "description": "Search knowledge base for relevant documents",
            "is_active": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    ]
    
    from sqlalchemy import select
    for tool_data in test_tools:
        result = await session.execute(
            select(Tool).where(Tool.slug == tool_data["slug"])
        )
        tool = result.scalar_one_or_none()
        
        if not tool:
            tool = Tool(**tool_data)
            session.add(tool)
            await session.commit()
            await session.refresh(tool)
            print(f"  ✅ Created tool: {tool.slug}")
        else:
            print(f"  ℹ️  Tool already exists: {tool.slug}")
        
        tools[tool_data["slug"]] = tool
    
    return tools


async def seed_agents(session: AsyncSession, prompts: dict, tools: dict) -> dict:
    """Create test agents"""
    print("🤖 Creating test agents...")
    
    agents = {}
    
    test_agents = [
        {
            "slug": "test-chat-simple",
            "name": "Test Simple Chat",
            "description": "Simple chat agent for testing",
            "system_prompt_slug": "test-system-prompt",
            "tools": [],
            "is_active": True,
            "generation_config": {"temperature": 0.7, "max_tokens": 1000},
        },
        {
            "slug": "test-chat-rag",
            "name": "Test RAG Chat",
            "description": "RAG-enabled chat agent for testing",
            "system_prompt_slug": "test-rag-prompt",
            "tools": ["rag.search"],
            "is_active": True,
            "generation_config": {"temperature": 0.7, "max_tokens": 1500},
        },
    ]
    
    from sqlalchemy import select
    for agent_data in test_agents:
        result = await session.execute(
            select(Agent).where(Agent.slug == agent_data["slug"])
        )
        agent = result.scalar_one_or_none()
        
        if not agent:
            agent = Agent(**agent_data)
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
            print(f"  ✅ Created agent: {agent.slug}")
        else:
            print(f"  ℹ️  Agent already exists: {agent.slug}")
        
        agents[agent_data["slug"]] = agent
    
    return agents


async def seed_all():
    """Seed all test data"""
    print("\n🌱 Starting test data seeding...\n")
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            tenants = await seed_tenants(session)
            users = await seed_users(session, tenants)
            models = await seed_models(session)
            prompts = await seed_prompts(session)
            tools = await seed_tools(session)
            agents = await seed_agents(session, prompts, tools)
            
            print("\n✅ Test data seeding completed successfully!\n")
            print("Summary:")
            print(f"  - Tenants: {len(tenants)}")
            print(f"  - Users: {len(users)}")
            print(f"  - Models: {len(models)}")
            print(f"  - Prompts: {len(prompts)}")
            print(f"  - Tools: {len(tools)}")
            print(f"  - Agents: {len(agents)}")
            print()
            
            return {
                "tenants": tenants,
                "users": users,
                "models": models,
                "prompts": prompts,
                "tools": tools,
                "agents": agents,
            }
        except Exception as e:
            print(f"\n❌ Error seeding test data: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(seed_all())
