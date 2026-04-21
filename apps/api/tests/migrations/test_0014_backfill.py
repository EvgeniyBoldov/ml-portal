from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

migration = importlib.import_module("app.migrations.versions.0014_collection_data_instance_fk")


class _FakeBind:
    def __init__(self, unresolved_ids: list[str]):
        self.unresolved_ids = unresolved_ids

    def execute(self, statement):
        sql = str(statement)
        if "SELECT id::text FROM collections WHERE data_instance_id IS NULL" in sql:
            return SimpleNamespace(fetchall=lambda: [(value,) for value in self.unresolved_ids])
        return SimpleNamespace(fetchall=lambda: [])


class _FakeOp:
    def __init__(self, unresolved_ids: list[str]):
        self.bind = _FakeBind(unresolved_ids)
        self.executed_sql: list[str] = []
        self.created_fk: list[str] = []
        self.altered_columns: list[tuple[str, str, bool]] = []

    def get_bind(self):
        return self.bind

    def execute(self, statement):
        self.executed_sql.append(str(statement))

    def add_column(self, *_args, **_kwargs):
        return None

    def create_foreign_key(self, name, *_args, **_kwargs):
        self.created_fk.append(name)

    def alter_column(self, table, column, **kwargs):
        self.altered_columns.append((table, column, bool(kwargs.get("nullable"))))

    def drop_constraint(self, *_args, **_kwargs):
        return None


def test_upgrade_fails_when_backfill_leaves_nulls(monkeypatch):
    fake_op = _FakeOp(unresolved_ids=["a", "b"])
    monkeypatch.setattr(migration, "op", fake_op)
    monkeypatch.setattr(migration, "_column_exists", lambda table, column: True)
    monkeypatch.setattr(migration, "_fk_exists", lambda table, fk: False)

    with pytest.raises(RuntimeError, match="unresolved collections without data_instance_id"):
        migration.upgrade()


def test_upgrade_cleans_bindings_when_config_column_exists(monkeypatch):
    fake_op = _FakeOp(unresolved_ids=[])
    monkeypatch.setattr(migration, "op", fake_op)
    monkeypatch.setattr(migration, "_column_exists", lambda table, column: True)
    monkeypatch.setattr(migration, "_fk_exists", lambda table, fk: False)

    migration.upgrade()

    assert "fk_collections_data_instance_id_tool_instances" in fake_op.created_fk
    assert any("config = config - 'bindings'" in sql for sql in fake_op.executed_sql)
    assert ("collections", "data_instance_id", False) in fake_op.altered_columns
