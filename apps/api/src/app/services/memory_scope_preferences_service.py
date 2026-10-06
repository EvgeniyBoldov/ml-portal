"""Validate explicit preferences and inherit them into a chat's execution focus."""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_scope import MemoryScope
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.repositories.users_repo import AsyncUsersRepository
from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
from app.schemas.memory_scope_preferences import MemoryScopePreferences
from app.services.chat_context_contracts import ScopePayload
from app.services.memory_scope_catalog import list_memory_scopes, resolve_memory_scopes


class MemoryScopePreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = AsyncUsersRepository(session)
        self.tenants = AsyncTenantsRepository(session)

    async def validate_keys(self, keys: list[str]) -> list[str]:
        validated = MemoryScopePreferences(memory_scope_keys=keys).memory_scope_keys
        rows = await resolve_memory_scopes(self.session, validated)
        if any(row.is_all or row.scope_type not in {"team", "project"} for row in rows):
            raise ValueError("Choose concrete team/project scopes; all is a memory search selector")
        # Preferences must fit the same branch bounds as the persisted chat focus.
        ScopePayload(
            team_keys=[row.key.removeprefix("team.") for row in rows if row.scope_type == "team"],
            project_keys=[row.key.removeprefix("project.") for row in rows if row.scope_type == "project"],
        )
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
    """Chat > user > tenant per branch, ignoring stale catalog identities."""
    by_key = {row.key: row for row in catalog if not row.is_all and row.scope_type in {"team", "project"}}
    focus = chat_context.get("focus") or chat_context.get("scope") or {}
    origins = focus.get("scope_origins") or {}
    chat_keys = list(dict.fromkeys([
        *focus.get("scope_keys", []),
        *(f"team.{key}" for key in focus.get("team_keys", [])),
        *(f"project.{key}" for key in focus.get("project_keys", [])),
    ]))
    selected: list[ScopeIdentity] = []
    for branch in ("team", "project"):
        candidates = [key for key in chat_keys if key in by_key and by_key[key].scope_type == branch
                      and origins.get(key) not in {"user_project_default", "user_default", "tenant_default"}]
        source = "chat_focus"
        if not candidates and not focus.get(f"suppress_{branch}_default"):
            for defaults, origin in ((user_keys, "user_default"), (tenant_keys, "tenant_default")):
                candidates = [key for key in defaults if key in by_key and by_key[key].scope_type == branch]
                if candidates:
                    source = origin
                    break
        selected.extend(ScopeIdentity(id=str(by_key[key].id), key=key, type=branch,
                                      name=by_key[key].name, source=source)
                        for key in dict.fromkeys(candidates))
    return EffectiveScopeContext(
        revision=int(focus.get("scope_revision") or 0), selected=selected,
        mentioned=[ScopeIdentity(id=str(by_key[key].id), key=key, type=by_key[key].scope_type,
                                name=by_key[key].name, source="chat_focus")
                   for key in focus.get("mentioned_scope_keys", []) if key in by_key],
        explicit_clear=bool(focus.get("suppress_project_default") and focus.get("suppress_team_default")) and not selected,
        ceiling_keys=[item.key for item in selected],
    )
