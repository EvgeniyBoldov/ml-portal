"""
Unit tests for services/collection/ddl.py

Tests DDL builder functions — pure string construction, no DB required.
"""
import pytest

from app.services.collection.ddl import (
    build_create_table_sql,
    build_indexes_sql,
    build_drop_indexes_sql,
)


SAMPLE_FIELDS = [
    {"name": "title", "data_type": "string", "required": True, "filterable": True, "sortable": False, "category": "user"},
    {"name": "body", "data_type": "text", "required": False, "filterable": True, "sortable": False, "category": "user"},
    {"name": "score", "data_type": "integer", "required": False, "filterable": True, "sortable": True, "category": "user"},
    {"name": "meta", "data_type": "json", "required": False, "filterable": False, "sortable": False, "category": "user"},
    {"name": "_sys", "data_type": "text", "required": False, "filterable": False, "sortable": False, "category": "specific"},
]


class TestBuildCreateTableSql:
    def test_contains_primary_key(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "id UUID PRIMARY KEY" in sql

    def test_contains_timestamps(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "_created_at" in sql
        assert "_updated_at" in sql

    def test_user_fields_included(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "title" in sql
        assert "body" in sql
        assert "score" in sql

    def test_specific_fields_excluded(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "_sys" not in sql

    def test_required_field_not_null(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "title VARCHAR(255) NOT NULL" in sql

    def test_optional_field_nullable(self):
        sql = build_create_table_sql("test_table", SAMPLE_FIELDS)
        assert "body TEXT\n" in sql or "body TEXT," in sql or "body TEXT " in sql

    def test_table_name_in_output(self):
        sql = build_create_table_sql("my_table", SAMPLE_FIELDS)
        assert "CREATE TABLE my_table" in sql

    def test_json_field_type(self):
        sql = build_create_table_sql("t", SAMPLE_FIELDS)
        assert "meta JSONB" in sql


class TestBuildIndexesSql:
    def test_trgm_index_for_filterable_string(self):
        indexes = build_indexes_sql("test_table", SAMPLE_FIELDS)
        trgm = [i for i in indexes if "title" in i and "trgm" in i]
        assert len(trgm) == 1

    def test_btree_index_for_sortable_integer(self):
        indexes = build_indexes_sql("test_table", SAMPLE_FIELDS)
        btree = [i for i in indexes if "score" in i and "btree" in i]
        assert len(btree) == 1

    def test_specific_fields_no_indexes(self):
        indexes = build_indexes_sql("test_table", SAMPLE_FIELDS)
        assert not any("_sys" in i for i in indexes)

    def test_json_fields_no_indexes(self):
        indexes = build_indexes_sql("test_table", SAMPLE_FIELDS)
        assert not any("meta" in i for i in indexes)

    def test_empty_fields_no_indexes(self):
        assert build_indexes_sql("t", []) == []


class TestBuildDropIndexesSql:
    def test_returns_two_statements(self):
        result = build_drop_indexes_sql("my_table", "title")
        assert len(result) == 2

    def test_drops_correct_table_and_field(self):
        result = build_drop_indexes_sql("my_table", "title")
        assert all("my_table" in s and "title" in s for s in result)

    def test_uses_if_exists(self):
        result = build_drop_indexes_sql("my_table", "title")
        assert all("IF EXISTS" in s for s in result)
