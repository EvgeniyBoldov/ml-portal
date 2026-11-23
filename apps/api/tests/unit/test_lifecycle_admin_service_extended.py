"""Extended unit tests for LifecycleAdminService.

Covers dependency listing (including cascade expansion and memory-scope
blockers), soft delete edge cases, restore provenance queries, and hard
delete paths for every lifecycle kind. Uses a scripted fake AsyncSession
that dispatches on normalized statement text instead of a real database.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

import app.services.lifecycle_admin_service as lifecycle_module
from app.models.chat import Chats
from app.models.collection import Collection
from app.models.memory import MemoryClaim, MemoryItem
from app.models.memory_scope import MemoryScope
from app.models.rbac import RbacRule
from app.models.sandbox import SandboxSession
from app.models.tenant import Tenants
from app.models.user import Users
from app.services.lifecycle_admin_service import LifecycleAdminService


# ---------------------------------------------------------------------------
# Fake async session: handlers keyed by substring of normalized SQL text
# ---------------------------------------------------------------------------


def stmt_text(stmt: Any) -> str:
    compiled = stmt.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split())


class FakeScalarResult:
    def __init__(self, items: list) -> None:
        self._items = list(items)

    def all(self) -> list:
        return list(self._items)

    def __iter__(self):
        return iter(self._items)


class _Resolved:
    def __init__(self, value: Any) -> None:
        self._value = value

    def __await__(self):
        async def _coro():
            return self._value

        return _coro().__await__()


class FakeResult:
    def __init__(
        self,
        *,
        rows=None,
        scalars=None,
        scalar=None,
        scalar_one=None,
        rowcount=0,
        async_scalars=False,
    ) -> None:
        self._rows = [tuple(row) for row in (rows or [])]
        self._scalars = scalars
        self._scalar = scalar
        self._scalar_one = scalar_one
        self.rowcount = rowcount
        self._async_scalars = async_scalars

    def all(self) -> list:
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar_one

    def scalars(self):
        items = self._scalars if self._scalars is not None else [row[0] for row in self._rows]
        result = FakeScalarResult(items)
        return _Resolved(result) if self._async_scalars else result


LIFECYCLE_DEFAULTS = dict(
    lifecycle_status="active",
    deprecated_at=None,
    deprecated_by=None,
    deprecated_reason=None,
    retention_days=None,
    delete_cascade=False,
    deprecated_root_kind=None,
    deprecated_root_id=None,
    is_active=True,
)


class FakeSession:
    def __init__(self) -> None:
        self.handlers: list[tuple[str, Any]] = []
        self.entities: dict[tuple[type, Any], Any] = {}
        self.executed: list[str] = []
        self.deleted: list[Any] = []
        self.added: list[Any] = []
        self.flush_count = 0

    def on(self, substr: str, result: FakeResult | None = None, **kwargs) -> None:
        self.handlers.append((substr, result if result is not None else FakeResult(**kwargs)))

    def entity(self, model: type, id_: Any, **attrs):
        fields = {**LIFECYCLE_DEFAULTS, "id": id_, **attrs}
        obj = SimpleNamespace(**fields)
        self.entities[(model, id_)] = obj
        return obj

    def _resolve(self, text: str) -> FakeResult:
        for substr, result in self.handlers:
            if substr in text:
                return result(text) if callable(result) else result
        return FakeResult()

    async def execute(self, stmt) -> FakeResult:
        text = stmt_text(stmt)
        self.executed.append(text)
        return self._resolve(text)

    async def scalar(self, stmt):
        return self._resolve(stmt_text(stmt)).scalar()

    async def scalars(self, stmt):
        return self._resolve(stmt_text(stmt)).scalars()

    async def get(self, model: type, id_: Any):
        return self.entities.get((model, id_))

    async def delete(self, obj) -> None:
        self.deleted.append(obj)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    def executed_any(self, substr: str) -> bool:
        return any(substr in text for text in self.executed)


def memory_claim_entity(claim_id, item_id, *, lifecycle_status="active"):
    return SimpleNamespace(
        id=claim_id,
        memory_item_id=item_id,
        lifecycle_status=lifecycle_status,
        deprecated_at=None,
        deprecated_by=None,
        deprecated_reason=None,
        retention_days=None,
        delete_cascade=False,
        deprecated_root_kind=None,
        deprecated_root_id=None,
    )


def memory_item_entity(item_id, *, lifecycle_status="active"):
    return SimpleNamespace(
        id=item_id,
        lifecycle_status=lifecycle_status,
        deprecated_at=None,
        deprecated_by=None,
        deprecated_reason=None,
        retention_days=None,
        delete_cascade=False,
        deprecated_root_kind=None,
        deprecated_root_id=None,
    )


# ---------------------------------------------------------------------------
# get_dependencies
# ---------------------------------------------------------------------------


async def test_get_dependencies_tenant_lists_all_resources():
    session = FakeSession()
    user_id, coll_id, sandbox_id, rule_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.on("users.login", rows=[(user_id, "alice")])
    session.on("collections.name", rows=[(coll_id, "Marketing")])
    session.on("sandbox_sessions.name", rows=[(sandbox_id, "Sandbox One")])
    session.on("rbac_rules.resource_type", rows=[(rule_id, "instance")])
    session.on("FROM user_tenants WHERE user_tenants.tenant_id", scalar=2)
    session.on("FROM collections WHERE collections.tenant_id", scalar=1)
    session.on("FROM sandbox_sessions WHERE sandbox_sessions.tenant_id", scalar=1)
    session.on("FROM rbac_rules WHERE rbac_rules.owner_tenant_id", scalar=1)

    deps = await LifecycleAdminService(session).get_dependencies("tenant", uuid4())

    by_type = {d["resource_type"]: d for d in deps}
    assert set(by_type) == {"users", "collections", "chats", "sandbox_sessions", "rbac_rules"}
    assert by_type["users"]["count"] == 2
    assert by_type["users"]["action"] == "migrate_to_default_tenant"
    assert by_type["users"]["will_be"] == "migrated"
    assert by_type["users"]["migration_target"] == "platform_default_tenant"
    assert by_type["users"]["entities"] == [
        {"uuid": str(user_id), "name": "alice", "url": f"/admin/users/{user_id}"}
    ]
    assert by_type["collections"]["count"] == 1
    assert by_type["collections"]["entities"][0]["url"] == f"/admin/collections/{coll_id}"
    assert by_type["chats"] == {
        "resource_type": "chats",
        "count": 0,
        "action": "detached_from_tenant",
        "will_be": "set_null",
        "entities": [],
        "migration_target": None,
        "details": {},
    }
    sandbox_entity = by_type["sandbox_sessions"]["entities"][0]
    assert sandbox_entity["name"] == "Sandbox One"
    assert sandbox_entity["url"] == f"/sandbox/{sandbox_id}"
    rule_entity = by_type["rbac_rules"]["entities"][0]
    assert rule_entity["name"] == "Rule: instance"
    assert rule_entity["url"] == f"/admin/rbac/{rule_id}"


async def test_get_dependencies_user_appends_last_admin_blocker():
    session = FakeSession()
    user_id = uuid4()
    tenant_id, chat_id, sandbox_id, rule_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.entity(Users, user_id, is_admin=True)
    session.on("tenants.name", rows=[(tenant_id, "Acme")])
    session.on("chats.name", rows=[(chat_id, None)])
    session.on("sandbox_sessions.name", rows=[(sandbox_id, None)])
    session.on("rbac_rules.resource_type", rows=[(rule_id, "agent")])
    session.on("FROM user_tenants WHERE user_tenants.user_id", scalar=1)
    session.on("FROM chats WHERE chats.owner_id", scalar=1)
    session.on("FROM sandbox_sessions WHERE sandbox_sessions.owner_id", scalar=1)
    session.on("FROM rbac_rules WHERE rbac_rules.owner_user_id", scalar=1)
    session.on("FROM users WHERE users.is_admin", scalar=1)

    deps = await LifecycleAdminService(session).get_dependencies("user", user_id)

    by_type = {d["resource_type"]: d for d in deps}
    guard = by_type["admin_guard"]
    assert guard["count"] == 1
    assert guard["action"] == "cannot_delete_last_active_admin"
    assert guard["will_be"] == "blocker"
    assert guard["details"] == {"reason": "last_active_admin"}
    assert by_type["tenant_bindings"]["count"] == 1
    assert by_type["tenant_bindings"]["entities"][0]["url"] == f"/admin/tenants/{tenant_id}"
    assert by_type["chats"]["entities"][0]["name"] == f"Chat {str(chat_id)[:8]}"
    assert by_type["chats"]["entities"][0]["url"] == f"/chat/{chat_id}"
    assert by_type["sandbox_sessions"]["entities"][0]["name"] == f"Session {str(sandbox_id)[:8]}"
    assert by_type["rbac_rules"]["entities"][0]["name"] == "Rule: agent"


async def test_get_dependencies_user_without_admin_guard():
    session = FakeSession()
    user_id = uuid4()
    session.entity(Users, user_id, is_admin=False)

    deps = await LifecycleAdminService(session).get_dependencies("user", user_id)

    assert [d["resource_type"] for d in deps] == [
        "tenant_bindings",
        "chats",
        "sandbox_sessions",
        "rbac_rules",
    ]


async def test_is_last_active_admin_variants():
    session = FakeSession()
    svc = LifecycleAdminService(session)
    user_id = uuid4()

    session.entities[(Users, user_id)] = None
    assert await svc._is_last_active_admin(user_id) is False

    session.entity(Users, user_id, is_admin=False)
    assert await svc._is_last_active_admin(user_id) is False

    session.entity(Users, user_id, is_admin=True, is_active=False)
    assert await svc._is_last_active_admin(user_id) is False

    session.entity(Users, user_id, is_admin=True, lifecycle_status="deprecated")
    assert await svc._is_last_active_admin(user_id) is False

    session.on("FROM users WHERE users.is_admin", scalar=3)
    session.entity(Users, user_id, is_admin=True)
    assert await svc._is_last_active_admin(user_id) is False

    session.handlers = [("FROM users WHERE users.is_admin", FakeResult(scalar=1))]
    assert await svc._is_last_active_admin(user_id) is True


async def test_get_dependencies_collection_agent_and_leaf_kinds():
    session = FakeSession()
    rule_id = uuid4()
    session.on("SELECT rbac_rules.id, rbac_rules.resource_type", rows=[(rule_id, "instance")])
    session.on("FROM rbac_rules WHERE rbac_rules.resource_type", scalar=1)
    svc = LifecycleAdminService(session)

    deps = await svc.get_dependencies("collection", uuid4())
    assert deps == [
        {
            "resource_type": "rbac_rules",
            "count": 1,
            "action": "cascade",
            "will_be": "cascade_deleted",
            "entities": [
                {"uuid": str(rule_id), "name": "Rule: instance", "url": f"/admin/rbac/{rule_id}"}
            ],
            "migration_target": None,
            "details": {},
        }
    ]

    agent_deps = await svc.get_dependencies("agent", uuid4())
    assert agent_deps[0]["resource_type"] == "rbac_rules"

    assert await svc.get_dependencies("rbac_rule", uuid4()) == []
    assert await svc.get_dependencies("chat", uuid4()) == []
    assert await svc.get_dependencies("sandbox_session", uuid4()) == []


async def test_get_dependencies_unsupported_kind_raises():
    svc = LifecycleAdminService(FakeSession())
    with pytest.raises(ValueError, match="Unsupported lifecycle kind: memory_claim"):
        await svc.get_dependencies("memory_claim", uuid4())


async def test_get_dependencies_memory_scope_marks_blockers_without_cascade():
    session = FakeSession()
    claim_id, item_id, candidate_id, document_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.on("SELECT memory_claims.id, memory_claims.normalized_subject", rows=[(claim_id, "prefers dark mode")])
    session.on("SELECT memory_candidate_scopes.candidate_id", rows=[(candidate_id,)])
    session.on("SELECT document_memory_scopes.document_id", rows=[(document_id,)])
    session.on("SELECT memory_items.id, memory_items.subject", rows=[(item_id, "UI prefs")])
    session.on("count(distinct(memory_claims.memory_item_id))", scalar_one=1)
    session.on("FROM memory_claim_scopes WHERE memory_claim_scopes.scope_id", scalar=2)
    session.on("FROM memory_candidate_scopes WHERE memory_candidate_scopes.scope_id", scalar=0)
    session.on("FROM document_memory_scopes WHERE document_memory_scopes.scope_id", scalar=3)

    deps = await LifecycleAdminService(session).get_dependencies("memory_scope", uuid4())

    by_type = {d["resource_type"]: d for d in deps}
    claims = by_type["memory_claims"]
    assert claims["count"] == 2
    assert claims["action"] == "block_delete_without_cascade"
    assert claims["will_be"] == "blocker"
    assert claims["entities"][0]["name"] == "prefers dark mode"
    items = by_type["memory_items"]
    assert items["count"] == 1
    assert items["action"] == "block_delete_without_cascade"
    assert items["will_be"] == "blocker"
    candidates = by_type["memory_candidates"]
    assert candidates["count"] == 0
    assert candidates["action"] == "remove_scope_binding"
    assert candidates["will_be"] == "cascade_deleted"
    assert candidates["entities"][0]["name"] == str(candidate_id)
    documents = by_type["document_scope_hints"]
    assert documents["count"] == 3
    assert documents["will_be"] == "blocker"


def test_apply_dependency_mode_semantics_variants():
    svc = LifecycleAdminService(FakeSession())
    deps = [
        {"resource_type": "users", "count": 1, "action": "migrate", "will_be": "migrated"},
        {"resource_type": "tenants", "count": 2, "action": "cascade", "will_be": "cascade_deleted"},
        {"resource_type": "chats", "count": 1, "action": "original", "will_be": "blocker"},
        {"resource_type": "admin_guard", "count": 1, "action": "cannot", "will_be": "blocker"},
    ]

    unchanged = svc._apply_dependency_mode_semantics(deps, mode="hard", cascade=False)
    assert unchanged == deps

    soft = svc._apply_dependency_mode_semantics(deps, mode="soft", cascade=True)
    assert soft[0]["action"] == "cascade"
    assert soft[0]["will_be"] == "cascade_deprecated"
    # "tenants" is not a lifecycle dependency resource: left untouched.
    assert soft[1]["action"] == "cascade"
    assert soft[1]["will_be"] == "cascade_deleted"
    # Blockers pass through untouched.
    assert soft[2] == deps[2]
    assert soft[3] == deps[3]

    hard = svc._apply_dependency_mode_semantics(deps, mode="hard", cascade=True)
    assert hard[0]["will_be"] == "cascade_deleted"


async def test_get_dependencies_cascade_expands_child_dependencies():
    session = FakeSession()
    tenant_id, user_id, binding_tenant_id = uuid4(), uuid4(), uuid4()
    session.on(
        "users.login",
        rows=[(user_id, "bob"), (user_id, "bob"), ("not-a-uuid", "x"), ("", "y")],
    )
    session.on("FROM user_tenants WHERE user_tenants.tenant_id", scalar=1)
    session.on("tenants.name", rows=[(binding_tenant_id, "Acme")])
    session.on("FROM user_tenants WHERE user_tenants.user_id", scalar=1)

    deps = await LifecycleAdminService(session).get_dependencies(
        "tenant", tenant_id, mode="soft", cascade=True, full_entities=True
    )

    # 5 direct tenant entries + 4 expanded user entries (visited/invalid dedup).
    assert len(deps) == 9
    direct_users = next(d for d in deps if d["resource_type"] == "users")
    assert direct_users["action"] == "cascade"
    assert direct_users["will_be"] == "cascade_deprecated"
    child_bindings = [d for d in deps if d["resource_type"] == "tenant_bindings"]
    assert len(child_bindings) == 1
    assert child_bindings[0]["count"] == 1
    # "tenant_bindings" is not rewritten by mode semantics.
    assert child_bindings[0]["action"] == "cascade"
    assert child_bindings[0]["will_be"] == "cascade_deleted"
    assert child_bindings[0]["details"]["cascade_parent"] == {
        "kind": "user",
        "id": str(user_id),
        "name": "bob",
        "resource_type": "users",
    }
    expanded_chats = [d for d in deps if d["resource_type"] == "chats"]
    assert len(expanded_chats) == 2
    assert all(d["will_be"] == "cascade_deprecated" for d in expanded_chats)


# ---------------------------------------------------------------------------
# soft_delete
# ---------------------------------------------------------------------------


async def test_soft_delete_raises_not_found():
    svc = LifecycleAdminService(FakeSession())
    with pytest.raises(ValueError, match="not_found"):
        await svc.soft_delete("tenant", uuid4(), actor_id=None, reason=None, retention_days=None)


async def test_soft_delete_deprecated_root_updates_fields():
    session = FakeSession()
    tenant_id = uuid4()
    tenant = session.entity(Tenants, tenant_id, is_platform_default=False, lifecycle_status="deprecated", retention_days=14, deprecated_reason="old")

    report = await LifecycleAdminService(session).soft_delete(
        "tenant", tenant_id, actor_id=None, reason="new reason", retention_days=5, cascade=True
    )

    assert report.lifecycle_status == "deprecated"
    assert report.cascaded == {}
    assert report.details == {"retention_days": 5, "delete_cascade": True}
    assert tenant.retention_days == 5
    assert tenant.deprecated_reason == "new reason"
    assert tenant.delete_cascade is True


async def test_soft_delete_cascade_skips_invalid_and_deprecated_entries():
    session = FakeSession()
    root_id, dep_id = uuid4(), uuid4()
    session.entity(Tenants, root_id, is_platform_default=False)
    session.entity(Users, dep_id, is_admin=False, lifecycle_status="deprecated")
    svc = LifecycleAdminService(session)
    svc.get_dependencies = AsyncMock(
        return_value=[
            {"resource_type": "memory_claims", "entities": [{"uuid": str(uuid4()), "name": "c"}]},
            {
                "resource_type": "users",
                "entities": [
                    {"uuid": "not-a-uuid", "name": "bad"},
                    {"uuid": "", "name": "empty"},
                    {"uuid": str(dep_id), "name": "dep"},
                    {"uuid": str(dep_id), "name": "duplicate"},
                ],
            },
        ]
    )

    report = await svc.soft_delete(
        "tenant", root_id, actor_id=None, reason=None, retention_days=None, cascade=True
    )

    assert report.cascaded == {}
    svc.get_dependencies.assert_awaited_once_with(
        "tenant", root_id, mode="soft", cascade=True, full_entities=True
    )


async def test_soft_delete_user_blocked_as_last_admin():
    session = FakeSession()
    user_id = uuid4()
    session.entity(Users, user_id, is_admin=True)
    session.on("FROM users WHERE users.is_admin", scalar=1)

    with pytest.raises(ValueError, match="last_admin"):
        await LifecycleAdminService(session).soft_delete(
            "user", user_id, actor_id=None, reason=None, retention_days=None
        )


async def test_soft_delete_memory_scope_with_cascade_counts_deprecated_memory():
    session = FakeSession()
    scope_id = uuid4()
    scope = session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    # Dependency listing queries (cascade=True -> full entities).
    session.on("count(distinct(memory_claims.memory_item_id))", scalar_one=0)
    # _deprecate_scope_memory: no claims bound to this scope.
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[])
    # Cascaded provenance counts after deprecation.
    session.on("FROM memory_claims WHERE memory_claims.lifecycle_status", scalar=1)
    session.on("FROM memory_items WHERE memory_items.lifecycle_status", scalar=1)

    report = await LifecycleAdminService(session).soft_delete(
        "memory_scope", scope_id, actor_id=None, reason="cleanup", retention_days=3, cascade=True
    )

    assert report.cascaded == {
        "memory_claims": 1,
        "memory_items": 1,
        "memory_candidates": 0,
        "document_scope_hints": 0,
    }
    assert scope.lifecycle_status == "deprecated"
    assert scope.deprecated_root_kind == "memory_scope"
    assert scope.deprecated_root_id == scope_id
    assert scope.retention_days == 3


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


async def test_restore_raises_not_found():
    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(FakeSession()).restore("chat", uuid4())


async def test_restore_active_entity_restores_nothing():
    session = FakeSession()
    chat_id = uuid4()
    session.entity(Chats, chat_id)

    report = await LifecycleAdminService(session).restore("chat", chat_id)

    assert report.lifecycle_status == "active"
    assert report.restored == {}
    assert report.details == {"restored_dependents": 0}
    assert session.flush_count == 1


async def test_restore_tenant_restores_cascaded_users_via_root_provenance():
    session = FakeSession()
    root_id, dep_id = uuid4(), uuid4()
    session.entity(
        Tenants,
        root_id,
        is_platform_default=False,
        lifecycle_status="deprecated",
        deprecated_reason="retire",
        delete_cascade=True,
        deprecated_root_kind="tenant",
        deprecated_root_id=root_id,
        is_active=False,
    )
    session.entity(
        Users,
        dep_id,
        is_admin=False,
        lifecycle_status="deprecated",
        deprecated_reason="retire",
        delete_cascade=True,
        deprecated_root_kind="tenant",
        deprecated_root_id=root_id,
        is_active=False,
    )
    session.on("users.deprecated_root_kind", rows=[(dep_id,)])

    report = await LifecycleAdminService(session).restore("tenant", root_id)

    assert report.restored == {"tenants": 1, "users": 1}
    assert report.details == {"restored_dependents": 2}
    tenant = session.entities[(Tenants, root_id)]
    user = session.entities[(Users, dep_id)]
    assert tenant.lifecycle_status == "active"
    assert tenant.is_active is True
    assert tenant.delete_cascade is False
    assert tenant.deprecated_root_kind is None
    assert tenant.deprecated_root_id is None
    assert user.lifecycle_status == "active"
    assert user.is_active is True


# ---------------------------------------------------------------------------
# hard_delete: tenant
# ---------------------------------------------------------------------------


async def test_hard_delete_tenant_not_found():
    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(FakeSession()).hard_delete("tenant", uuid4())


async def test_hard_delete_tenant_refuses_platform_default():
    session = FakeSession()
    tenant_id = uuid4()
    session.entity(Tenants, tenant_id, is_platform_default=True)

    with pytest.raises(ValueError, match="cannot_delete_default_tenant"):
        await LifecycleAdminService(session).hard_delete("tenant", tenant_id)


async def test_hard_delete_tenant_requires_platform_default(monkeypatch):
    session = FakeSession()
    tenant_id = uuid4()
    session.entity(Tenants, tenant_id, is_platform_default=False)

    class FakeTenantsService:
        def __init__(self, session):
            self.repo = SimpleNamespace(get_platform_default=AsyncMock(return_value=None))

    monkeypatch.setattr(lifecycle_module, "AsyncTenantsService", FakeTenantsService)

    with pytest.raises(ValueError, match="platform_default_tenant_not_found"):
        await LifecycleAdminService(session).hard_delete("tenant", tenant_id)


async def test_hard_delete_tenant_cascade_deletes_users_collections_sandboxes(monkeypatch):
    session = FakeSession()
    tenant_id, default_id = uuid4(), uuid4()
    u1, u2, c1, c2, sb1, sb2 = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    tenant = session.entity(Tenants, tenant_id, is_platform_default=False)
    user1 = session.entity(Users, u1, is_admin=False)
    session.entity(Users, u2, is_admin=True)
    session.on("FROM users JOIN user_tenants", rows=[(u1,), (u2,)])
    session.on("FROM users WHERE users.is_admin", scalar=1)  # u2 is last admin -> skipped
    session.on("SELECT collections.id", rows=[(c1,), (c2,)])
    session.on("SELECT sandbox_sessions.id", rows=[(str(sb1),), (str(sb2),)])

    class FakeTenantsService:
        def __init__(self, session):
            self.repo = SimpleNamespace(
                get_platform_default=AsyncMock(return_value=SimpleNamespace(id=default_id))
            )

    collection_deletes: list = []

    class FakeCollectionService:
        def __init__(self, session):
            self.session = session

        async def delete_collection(self, coll_id, *, drop_table=False):
            collection_deletes.append(coll_id)
            if coll_id == c2:
                raise RuntimeError("collection boom")
            return True

    sandbox_deletes: list = []

    class FakeSandboxService:
        def __init__(self, session):
            self.session = session

        async def delete_session(self, sandbox_id):
            sandbox_deletes.append(sandbox_id)
            return sandbox_id == sb1

    chat_deletes: list = []

    class FakeChatsService:
        def __init__(self, session):
            self.session = session

        async def delete_chat(self, *, chat_id, owner_id):
            chat_deletes.append((chat_id, owner_id))

    rbac_owner_calls: list = []

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_owner(self, *, owner_tenant_id=None, owner_user_id=None):
            if owner_tenant_id is not None:
                rbac_owner_calls.append(("tenant", owner_tenant_id))
                return 7
            rbac_owner_calls.append(("user", owner_user_id))
            return 0

    monkeypatch.setattr(lifecycle_module, "AsyncTenantsService", FakeTenantsService)
    monkeypatch.setattr(lifecycle_module, "CollectionService", FakeCollectionService)
    monkeypatch.setattr(lifecycle_module, "SandboxService", FakeSandboxService)
    monkeypatch.setattr(lifecycle_module, "ChatsService", FakeChatsService)
    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)

    report = await LifecycleAdminService(session).hard_delete("tenant", tenant_id, cascade=True)

    assert report.kind == "tenant"
    assert report.mode == "hard"
    assert report.lifecycle_status == "deleted"
    assert report.details == {}
    assert report.cascaded["users"] == 1
    assert report.cascaded["collections"] == 1
    assert report.cascaded["sandbox_sessions"] == 1
    assert report.cascaded.get("chats") == 0
    assert report.rbac_rules_removed == 7
    assert report.migrated == {}
    assert report.renamed == []
    assert tenant in session.deleted
    assert user1 in session.deleted
    assert session.flush_count >= 2  # nested user delete + tenant delete
    assert set(collection_deletes) == {c1, c2}
    assert set(sandbox_deletes) == {sb1, sb2}
    assert chat_deletes == []
    assert ("tenant", tenant_id) in rbac_owner_calls
    assert ("user", u1) in rbac_owner_calls
    assert session.executed_any("DELETE FROM user_tenants")


async def test_hard_delete_tenant_non_cascade_migrates_to_default(monkeypatch):
    session = FakeSession()
    tenant_id, default_id = uuid4(), uuid4()
    tenant = session.entity(Tenants, tenant_id, is_platform_default=False)
    session.on("SELECT sandbox_sessions.id", rows=[])

    class FakeTenantsService:
        def __init__(self, session):
            self.repo = SimpleNamespace(
                get_platform_default=AsyncMock(return_value=SimpleNamespace(id=default_id))
            )

    migrate = AsyncMock(
        return_value=SimpleNamespace(
            migrated={"chats": 4, "collections": 2},
            renamed_collections=[("old-name", "old-name-from-default")],
        )
    )

    class FakeMigrationService:
        def __init__(self, session):
            self.session = session

        async def migrate_tenant_data(self, *, from_tenant_id, to_tenant_id):
            return await migrate(from_tenant_id=from_tenant_id, to_tenant_id=to_tenant_id)

    remove_owner = AsyncMock(return_value=2)

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_owner(self, **kwargs):
            return await remove_owner(**kwargs)

    monkeypatch.setattr(lifecycle_module, "AsyncTenantsService", FakeTenantsService)
    monkeypatch.setattr(lifecycle_module, "TenantMigrationService", FakeMigrationService)
    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)

    report = await LifecycleAdminService(session).hard_delete("tenant", tenant_id)

    migrate.assert_awaited_once_with(from_tenant_id=tenant_id, to_tenant_id=default_id)
    remove_owner.assert_awaited_once_with(owner_tenant_id=tenant_id)
    assert report.details == {"migrated_to_tenant_id": str(default_id)}
    assert report.migrated == {"chats": 4, "collections": 2}
    assert report.renamed == [{"old": "old-name", "new": "old-name-from-default"}]
    assert report.rbac_rules_removed == 2
    assert report.cascaded == {}
    assert tenant in session.deleted


# ---------------------------------------------------------------------------
# hard_delete: user
# ---------------------------------------------------------------------------


async def test_hard_delete_user_not_found():
    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(FakeSession()).hard_delete("user", uuid4())


async def test_hard_delete_user_blocked_as_last_admin():
    session = FakeSession()
    user_id = uuid4()
    session.entity(Users, user_id, is_admin=True)
    session.on("FROM users WHERE users.is_admin", scalar=1)

    with pytest.raises(ValueError, match="last_admin"):
        await LifecycleAdminService(session).hard_delete("user", user_id)


async def test_hard_delete_user_deletes_chats_and_rbac_rules(monkeypatch):
    session = FakeSession()
    user_id, chat1, chat2 = uuid4(), uuid4(), uuid4()
    user = session.entity(Users, user_id, is_admin=False)
    session.on("SELECT chats.id", rows=[(chat1,), (chat2,)])
    session.on("FROM chats WHERE chats.owner_id", scalar=2)
    session.on("FROM sandbox_sessions WHERE sandbox_sessions.owner_id", scalar=1)

    delete_chat = AsyncMock(return_value=True)

    class FakeChatsService:
        def __init__(self, session):
            self.session = session

        async def delete_chat(self, **kwargs):
            return await delete_chat(**kwargs)

    remove_owner = AsyncMock(return_value=3)

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_owner(self, **kwargs):
            return await remove_owner(**kwargs)

    monkeypatch.setattr(lifecycle_module, "ChatsService", FakeChatsService)
    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)

    report = await LifecycleAdminService(session).hard_delete("user", user_id)

    assert delete_chat.await_count == 2
    delete_chat.assert_any_await(chat_id=chat1, owner_id=user_id)
    delete_chat.assert_any_await(chat_id=chat2, owner_id=user_id)
    remove_owner.assert_awaited_once_with(owner_user_id=user_id)
    assert report.cascaded == {"chats": 2, "sandbox_sessions": 1}
    assert report.rbac_rules_removed == 3
    assert user in session.deleted
    assert session.flush_count == 1


async def test_hard_delete_user_supports_awaitable_scalars(monkeypatch):
    session = FakeSession()
    user_id, chat_id = uuid4(), uuid4()
    session.entity(Users, user_id, is_admin=False)
    session.on("SELECT chats.id", FakeResult(rows=[(chat_id,)], async_scalars=True))

    class FakeChatsService:
        def __init__(self, session):
            self.session = session

        async def delete_chat(self, **kwargs):
            return True

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_owner(self, **kwargs):
            return 0

    monkeypatch.setattr(lifecycle_module, "ChatsService", FakeChatsService)
    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)

    report = await LifecycleAdminService(session).hard_delete("user", user_id)

    assert report.cascaded == {"chats": 0, "sandbox_sessions": 0}
    assert session.flush_count == 1


# ---------------------------------------------------------------------------
# hard_delete: collection / rbac_rule / chat / sandbox_session
# ---------------------------------------------------------------------------


async def test_hard_delete_collection_not_found():
    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(FakeSession()).hard_delete("collection", uuid4())


async def test_hard_delete_collection_not_found_when_service_declines(monkeypatch):
    session = FakeSession()
    coll_id = uuid4()
    session.entity(Collection, coll_id, slug="x")

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_resource(self, **kwargs):
            return 0

    class FakeCollectionService:
        def __init__(self, session):
            self.session = session

        async def delete_collection(self, *args, **kwargs):
            return False

    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)
    monkeypatch.setattr(lifecycle_module, "CollectionService", FakeCollectionService)

    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(session).hard_delete("collection", coll_id)


async def test_hard_delete_collection_unbinds_agents_and_drops_table(monkeypatch):
    session = FakeSession()
    coll_id = uuid4()
    other_collection_id = uuid4()
    session.entity(Collection, coll_id, slug="marketing")
    agent_with_binding = SimpleNamespace(allowed_collection_ids=[str(coll_id), str(other_collection_id)])
    agent_without_binding = SimpleNamespace(allowed_collection_ids=[str(other_collection_id)])
    agent_empty = SimpleNamespace(allowed_collection_ids=[])
    session.on(
        "SELECT agents.id",
        scalars=[agent_with_binding, agent_without_binding, agent_empty],
    )

    remove_resource = AsyncMock(return_value=4)

    class FakeRbacCleanupService:
        def __init__(self, session):
            self.session = session

        async def remove_rules_for_resource(self, **kwargs):
            return await remove_resource(**kwargs)

    delete_collection = AsyncMock(return_value=True)

    class FakeCollectionService:
        def __init__(self, session):
            self.session = session

        async def delete_collection(self, *args, **kwargs):
            return await delete_collection(*args, **kwargs)

    monkeypatch.setattr(lifecycle_module, "RbacCleanupService", FakeRbacCleanupService)
    monkeypatch.setattr(lifecycle_module, "CollectionService", FakeCollectionService)

    report = await LifecycleAdminService(session).hard_delete("collection", coll_id)

    assert agent_with_binding.allowed_collection_ids == [str(other_collection_id)]
    assert any(a is agent_with_binding for a in session.added)
    assert not any(a is agent_without_binding for a in session.added)
    assert not any(a is agent_empty for a in session.added)
    remove_resource.assert_awaited_once_with(resource_type="instance", resource_id=coll_id)
    delete_collection.assert_awaited_once_with("marketing", drop_table=True)
    assert report.details == {"table_dropped": True}
    assert report.rbac_rules_removed == 4
    assert report.lifecycle_status == "deleted"


async def test_hard_delete_rbac_rule_uses_rbac_service(monkeypatch):
    session = FakeSession()
    rule_id = uuid4()
    session.entities[(RbacRule, rule_id)] = SimpleNamespace(id=rule_id)
    delete_rule = AsyncMock()

    class FakeRbacService:
        def __init__(self, session):
            self.session = session

        async def delete_rule(self, rule_id):
            return await delete_rule(rule_id)

    monkeypatch.setattr(lifecycle_module, "RbacService", FakeRbacService)

    report = await LifecycleAdminService(session).hard_delete("rbac_rule", rule_id)

    delete_rule.assert_awaited_once_with(rule_id)
    assert report.lifecycle_status == "deleted"
    assert report.rbac_rules_removed == 0


async def test_hard_delete_chat_removes_row():
    session = FakeSession()
    chat_id = uuid4()
    chat = session.entity(Chats, chat_id)

    report = await LifecycleAdminService(session).hard_delete("chat", chat_id)

    assert report.mode == "hard"
    assert report.lifecycle_status == "deleted"
    assert session.deleted == [chat]
    assert session.flush_count == 1


async def test_hard_delete_sandbox_uses_service(monkeypatch):
    session = FakeSession()
    sandbox_id = uuid4()
    session.entities[(SandboxSession, sandbox_id)] = SimpleNamespace(id=sandbox_id)
    delete_session = AsyncMock(return_value=True)

    class FakeSandboxService:
        def __init__(self, session):
            self.session = session

        async def delete_session(self, sandbox_id):
            return await delete_session(sandbox_id)

    monkeypatch.setattr(lifecycle_module, "SandboxService", FakeSandboxService)

    report = await LifecycleAdminService(session).hard_delete("sandbox_session", sandbox_id)

    delete_session.assert_awaited_once_with(sandbox_id)
    assert report.mode == "hard"
    assert report.lifecycle_status == "deleted"


async def test_hard_delete_unsupported_kind_raises():
    with pytest.raises(ValueError, match="Unsupported lifecycle kind: memory_claim"):
        await LifecycleAdminService(FakeSession()).hard_delete("memory_claim", uuid4())


# ---------------------------------------------------------------------------
# hard_delete: memory_scope
# ---------------------------------------------------------------------------


async def test_hard_delete_memory_scope_not_found():
    with pytest.raises(ValueError, match="not_found"):
        await LifecycleAdminService(FakeSession()).hard_delete("memory_scope", uuid4())


async def test_hard_delete_memory_scope_blocked_without_cascade():
    session = FakeSession()
    scope_id = uuid4()
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("count(distinct(memory_claims.memory_item_id))", scalar_one=0)
    session.on("FROM memory_claim_scopes WHERE memory_claim_scopes.scope_id", scalar=1)

    with pytest.raises(ValueError, match="memory_scope_has_dependencies"):
        await LifecycleAdminService(session).hard_delete("memory_scope", scope_id)


async def test_hard_delete_memory_scope_without_dependencies_or_hints():
    session = FakeSession()
    scope_id = uuid4()
    scope = session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("count(distinct(memory_claims.memory_item_id))", scalar_one=0)
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[])

    report = await LifecycleAdminService(session).hard_delete("memory_scope", scope_id)

    assert report.details == {
        "claims_deleted": 0,
        "claims_retained_for_other_scopes": 0,
        "documents_preserved": 0,
        "long_memory_reindex_queued": False,
    }
    assert report.cascaded == {
        "memory_claims": 0,
        "memory_items": 0,
        "memory_candidates": 0,
        "document_scope_hints": 0,
    }
    assert scope in session.deleted
    assert session.flush_count == 1
    assert session.executed_any("UPDATE users SET")
    assert session.executed_any("UPDATE tenants SET")
    assert session.executed_any("DELETE FROM memory_candidate_scopes")
    assert session.executed_any("DELETE FROM document_memory_scopes")
    assert not session.executed_any("DELETE FROM memory_claim_scopes")
    assert not session.executed_any("DELETE FROM memory_claims")
    assert not session.executed_any("DELETE FROM memory_items")


async def test_hard_delete_memory_scope_cascade_deletes_unshared_claims_and_items():
    session = FakeSession()
    scope_id, claim1, claim2, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    scope = session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[(claim1,), (claim2,)])
    session.on("FROM memory_claim_scopes JOIN memory_scopes", rows=[(claim2,)])  # claim2 retained elsewhere
    session.on("SELECT memory_claims.memory_item_id", rows=[(item_id,)])
    session.on("FROM memory_candidate_scopes WHERE memory_candidate_scopes.scope_id", scalar=5)
    session.on("FROM memory_claims WHERE memory_claims.memory_item_id", scalar=0)
    session.on("DELETE FROM memory_items", rowcount=1)

    report = await LifecycleAdminService(session).hard_delete("memory_scope", scope_id, cascade=True)

    assert report.details["claims_deleted"] == 1
    assert report.details["claims_retained_for_other_scopes"] == 1
    assert report.cascaded == {
        "memory_claims": 1,
        "memory_items": 1,
        "memory_candidates": 5,
        "document_scope_hints": 0,
    }
    assert scope in session.deleted
    assert session.executed_any("DELETE FROM memory_claim_scopes")
    assert session.executed_any("DELETE FROM memory_claims")
    assert session.executed_any("DELETE FROM memory_items")
    assert session.executed_any("DELETE FROM memory_candidate_scopes")
    assert session.executed_any("DELETE FROM document_memory_scopes")


async def test_hard_delete_memory_scope_cascade_keeps_items_with_remaining_claims():
    session = FakeSession()
    scope_id, claim_id, item_id = uuid4(), uuid4(), uuid4()
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[(claim_id,)])
    session.on("SELECT memory_claims.memory_item_id", rows=[(item_id,)])
    session.on("FROM memory_claims WHERE memory_claims.memory_item_id", scalar=2)

    report = await LifecycleAdminService(session).hard_delete("memory_scope", scope_id, cascade=True)

    assert report.cascaded["memory_items"] == 0
    assert not session.executed_any("DELETE FROM memory_items")


async def test_hard_delete_memory_scope_requires_long_memory_encoder():
    session = FakeSession()
    scope_id = uuid4()
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[])
    session.on("FROM document_memory_scopes WHERE document_memory_scopes.scope_id", scalar=2)

    with pytest.raises(ValueError, match="long_memory_encoder_not_configured"):
        await LifecycleAdminService(session).hard_delete("memory_scope", scope_id, cascade=True)


async def test_hard_delete_memory_scope_preserves_documents_and_queues_reindex(monkeypatch):
    session = FakeSession()
    scope_id, doc1, doc2, encoder_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[])
    session.on("FROM document_memory_scopes WHERE document_memory_scopes.scope_id", scalar=2)
    session.on("SELECT document_memory_scopes.document_id", FakeResult(scalars=[doc1, doc2]))
    session.on("SELECT models.id", scalar=encoder_id)
    source1 = SimpleNamespace(source_id=doc1, tenant_id=uuid4())
    source2 = SimpleNamespace(source_id=doc2, tenant_id=uuid4())
    session.on("FROM sources", FakeResult(scalars=[source1, source2]))

    reconcile = AsyncMock()

    class FakeMetadataService:
        def __init__(self, session):
            self.session = session

        async def reconcile_scope_assignment(self, source_id, tenant_id):
            return await reconcile(source_id, tenant_id)

    request_reindex = AsyncMock()

    class FakeConfigRepository:
        def __init__(self, session):
            self.session = session

        async def request_reindex(self, encoder_id):
            return await request_reindex(encoder_id)

    monkeypatch.setattr(
        "app.services.document_source_metadata_service.DocumentSourceMetadataService",
        FakeMetadataService,
    )
    monkeypatch.setattr(
        "app.repositories.long_memory_config_repository.LongMemoryConfigRepository",
        FakeConfigRepository,
    )

    report = await LifecycleAdminService(session).hard_delete("memory_scope", scope_id, cascade=True)

    assert reconcile.await_count == 2
    reconcile.assert_any_await(source1.source_id, source1.tenant_id)
    reconcile.assert_any_await(source2.source_id, source2.tenant_id)
    request_reindex.assert_awaited_once_with(encoder_id)
    assert report.details["documents_preserved"] == 2
    assert report.details["long_memory_reindex_queued"] is True
    assert report.cascaded["document_scope_hints"] == 2
    assert session.flush_count == 1


# ---------------------------------------------------------------------------
# _deprecate_scope_memory
# ---------------------------------------------------------------------------


async def test_deprecate_scope_memory_marks_unshared_claims_and_items():
    session = FakeSession()
    scope_id = uuid4()
    claim1, claim2, claim3 = uuid4(), uuid4(), uuid4()
    item1, item2, item3 = uuid4(), uuid4(), uuid4()
    c1 = memory_claim_entity(claim1, item1)
    c2 = memory_claim_entity(claim2, item2)
    c3 = memory_claim_entity(claim3, item3, lifecycle_status="deprecated")
    i1 = memory_item_entity(item1)
    i3 = memory_item_entity(item3, lifecycle_status="deprecated")
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[(claim1,), (claim2,), (claim3,)])
    session.on("FROM memory_claims WHERE memory_claims.id IN", scalars=[c1, c2, c3])
    session.on("FROM memory_claim_scopes JOIN memory_scopes", rows=[(claim2,)])  # claim2 retained
    session.on("FROM memory_claims WHERE memory_claims.memory_item_id", scalar=0)
    session.entities[(MemoryItem, item1)] = i1
    session.entities[(MemoryItem, item3)] = i3

    actor_id = uuid4()
    await LifecycleAdminService(session)._deprecate_scope_memory(
        scope_id, actor_id=actor_id, reason="cleanup", retention_days=8, root_id=scope_id
    )

    assert c1.lifecycle_status == "deprecated"
    assert c1.deprecated_at is not None
    assert c1.deprecated_by is actor_id
    assert c1.deprecated_reason == "cleanup"
    assert c1.retention_days == 8
    assert c1.delete_cascade is True
    assert c1.deprecated_root_kind == "memory_scope"
    assert c1.deprecated_root_id == scope_id
    # Retained for another active scope: untouched.
    assert c2.lifecycle_status == "active"
    # Already deprecated: untouched.
    assert c3.deprecated_reason is None
    # Item with no active claims elsewhere is deprecated.
    assert i1.lifecycle_status == "deprecated"
    assert i1.deprecated_root_id == scope_id
    # Already deprecated item: untouched.
    assert i3.deprecated_reason is None


async def test_deprecate_scope_memory_keeps_items_with_active_claims_elsewhere():
    session = FakeSession()
    scope_id, claim_id, item_id = uuid4(), uuid4(), uuid4()
    claim = memory_claim_entity(claim_id, item_id)
    item = memory_item_entity(item_id)
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[(claim_id,)])
    session.on("FROM memory_claims WHERE memory_claims.id IN", scalars=[claim])
    session.on("FROM memory_claim_scopes JOIN memory_scopes", rows=[])
    session.on("FROM memory_claims WHERE memory_claims.memory_item_id", scalar=1)
    session.entities[(MemoryItem, item_id)] = item

    await LifecycleAdminService(session)._deprecate_scope_memory(
        scope_id, actor_id=None, reason=None, retention_days=None, root_id=scope_id
    )

    assert claim.lifecycle_status == "deprecated"
    assert item.lifecycle_status == "active"


async def test_deprecate_scope_memory_skips_missing_item():
    session = FakeSession()
    scope_id, claim_id, item_id = uuid4(), uuid4(), uuid4()
    claim = memory_claim_entity(claim_id, item_id)
    session.entity(MemoryScope, scope_id, scope_type="company", key="company")
    session.on("SELECT memory_claim_scopes.claim_id FROM memory_claim_scopes WHERE", rows=[(claim_id,)])
    session.on("FROM memory_claims WHERE memory_claims.id IN", scalars=[claim])
    session.on("FROM memory_claim_scopes JOIN memory_scopes", rows=[])
    session.on("FROM memory_claims WHERE memory_claims.memory_item_id", scalar=0)

    await LifecycleAdminService(session)._deprecate_scope_memory(
        scope_id, actor_id=None, reason=None, retention_days=None, root_id=scope_id
    )

    assert claim.lifecycle_status == "deprecated"


# Silence unused-import warnings for models referenced only via entities dict.
_ = (MemoryClaim, MemoryItem)
