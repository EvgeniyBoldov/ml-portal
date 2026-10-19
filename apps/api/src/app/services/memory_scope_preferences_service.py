"""Validate explicit preferences and inherit them into a chat's execution focus."""
from typing import Annotated, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_scope import MemoryScope
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.repositories.users_repo import AsyncUsersRepository
from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
from pydantic import Field, TypeAdapter

from app.schemas.memory_scope_preferences import MemoryScopeKey
from app.services.memory_scope_catalog import list_memory_scopes, resolve_memory_scopes


class MemoryScopePreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = AsyncUsersRepository(session)
        self.tenants = AsyncTenantsRepository(session)

    async def validate_keys(self, keys: list[str], *, max_scopes: int = 60) -> list[str]:
        validated = TypeAdapter(Annotated[list[MemoryScopeKey], Field(max_length=max_scopes)]).validate_python(keys)
        rows = await resolve_memory_scopes(self.session, validated)
        if any(row.is_all for row in rows):
            raise ValueError("Choose concrete scope slugs")
        return list(dict.fromkeys(row.key for row in rows))

    async def update_user(self, user_id: UUID, keys: list[str]) -> list[str]:
        validated = await self.validate_keys(keys)
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        if user.lifecycle_status != "active":
            raise ValueError("deprecated")
        user.memory_scope_keys = validated
        await self.session.flush()
        return validated

    async def resolve_context(
        self, *, user_id: UUID, tenant_id: UUID | None, chat_context: dict[str, Any],
    ) -> EffectiveScopeContext:
        user = await self.users.get_by_id(user_id)
        tenant = await self.tenants.get_by_id(tenant_id) if tenant_id else None
        return inherit_scope_context(
            catalog=await list_memory_scopes(self.session), chat_context=chat_context,
            user_keys=list(user.memory_scope_keys or []) if user and user.lifecycle_status == "active" else [],
            tenant_keys=list(tenant.memory_scope_keys or []) if tenant and tenant.lifecycle_status == "active" else [],
        )


def inherit_scope_context(
    *, catalog: list[MemoryScope], chat_context: dict[str, Any], user_keys: list[str], tenant_keys: list[str],
) -> EffectiveScopeContext:
    """Union tenant and user defaults; a chat override replaces the entire set."""
    by_key = {row.key: row for row in catalog if not row.is_all}
    focus = chat_context.get("focus") or chat_context.get("scope") or {}
    origins = focus.get("scope_origins") or {}
    explicit = (focus.get("scope_mode") == "replace" or bool(focus.get("suppress_scope_default"))
                or bool(focus.get("suppress_project_default") and focus.get("suppress_team_default"))
                or any(origin in {"turn", "chat_focus"} for origin in origins.values()))
    if explicit:
        keys = list(dict.fromkeys(focus.get("scope_keys") or []))
        sources = {key: "chat_focus" for key in keys}
    else:
        keys = list(dict.fromkeys([*tenant_keys, *user_keys]))
        if not keys and "company" in by_key:
            keys = ["company"]
        sources = {key: "user_default" if key in user_keys else "tenant_default" for key in keys}
    selected = [ScopeIdentity(id=str(by_key[key].id), key=key, type="scope", name=by_key[key].name,
                              source=sources[key]) for key in keys if key in by_key]
    return EffectiveScopeContext(
        revision=int(focus.get("scope_revision") or 0), selected=selected,
        mentioned=[ScopeIdentity(id=str(by_key[key].id), key=key, type="scope",
                                name=by_key[key].name, source="chat_focus")
                   for key in focus.get("mentioned_scope_keys", []) if key in by_key],
        mode="replace" if explicit else "inherit", explicit_clear=explicit and not selected,
        ceiling_keys=[item.key for item in selected],
    )
