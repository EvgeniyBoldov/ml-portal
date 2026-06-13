"""Tests for TemplateSchemaBuilder (S2)."""
from __future__ import annotations
import pytest
from app.services.collection.template_contract import FieldKind, FieldSource, TemplateContract
from app.services.collection.template_layout_parser import RawLayout, TokenOccurrence, TableRegion
from app.services.collection.template_schema_builder import TemplateSchemaBuilder


class FakeLLM:
    def __init__(self, response: dict | None = None, fail: bool = False):
        self.response = response
        self.fail = fail
    async def chat(self, messages, *, params=None):
        if self.fail:
            raise RuntimeError("fail")
        return {"content": self.response}


@pytest.fixture
def builder():
    return TemplateSchemaBuilder(llm=None)


@pytest.fixture
def scalar_layout():
    return RawLayout(
        format="text", title="Test", version=None,
        tokens=[
            TokenOccurrence(token="name", table_prefix=None, column_key=None, location={}),
            TokenOccurrence(token="email", table_prefix=None, column_key=None, location={}),
        ],
        scalar_keys=["name", "email"],
        table_prefixes=[],
        table_regions=[],
        text_lines=["Form", "{{name}} {{email}}"],
    )


@pytest.fixture
def table_layout():
    return RawLayout(
        format="excel", title="Items", version="1.0",
        tokens=[
            TokenOccurrence(token="items.name", table_prefix="items", column_key="name", location={"sheet": "Sheet1"}),
            TokenOccurrence(token="items.qty", table_prefix="items", column_key="qty", location={"sheet": "Sheet1"}),
        ],
        scalar_keys=[],
        table_prefixes=["items"],
        table_regions=[
            TableRegion(
                region_id="Sheet1:marker:items",
                location={"sheet": "Sheet1", "marker_row": 2, "col_start": 1, "col_end": 2},
                loop_tokens=["{{items.name}}", "{{items.qty}}"],
                loop_prefix="items",
                header_row=["Name", "Qty"],
            ),
        ],
        text_lines=["Items v1.0", "Name Qty", "{{items.name}} {{items.qty}}"],
    )


@pytest.mark.asyncio
async def test_heuristic_scalars(builder, scalar_layout):
    contract = await builder.build(scalar_layout)
    assert len(contract.scalar_fields()) == 2
    assert contract.scalar_fields()[0].key == "name"
    assert contract.scalar_fields()[0].source == FieldSource.PARSER


@pytest.mark.asyncio
async def test_heuristic_table(builder, table_layout):
    contract = await builder.build(table_layout)
    assert len(contract.table_fields()) == 1
    tf = contract.table_fields()[0]
    assert tf.key == "items"
    assert len(tf.columns) == 2
    assert tf.columns[0].key == "name"
    assert tf.columns[1].key == "qty"
    assert tf.source == FieldSource.PARSER


@pytest.mark.asyncio
async def test_merge_with_existing_preserves_locked(scalar_layout):
    existing = TemplateContract(fields=[
        ScalarField(key="name", label="Old", type=FieldType.STRING, required=True, locked=True, source=FieldSource.ADMIN),
    ])
    builder = TemplateSchemaBuilder(llm=None)
    merged = await builder.build(scalar_layout, existing_contract=existing)
    assert merged.get_field("name").label == "Old"
    assert merged.get_field("name").locked is True


@pytest.mark.asyncio
async def test_llm_success(table_layout):
    llm_response = {
        "fields": [
            {"key": "items", "kind": "table", "label": "Positions", "columns": [
                {"key": "name", "label": "Item Name", "type": "string", "required": True},
                {"key": "qty", "label": "Quantity", "type": "number", "required": True},
            ]},
        ]
    }
    builder = TemplateSchemaBuilder(llm=FakeLLM(response=llm_response))
    contract = await builder.build(table_layout)
    assert len(contract.table_fields()) == 1
    assert contract.table_fields()[0].label == "Positions"


@pytest.mark.asyncio
async def test_llm_failure_fallback_to_heuristic(table_layout):
    builder = TemplateSchemaBuilder(llm=FakeLLM(fail=True))
    contract = await builder.build(table_layout)
    assert len(contract.table_fields()) == 1
    assert contract.table_fields()[0].source == FieldSource.PARSER
