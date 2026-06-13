"""Tests for TemplateFillEngine (S4)."""
from __future__ import annotations
import pytest
from app.services.collection.template_contract import (
    ScalarField, TableField, TableColumn, TemplateContract, FieldType,
    AnchorStrategy, TableAnchor, MarkerAnchor, StructuralAnchor,
)
from app.services.collection.template_fill_engine import TemplateFillEngine, FillResult


@pytest.fixture
def scalar_contract():
    return TemplateContract(fields=[
        ScalarField(key="name", label="Name", type=FieldType.STRING, required=True),
        ScalarField(key="amount", label="Amount", type=FieldType.NUMBER, required=True),
    ])


@pytest.fixture
def table_contract():
    return TemplateContract(fields=[
        ScalarField(key="company", label="Company", type=FieldType.STRING, required=True),
        TableField(
            key="items",
            label="Items",
            required=True,
            anchor=TableAnchor(
                strategy=AnchorStrategy.MARKER,
                marker=MarkerAnchor(loop_tokens=["{{items.name}}", "{{items.qty}}"]),
            ),
            columns=[
                TableColumn(key="name", label="Name", type=FieldType.STRING, required=True),
                TableColumn(key="qty", label="Qty", type=FieldType.NUMBER, required=True),
            ],
        ),
    ])


def test_fill_text_scalar_only(scalar_contract):
    engine = TemplateFillEngine(scalar_contract)
    template = b"Hello {{name}}, your amount is {{amount}}"
    values = {"name": "Alice", "amount": "100.50"}
    result = engine.fill(template, values, "test.txt")
    assert result.success is True
    assert b"Hello Alice" in result.content
    assert b"100.50" in result.content
    assert "name" in result.filled_scalars
    assert "amount" in result.filled_scalars


def test_fill_text_missing_required(scalar_contract):
    engine = TemplateFillEngine(scalar_contract)
    template = b"Hello {{name}}, amount {{amount}}"
    values = {"name": "Alice"}  # missing amount
    result = engine.fill(template, values, "test.txt")
    assert result.success is False
    assert "Validation failed" in result.error


def test_fill_text_table_marker_loop(table_contract):
    engine = TemplateFillEngine(table_contract)
    template = b"{{#items}}{{items.name}} {{items.qty}}{{/items}}"
    values = {
        "company": "Acme",
        "items": [
            {"name": "Apple", "qty": 5},
            {"name": "Banana", "qty": 3},
        ]
    }
    result = engine.fill(template, values, "test.txt")
    assert result.success is True
    assert b"Apple 5" in result.content
    assert b"Banana 3" in result.content
    assert "items" in result.filled_tables


def test_fill_text_empty_table(table_contract):
    engine = TemplateFillEngine(table_contract)
    template = b"{{#items}}{{items.name}}{{/items}}"
    values = {"company": "Acme", "items": []}
    result = engine.fill(template, values, "test.txt")
    # Empty table should still succeed, just produce empty content
    assert result.success is True
    assert result.content == b""


def test_validation_unknown_key(scalar_contract):
    engine = TemplateFillEngine(scalar_contract)
    template = b"test"
    values = {"name": "Alice", "amount": 100, "unknown": "value"}
    result = engine.fill(template, values, "test.txt")
    assert result.success is False
    assert "unknown" in result.error


def test_validation_type_mismatch(scalar_contract):
    engine = TemplateFillEngine(scalar_contract)
    template = b"test"
    values = {"name": "Alice", "amount": "not_a_number"}
    result = engine.fill(template, values, "test.txt")
    assert result.success is False
    assert "amount" in result.error.lower() or "number" in result.error.lower()
