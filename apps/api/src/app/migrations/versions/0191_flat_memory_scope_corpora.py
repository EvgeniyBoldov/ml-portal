"""Flat memory scope slugs and independent HippoRAG corpora.

Revision ID: 0191
Revises: 0190
"""
from __future__ import annotations

from uuid import uuid4
import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0191"
down_revision = "0190"
branch_labels = None
depends_on = None


def _scope_payload(value: dict, mapping: dict[str, str]) -> dict:
    result = dict(value)
    old_keys = list(result.get("scope_keys") or [])
    if not old_keys:
        old_keys = [*(f"team.{key}" for key in result.get("team_keys", [])),
                    *(f"project.{key}" for key in result.get("project_keys", []))]
    origins = result.get("scope_origins") or {}
    explicit = (result.get("scope_mode") == "replace"
                or bool(result.get("suppress_team_default") and result.get("suppress_project_default"))
                or any(origin in {"turn", "chat_focus"} for origin in origins.values()))
    keys = list(dict.fromkeys(mapping.get(key, key) for key in old_keys if key in mapping))
    result.update(scope_keys=keys, scope_mode="replace" if explicit else "inherit",
                  suppress_scope_default=explicit and not keys, team_keys=[], project_keys=[],
                  suppress_team_default=False, suppress_project_default=False,
                  scope_origins={mapping.get(key, key): origin for key, origin in origins.items() if key in mapping},
                  mentioned_scope_keys=[mapping[key] for key in result.get("mentioned_scope_keys", []) if key in mapping])
    return result


def _runtime_scope(value, mapping: dict[str, str]):
    if isinstance(value, list):
        return [_runtime_scope(item, mapping) for item in value
                if not isinstance(item, dict) or item.get("type") not in {"memory_recall", "planner_memory_result"}]
    if not isinstance(value, dict):
        return value
    result = {key: _runtime_scope(item, mapping) for key, item in value.items()}
    for key in ("keys", "scope_keys", "ceiling_keys", "mentioned_keys", "mentioned_scope_keys", "scope_ceiling_keys", "effective_scope_keys", "explicit_scope_keys"):
        if isinstance(value.get(key), list):
            result[key] = list(dict.fromkeys(mapping.get(item, item) for item in value[key]))
    if value.get("key") in mapping:
        result.update(key=mapping[value["key"]], type="scope")
    if isinstance(value.get("scope_origins"), dict):
        result["scope_origins"] = {mapping.get(key, key): origin for key, origin in value["scope_origins"].items()}
    if value.get("type") == "execution_context":
        keys = [*value.get("team_keys", []), *value.get("focused_project_keys", [])]
        return {"type": "execution_context", "revision": value.get("revision", 0),
                "scope_keys": list(dict.fromkeys(mapping[key] for key in keys if key in mapping)),
                "search_policy": "parallel_independent_search_per_scope"}
    return result


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, key, scope_type, is_all, aliases FROM memory_scopes ORDER BY (key='project.all') DESC, scope_type, key")).mappings().all()
    op.drop_constraint("ck_memory_scopes_all_key", "memory_scopes", type_="check")
    op.drop_constraint("ck_memory_scopes_project_type", "memory_scopes", type_="check")
    op.drop_index("uq_memory_scopes_all_type", table_name="memory_scopes")
    op.drop_constraint("uq_memory_scopes_type_key", "memory_scopes", type_="unique")
    mapping, used = {}, set()
    for row in rows:
        if row["key"] == "project.all":
            slug = "company"
        elif row["scope_type"] == "team":
            slug = "team-" + ("common" if row["is_all"] else row["key"].removeprefix("team."))
        else:
            slug = row["key"].removeprefix("project.")
        slug = re.sub(r"[^a-z0-9._-]", "-", slug.lower()).strip("-.") or "scope"
        if slug in used:
            slug = slug[:170] + "-" + str(row["id"])[:8]
        used.add(slug)
        mapping[row["key"]] = slug
        connection.execute(sa.text("""UPDATE memory_scopes SET key=:key, scope_type='project', is_all=false,
            aliases=:aliases WHERE id=:id""").bindparams(sa.bindparam("aliases", type_=sa.ARRAY(sa.String))),
            {"key": slug, "id": row["id"], "aliases": list(dict.fromkeys([*(row["aliases"] or []), row["key"]]))})
    connection.execute(sa.text("""INSERT INTO memory_scopes (id, scope_type, key, name, aliases, is_all)
        SELECT :id, 'project', 'company', 'Компания', '{}', false
        WHERE NOT EXISTS (SELECT 1 FROM memory_scopes WHERE key='company')"""), {"id": uuid4()})
    op.execute("UPDATE memory_scopes SET name='Компания', lifecycle_status='active', deprecated_at=NULL WHERE key='company'")
    op.create_unique_constraint("uq_memory_scopes_key", "memory_scopes", ["key"])
    op.create_check_constraint("ck_memory_scopes_slug", "memory_scopes", "key ~ '^[a-z0-9][a-z0-9._-]*$'")
    op.create_check_constraint("ck_memory_scopes_flat", "memory_scopes", "scope_type = 'project' AND NOT is_all")
    op.alter_column("memory_scopes", "scope_type", server_default="project")
    # Existing links retain their scope IDs, including old team associations.
    # Multiple historical document links are retained; new uploads select one.
    op.execute("""INSERT INTO document_memory_scopes (document_id, scope_id, method)
        SELECT d.id, s.id, 'default' FROM ragdocuments d CROSS JOIN memory_scopes s
        WHERE s.key='company' AND NOT EXISTS (
            SELECT 1 FROM document_memory_scopes b WHERE b.document_id=d.id)""")
    op.execute("""UPDATE sources SET meta=jsonb_set(coalesce(meta, '{}'::jsonb), '{memory}',
        (coalesce(meta->'memory', '{}'::jsonb) - 'project_keys') || jsonb_build_object('scope_keys', bindings.keys))
        FROM (SELECT document_id, array_agg(s.key ORDER BY s.key) AS keys
              FROM document_memory_scopes b JOIN memory_scopes s ON s.id=b.scope_id
              GROUP BY document_id) bindings WHERE sources.source_id=bindings.document_id""")
    for table in ("users", "tenants"):
        for row in connection.execute(sa.text(f"SELECT id, memory_scope_keys FROM {table}")).mappings().all():
            keys = list(dict.fromkeys(mapping[key] for key in row["memory_scope_keys"] or [] if key in mapping))
            connection.execute(sa.text(f"UPDATE {table} SET memory_scope_keys=:keys WHERE id=:id").bindparams(
                sa.bindparam("keys", type_=sa.ARRAY(sa.String))), {"keys": keys, "id": row["id"]})
    for row in connection.execute(sa.text("SELECT id, payload FROM chat_memory_items WHERE kind='scope'")).mappings().all():
        connection.execute(sa.text("UPDATE chat_memory_items SET payload=:payload WHERE id=:id").bindparams(
            sa.bindparam("payload", type_=JSONB)), {"payload": _scope_payload(row["payload"] or {}, mapping), "id": row["id"]})
    # Active continuations keep their identities but discard old unscoped
    # retrieval context. Historical execution events remain immutable.
    for table, columns, predicate in (
        ("runtime_plans", ("scope_context", "memory_context"), "status IN ('draft','active','waiting_input')"),
        ("runtime_plan_tasks", ("scope_context",), "plan_id IN (SELECT id FROM runtime_plans WHERE status IN ('draft','active','waiting_input'))"),
        ("runtime_pauses", ("payload",), "status='waiting'"),
        ("chat_turns", ("paused_context",), "status='paused'"),
        ("sandbox_runs", ("paused_context",), "paused_context IS NOT NULL"),
    ):
        for row in connection.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table} WHERE {predicate}")).mappings().all():
            values = {column: _runtime_scope(row[column], mapping) for column in columns}
            stmt = sa.text(f"UPDATE {table} SET " + ', '.join(f"{column}=:{column}" for column in columns) + " WHERE id=:id")
            connection.execute(stmt.bindparams(*(sa.bindparam(column, type_=JSONB) for column in columns)), {**values, "id": row["id"]})
    from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3
    from app.services.v3_role_defaults import CHAT_CONTEXT_COMPACTOR_V1
    for role, prompt in (("turn_preflight", TURN_PREFLIGHT_PROMPT_V3),
                         ("chat_context_compactor", CHAT_CONTEXT_COMPACTOR_V1)):
        fields = {key: prompt[key] for key in ("identity", "mission", "rules", "safety", "output_requirements")}
        connection.execute(sa.text("""UPDATE system_llm_roles SET identity=:identity, mission=:mission,
            rules=:rules, safety=:safety, output_requirements=:output_requirements,
            examples='[]'::jsonb, updated_at=now() WHERE role_type=:role AND is_active IS TRUE"""),
            {**fields, "role": role})
    # Native reindex consumes authoritative document bindings from PostgreSQL
    # and reuses saved OpenIE snapshots. A committed request survives restarts.
    connection.execute(sa.text("""INSERT INTO long_memory_reindex_requests (id, model_id)
        SELECT :id, id FROM models WHERE use_for_long_memory IS TRUE"""), {"id": uuid4()})


def downgrade() -> None:
    raise RuntimeError("Scope identity migration preserves IDs but cannot restore old chat branch semantics automatically")
