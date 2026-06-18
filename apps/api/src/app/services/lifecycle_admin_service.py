from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import inspect

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.chat import Chats
from app.models.collection import Collection
from app.models.rbac import RbacRule
from app.models.sandbox import SandboxSession
from app.models.tenant import Tenants, UserTenants
from app.models.user import Users
from app.services.agent_service import AgentService
from app.services.chats_service import ChatsService
from app.services.collection_service import CollectionService
from app.services.rbac_cleanup_service import RbacCleanupService
from app.services.rbac_service import RbacService
from app.services.tenant_migration_service import TenantMigrationService
from app.services.tenants_service import AsyncTenantsService
from app.services.sandbox_service import SandboxService

LifecycleKind = Literal["tenant", "user", "collection", "agent", "rbac_rule"]


@dataclass
class DependencyEntry:
    @dataclass
    class DependencyEntity:
        uuid: str
        name: str
        url: str | None = None

    resource_type: str
    count: int
    action: str
    will_be: str = "cascade_deleted"
    entities: list[DependencyEntity] = field(default_factory=list)
    migration_target: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleReport:
    kind: LifecycleKind
    entity_id: str
    mode: Literal["soft", "hard", "restore"]
    lifecycle_status: str
    details: dict[str, Any]
    migrated: dict[str, int]
    cascaded: dict[str, int]
    set_null: dict[str, int]
    rbac_rules_removed: int
    renamed: list[dict[str, str]]


class LifecycleAdminService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dependencies(
        self,
        kind: LifecycleKind,
        entity_id: uuid.UUID,
        *,
        cascade: bool = False,
        full_entities: bool = False,
    ) -> list[dict[str, Any]]:
        direct = await self._get_direct_dependencies(kind, entity_id, full_entities=full_entities)
        if not cascade:
            return direct

        visited: set[tuple[str, str]] = {(kind, str(entity_id))}
        expanded = await self._expand_cascade_dependencies(direct, visited=visited, full_entities=full_entities)
        return direct + expanded

    async def _get_direct_dependencies(self, kind: LifecycleKind, entity_id: uuid.UUID, *, full_entities: bool = False) -> list[dict[str, Any]]:
        if kind == "tenant":
            return await self._tenant_dependencies(entity_id, full_entities=full_entities)
        if kind == "user":
            return await self._user_dependencies(entity_id, full_entities=full_entities)
        if kind == "collection":
            return await self._collection_dependencies(entity_id, full_entities=full_entities)
        if kind == "agent":
            return await self._agent_dependencies(entity_id, full_entities=full_entities)
        if kind == "rbac_rule":
            return []
        raise ValueError(f"Unsupported lifecycle kind: {kind}")

    async def _expand_cascade_dependencies(
        self,
        direct: list[dict[str, Any]],
        *,
        visited: set[tuple[str, str]],
        full_entities: bool = False,
    ) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        resource_kind_map: dict[str, LifecycleKind] = {
            "users": "user",
            "collections": "collection",
            "agents": "agent",
            "rbac_rules": "rbac_rule",
        }

        for dep in direct:
            resource_type = str(dep.get("resource_type") or "")
            child_kind = resource_kind_map.get(resource_type)
            if child_kind is None:
                continue
            entities = dep.get("entities") or []
            for entity in entities:
                entity_id = str(entity.get("uuid") or "")
                if not entity_id:
                    continue
                key = (child_kind, entity_id)
                if key in visited:
                    continue
                visited.add(key)
                try:
                    child_uuid = uuid.UUID(entity_id)
                except ValueError:
                    continue
                child_direct = await self._get_direct_dependencies(child_kind, child_uuid, full_entities=full_entities)
                for child_dep in child_direct:
                    details = dict(child_dep.get("details") or {})
                    details["cascade_parent"] = {
                        "kind": child_kind,
                        "id": entity_id,
                        "name": entity.get("name"),
                        "resource_type": resource_type,
                    }
                    child_dep["details"] = details
                    expanded.append(child_dep)
                nested = await self._expand_cascade_dependencies(child_direct, visited=visited, full_entities=full_entities)
                expanded.extend(nested)
        return expanded

    async def soft_delete(
        self,
        kind: LifecycleKind,
        entity_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None,
        reason: str | None,
        retention_days: int | None,
        cascade: bool = False,
    ) -> LifecycleReport:
        entity = await self._get_entity(kind, entity_id)
        if entity is None:
            raise ValueError("not_found")
        if kind == "tenant" and bool(getattr(entity, "is_platform_default", False)):
            raise ValueError("cannot_delete_default_tenant")

        entity.lifecycle_status = "deprecated"
        entity.deprecated_at = datetime.now(timezone.utc)
        entity.deprecated_by = actor_id
        entity.deprecated_reason = reason
        if retention_days is not None:
            entity.retention_days = retention_days

        if kind in {"tenant", "user", "collection"} and hasattr(entity, "is_active"):
            entity.is_active = False

        if kind == "collection":
            await self._remove_collection_from_agent_bindings(entity_id)

        return LifecycleReport(
            kind=kind,
            entity_id=str(entity_id),
            mode="soft",
            lifecycle_status="deprecated",
            details={"retention_days": entity.retention_days},
            migrated={},
            cascaded={},
            set_null={},
            rbac_rules_removed=0,
            renamed=[],
        )

    async def restore(self, kind: LifecycleKind, entity_id: uuid.UUID) -> LifecycleReport:
        entity = await self._get_entity(kind, entity_id)
        if entity is None:
            raise ValueError("not_found")

        entity.lifecycle_status = "active"
        entity.deprecated_at = None
        entity.deprecated_by = None
        entity.deprecated_reason = None

        if kind in {"tenant", "user", "collection"} and hasattr(entity, "is_active"):
            entity.is_active = True

        return LifecycleReport(
            kind=kind,
            entity_id=str(entity_id),
            mode="restore",
            lifecycle_status="active",
            details={},
            migrated={},
            cascaded={},
            set_null={},
            rbac_rules_removed=0,
            renamed=[],
        )

    async def hard_delete(self, kind: LifecycleKind, entity_id: uuid.UUID, *, cascade: bool = False) -> LifecycleReport:
        if kind == "tenant":
            entity = await self.session.get(Tenants, entity_id)
            if entity is None:
                raise ValueError("not_found")
            if getattr(entity, "is_platform_default", False):
                raise ValueError("cannot_delete_default_tenant")
            tenant_repo = AsyncTenantsService(self.session).repo
            default_tenant = await tenant_repo.get_platform_default()
            if not default_tenant:
                raise ValueError("platform_default_tenant_not_found")

            cascaded_counts: dict[str, int] = {}
            migrated_counts: dict[str, int] = {}
            renamed_collections: list[tuple[str, str]] = []

            if cascade:
                # Cascade delete: delete all users and their dependencies
                user_ids_result = await self.session.execute(
                    select(Users.id).join(UserTenants, UserTenants.user_id == Users.id)
                    .where(UserTenants.tenant_id == entity_id)
                )
                user_ids = [r for r in user_ids_result.scalars()]
                for user_id in user_ids:
                    try:
                        user_report = await self.hard_delete("user", user_id, cascade=True)
                        for resource, count in (user_report.cascaded or {}).items():
                            cascaded_counts[resource] = cascaded_counts.get(resource, 0) + count
                        cascaded_counts["users"] = cascaded_counts.get("users", 0) + 1
                    except ValueError:
                        # Skip users that can't be deleted (e.g., last admin)
                        pass

                # Delete collections directly (no migration)
                collection_ids_result = await self.session.execute(
                    select(Collection.id).where(Collection.tenant_id == entity_id)
                )
                collection_ids = [r for r in collection_ids_result.scalars()]
                collection_service = CollectionService(self.session)
                for coll_id in collection_ids:
                    try:
                        await collection_service.delete_collection(coll_id)
                        cascaded_counts["collections"] = cascaded_counts.get("collections", 0) + 1
                    except Exception:
                        pass
            else:
                # Non-cascade: migrate data to default tenant
                migration = TenantMigrationService(self.session)
                migration_report = await migration.migrate_tenant_data(
                    from_tenant_id=entity_id,
                    to_tenant_id=default_tenant.id,
                )
                migrated_counts = dict(migration_report.migrated or {})
                renamed_collections = migration_report.renamed_collections or []

            # Always delete sandbox sessions and RBAC rules for the tenant
            sandbox_ids = await self._sample_ids(
                select(SandboxSession.id).where(SandboxSession.tenant_id == entity_id),
                limit=10000,
            )
            sandbox_service = SandboxService(self.session)
            sandbox_deleted = 0
            for sandbox_id in sandbox_ids:
                if await sandbox_service.delete_session(uuid.UUID(sandbox_id)):
                    sandbox_deleted += 1
            if sandbox_deleted > 0:
                cascaded_counts["sandbox_sessions"] = cascaded_counts.get("sandbox_sessions", 0) + sandbox_deleted

            rbac_cleanup = RbacCleanupService(self.session)
            removed_rules = await rbac_cleanup.remove_rules_for_owner(owner_tenant_id=entity_id)

            # Delete tenant bindings
            await self.session.execute(
                UserTenants.__table__.delete().where(UserTenants.tenant_id == entity_id)
            )

            await self.session.delete(entity)
            await self.session.flush()

            return LifecycleReport(
                kind=kind,
                entity_id=str(entity_id),
                mode="hard",
                lifecycle_status="deleted",
                details={} if cascade else {"migrated_to_tenant_id": str(default_tenant.id)},
                migrated=migrated_counts,
                cascaded=cascaded_counts,
                set_null={},
                rbac_rules_removed=removed_rules,
                renamed=[{"old": old, "new": new} for (old, new) in renamed_collections],
            )

        if kind == "user":
            entity = await self.session.get(Users, entity_id)
            if entity is None:
                raise ValueError("not_found")
            await self._assert_user_not_last_active_admin(entity_id)
            chats_count = await self._count(select(func.count()).select_from(Chats).where(Chats.owner_id == entity_id))
            sandbox_count = await self._count(
                select(func.count()).select_from(SandboxSession).where(SandboxSession.owner_id == entity_id)
            )
            chats_service = ChatsService(self.session)
            chat_ids_result = await self.session.execute(select(Chats.id).where(Chats.owner_id == entity_id))
            scalar_result = chat_ids_result.scalars()
            if inspect.isawaitable(scalar_result):
                scalar_result = await scalar_result
            chat_ids = scalar_result.all()
            if inspect.isawaitable(chat_ids):
                chat_ids = await chat_ids
            for chat_id in chat_ids:
                await chats_service.delete_chat(chat_id=chat_id, owner_id=entity_id)
            rbac_cleanup = RbacCleanupService(self.session)
            removed_rules = await rbac_cleanup.remove_rules_for_owner(owner_user_id=entity_id)
            await self.session.delete(entity)
            await self.session.flush()
            return LifecycleReport(
                kind=kind,
                entity_id=str(entity_id),
                mode="hard",
                lifecycle_status="deleted",
                details={},
                migrated={},
                cascaded={"chats": chats_count, "sandbox_sessions": sandbox_count},
                set_null={},
                rbac_rules_removed=removed_rules,
                renamed=[],
            )

        if kind == "collection":
            collection = await self.session.get(Collection, entity_id)
            if collection is None:
                raise ValueError("not_found")
            await self._remove_collection_from_agent_bindings(entity_id)
            rbac_cleanup = RbacCleanupService(self.session)
            removed_rules = await rbac_cleanup.remove_rules_for_resource(
                resource_type="instance",
                resource_id=entity_id,
            )
            service = CollectionService(self.session)
            deleted = await service.delete_collection(collection.slug, drop_table=True)
            if not deleted:
                raise ValueError("not_found")
            return LifecycleReport(
                kind=kind,
                entity_id=str(entity_id),
                mode="hard",
                lifecycle_status="deleted",
                details={"table_dropped": True},
                migrated={},
                cascaded={},
                set_null={},
                rbac_rules_removed=removed_rules,
                renamed=[],
            )

        if kind == "agent":
            entity = await self.session.get(Agent, entity_id)
            if entity is None:
                raise ValueError("not_found")
            rbac_cleanup = RbacCleanupService(self.session)
            removed_rules = await rbac_cleanup.remove_rules_for_resource(
                resource_type="agent",
                resource_id=entity_id,
            )
            svc = AgentService(self.session)
            await svc.delete_agent(entity_id)
            return LifecycleReport(
                kind=kind,
                entity_id=str(entity_id),
                mode="hard",
                lifecycle_status="deleted",
                details={},
                migrated={},
                cascaded={},
                set_null={},
                rbac_rules_removed=removed_rules,
                renamed=[],
            )

        if kind == "rbac_rule":
            entity = await self.session.get(RbacRule, entity_id)
            if entity is None:
                raise ValueError("not_found")
            svc = RbacService(self.session)
            await svc.delete_rule(entity_id)
            return LifecycleReport(
                kind=kind,
                entity_id=str(entity_id),
                mode="hard",
                lifecycle_status="deleted",
                details={},
                migrated={},
                cascaded={},
                set_null={},
                rbac_rules_removed=0,
                renamed=[],
            )

        raise ValueError(f"Unsupported lifecycle kind: {kind}")

    async def _remove_collection_from_agent_bindings(self, collection_id: uuid.UUID) -> None:
        agents_result = await self.session.execute(
            select(Agent).where(Agent.allowed_collection_ids.isnot(None))
        )
        agents = agents_result.scalars().all()
        collection_id_str = str(collection_id)
        for agent in agents:
            allowed = list(getattr(agent, "allowed_collection_ids", None) or [])
            if not allowed:
                continue
            filtered = [cid for cid in allowed if str(cid) != collection_id_str]
            if len(filtered) == len(allowed):
                continue
            agent.allowed_collection_ids = filtered
            self.session.add(agent)

    async def _get_entity(self, kind: LifecycleKind, entity_id: uuid.UUID):
        model_map = {
            "tenant": Tenants,
            "user": Users,
            "collection": Collection,
            "agent": Agent,
            "rbac_rule": RbacRule,
        }
        model = model_map.get(kind)
        if model is None:
            return None
        return await self.session.get(model, entity_id)

    async def _tenant_dependencies(self, tenant_id: uuid.UUID, *, full_entities: bool = False) -> list[dict[str, Any]]:
        limit = None if full_entities else 5
        user_entities = await self._sample_entities(
            select(Users.id, Users.login).join(UserTenants, UserTenants.user_id == Users.id).where(UserTenants.tenant_id == tenant_id),
            resource_type="users",
            limit=limit,
        )
        collection_entities = await self._sample_entities(
            select(Collection.id, Collection.name).where(Collection.tenant_id == tenant_id),
            resource_type="collections",
            limit=limit,
        )
        sandbox_entities = await self._sample_entities(
            select(SandboxSession.id, SandboxSession.name).where(SandboxSession.tenant_id == tenant_id),
            resource_type="sandbox_sessions",
            limit=limit,
        )
        rbac_entities = await self._sample_entities(
            select(RbacRule.id, RbacRule.resource_type).where(RbacRule.owner_tenant_id == tenant_id),
            resource_type="rbac_rules",
            limit=limit,
        )
        counts = {
            "users": await self._count(select(func.count()).select_from(UserTenants).where(UserTenants.tenant_id == tenant_id)),
            "collections": await self._count(select(func.count()).select_from(Collection).where(Collection.tenant_id == tenant_id)),
            "sandbox_sessions": await self._count(select(func.count()).select_from(SandboxSession).where(SandboxSession.tenant_id == tenant_id)),
            "rbac_rules": await self._count(select(func.count()).select_from(RbacRule).where(RbacRule.owner_tenant_id == tenant_id)),
        }
        return [
            asdict(
                DependencyEntry(
                    "users",
                    counts["users"],
                    "migrate_to_default_tenant",
                    will_be="migrated",
                    entities=user_entities,
                    migration_target="platform_default_tenant",
                )
            ),
            asdict(
                DependencyEntry(
                    "collections",
                    counts["collections"],
                    "migrate_to_default_tenant",
                    will_be="migrated",
                    entities=collection_entities,
                    migration_target="platform_default_tenant",
                )
            ),
            asdict(
                DependencyEntry(
                    "chats",
                    0,
                    "detached_from_tenant",
                    will_be="set_null",
                    entities=[],
                )
            ),
            asdict(
                DependencyEntry(
                    "sandbox_sessions",
                    counts["sandbox_sessions"],
                    "cascade",
                    will_be="cascade_deleted",
                    entities=sandbox_entities,
                )
            ),
            asdict(
                DependencyEntry(
                    "rbac_rules",
                    counts["rbac_rules"],
                    "cascade",
                    will_be="cascade_deleted",
                    entities=rbac_entities,
                )
            ),
        ]

    async def _user_dependencies(self, user_id: uuid.UUID, *, full_entities: bool = False) -> list[dict[str, Any]]:
        limit = None if full_entities else 5
        tenant_binding_entities = await self._sample_entities(
            select(Tenants.id, Tenants.name).join(UserTenants, UserTenants.tenant_id == Tenants.id).where(UserTenants.user_id == user_id),
            resource_type="tenants",
            limit=limit,
        )
        chat_entities = await self._sample_entities(
            select(Chats.id, Chats.name).where(Chats.owner_id == user_id),
            resource_type="chats",
            limit=limit,
        )
        sandbox_entities = await self._sample_entities(
            select(SandboxSession.id, SandboxSession.name).where(SandboxSession.owner_id == user_id),
            resource_type="sandbox_sessions",
            limit=limit,
        )
        rbac_entities = await self._sample_entities(
            select(RbacRule.id, RbacRule.resource_type).where(RbacRule.owner_user_id == user_id),
            resource_type="rbac_rules",
            limit=limit,
        )
        is_last_admin = await self._is_last_active_admin(user_id)
        blocker_entry = []
        if is_last_admin:
            blocker_entry.append(
                asdict(
                    DependencyEntry(
                        "admin_guard",
                        1,
                        "cannot_delete_last_active_admin",
                        will_be="blocker",
                        details={"reason": "last_active_admin"},
                    )
                )
            )
        return [
            asdict(
                DependencyEntry(
                    "tenant_bindings",
                    await self._count(select(func.count()).select_from(UserTenants).where(UserTenants.user_id == user_id)),
                    "cascade",
                    will_be="cascade_deleted",
                    entities=tenant_binding_entities,
                )
            ),
            asdict(
                DependencyEntry(
                    "chats",
                    await self._count(select(func.count()).select_from(Chats).where(Chats.owner_id == user_id)),
                    "cascade",
                    will_be="cascade_deleted",
                    entities=chat_entities,
                )
            ),
            asdict(
                DependencyEntry(
                    "sandbox_sessions",
                    await self._count(select(func.count()).select_from(SandboxSession).where(SandboxSession.owner_id == user_id)),
                    "cascade",
                    will_be="cascade_deleted",
                    entities=sandbox_entities,
                )
            ),
            asdict(
                DependencyEntry(
                    "rbac_rules",
                    await self._count(select(func.count()).select_from(RbacRule).where(RbacRule.owner_user_id == user_id)),
                    "cascade",
                    will_be="cascade_deleted",
                    entities=rbac_entities,
                )
            ),
            *blocker_entry,
        ]

    async def _collection_dependencies(self, collection_id: uuid.UUID, *, full_entities: bool = False) -> list[dict[str, Any]]:
        limit = None if full_entities else 5
        rule_count = await self._count(
            select(func.count()).select_from(RbacRule).where(
                RbacRule.resource_type == "instance",
                RbacRule.resource_id == collection_id,
            )
        )
        rule_entities = await self._sample_entities(
            select(RbacRule.id, RbacRule.resource_type).where(
                RbacRule.resource_type == "instance",
                RbacRule.resource_id == collection_id,
            ),
            resource_type="rbac_rules",
            limit=limit,
        )
        return [
            asdict(
                DependencyEntry(
                    "rbac_rules",
                    rule_count,
                    "cascade",
                    will_be="cascade_deleted",
                    entities=rule_entities,
                )
            )
        ]

    async def _agent_dependencies(self, agent_id: uuid.UUID, *, full_entities: bool = False) -> list[dict[str, Any]]:
        limit = None if full_entities else 5
        rule_count = await self._count(
            select(func.count()).select_from(RbacRule).where(RbacRule.resource_type == "agent", RbacRule.resource_id == agent_id)
        )
        rule_entities = await self._sample_entities(
            select(RbacRule.id, RbacRule.resource_type).where(RbacRule.resource_type == "agent", RbacRule.resource_id == agent_id),
            resource_type="rbac_rules",
            limit=limit,
        )
        return [
            asdict(
                DependencyEntry(
                    "rbac_rules",
                    rule_count,
                    "cascade",
                    will_be="cascade_deleted",
                    entities=rule_entities,
                )
            )
        ]

    async def _count(self, query) -> int:
        return int((await self.session.execute(query)).scalar() or 0)

    async def _sample_ids(self, query, limit: int = 5) -> list[str]:
        rows = (await self.session.execute(query.limit(limit))).scalars().all()
        return [str(row) for row in rows]

    async def _sample_entities(self, query, *, resource_type: str, limit: int | None = 5) -> list[DependencyEntry.DependencyEntity]:
        if limit is not None:
            query = query.limit(limit)
        rows = (await self.session.execute(query)).all()
        items: list[DependencyEntry.DependencyEntity] = []
        for row in rows:
            row_uuid = str(row[0])
            row_name = str(row[1]) if len(row) > 1 and row[1] else row_uuid
            if resource_type == "rbac_rules":
                row_name = f"Rule: {row_name}"
            if resource_type == "chats" and row_name == row_uuid:
                row_name = f"Chat {row_uuid[:8]}"
            if resource_type == "sandbox_sessions" and row_name == row_uuid:
                row_name = f"Session {row_uuid[:8]}"
            items.append(
                DependencyEntry.DependencyEntity(
                    uuid=row_uuid,
                    name=row_name,
                    url=self._resource_url(resource_type, row_uuid),
                )
            )
        return items

    def _resource_url(self, resource_type: str, entity_id: str) -> str | None:
        mapping = {
            "users": f"/admin/users/{entity_id}",
            "collections": f"/admin/collections/{entity_id}",
            "sandbox_sessions": f"/sandbox/{entity_id}",
            "rbac_rules": f"/admin/rbac/{entity_id}",
            "tenants": f"/admin/tenants/{entity_id}",
            "chats": f"/chat/{entity_id}",
        }
        return mapping.get(resource_type)

    async def _is_last_active_admin(self, user_id: uuid.UUID) -> bool:
        target_user = await self.session.get(Users, user_id)
        if target_user is None:
            return False
        if target_user.role != "admin":
            return False
        if not bool(getattr(target_user, "is_active", True)):
            return False
        if getattr(target_user, "lifecycle_status", "active") != "active":
            return False

        count_active_admins = await self._count(
            select(func.count())
            .select_from(Users)
            .where(Users.role == "admin")
            .where(Users.is_active.is_(True))
            .where(Users.lifecycle_status == "active")
        )
        return count_active_admins <= 1

    async def _assert_user_not_last_active_admin(self, user_id: uuid.UUID) -> None:
        if await self._is_last_active_admin(user_id):
            raise ValueError("last_admin")
