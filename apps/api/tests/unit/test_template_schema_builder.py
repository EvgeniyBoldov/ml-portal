"""Tests for TemplateSchemaBuilder (S2)."""
from __future__ import annotations
import pytest
from app.services.collection.template_contract import FieldKind, FieldSource, TemplateContract, ScalarField, FieldType
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
            TokenOccurrence(token="author.email", table_prefix=None, column_key=None, location={}),
        ],
        scalar_keys=["name", "author.email"],
        table_prefixes=[],
        table_regions=[],
        text_lines=["Form", "{{name}} {{author.email}}"],
    )


@pytest.fixture
def table_layout():
    return RawLayout(
        format="excel", title="Items", version="1.0",
        tokens=[
            TokenOccurrence(
                token="items.name",
                table_prefix="items",
                column_key="name",
                location={"sheet": "Sheet1"},
                segments=[
                    {"key": "items", "params": {"name": "Items", "min": 1, "max": 5}, "repeat": True},
                    {"key": "name", "params": {"name": "Item Name"}, "repeat": False},
                ],
            ),
            TokenOccurrence(
                token="items.qty",
                table_prefix="items",
                column_key="qty",
                location={"sheet": "Sheet1"},
                hint_type="int",
                hint_args="10",
                segments=[
                    {"key": "items", "params": {"name": "Items", "min": 1, "max": 5}, "repeat": True},
                    {"key": "qty", "params": {"name": "Quantity", "required": True}, "repeat": False},
                ],
            ),
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
    assert contract.scalar_fields()[1].key == "author.email"
    assert contract.scalar_fields()[0].source == FieldSource.PARSER
    assert contract.scalar_fields()[0].required is False
    dumped = contract.to_jsonb()
    assert dumped["fields"][1]["key"] == "author"
    assert dumped["fields"][1]["kind"] == "object"
    assert dumped["fields"][1]["fields"][0]["key"] == "email"


@pytest.mark.asyncio
async def test_heuristic_table(builder, table_layout):
    contract = await builder.build(table_layout)
    assert len(contract.table_fields()) == 1
    tf = contract.table_fields()[0]
    assert tf.key == "items"
    assert tf.label == "Items"
    assert len(tf.columns) == 2
    assert tf.columns[0].key == "name"
    assert tf.columns[1].key == "qty"
    assert tf.columns[0].label == "Item Name"
    assert tf.columns[1].label == "Quantity"
    assert tf.source == FieldSource.PARSER
    assert tf.required is False
    assert tf.min_rows == 1
    assert tf.max_rows == 5
    assert tf.columns[0].required is False
    assert tf.columns[1].required is True
    dumped = contract.to_jsonb()
    assert dumped["fields"][0]["key"] == "items"
    assert dumped["fields"][0]["kind"] == "table"
    assert [field["key"] for field in dumped["fields"][0]["fields"]] == ["name", "qty"]


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


@pytest.mark.asyncio
async def test_structural_region_fallback_creates_table(builder):
    layout = RawLayout(
        format="excel",
        title="Sheet",
        version=None,
        tokens=[],
        scalar_keys=[],
        table_prefixes=[],
        table_regions=[
            TableRegion(
                region_id="Sheet1:structural:r1-3",
                location={"sheet": "Sheet1", "row_start": 1, "row_end": 3, "col_start": 1, "col_end": 2},
                loop_tokens=[],
                loop_prefix=None,
                header_row=["Name", "Qty"],
            ),
        ],
        text_lines=["Name Qty"],
    )

    contract = await builder.build(layout)

    assert len(contract.table_fields()) == 1
    table = contract.table_fields()[0]
    assert table.key == "table_1"
    assert [column.key for column in table.columns] == ["name", "qty"]
    assert table.source == FieldSource.PARSER


@pytest.mark.asyncio
async def test_typed_placeholder_infers_number(builder):
    layout = RawLayout(
        format="text",
        title="Form",
        version=None,
        tokens=[
            TokenOccurrence(
                token="author.tel",
                table_prefix=None,
                column_key=None,
                location={},
                placeholder="{{author.tel:int(10)}}",
                hint_type="int",
                hint_args="10",
            )
        ],
        scalar_keys=["author.tel"],
        table_prefixes=[],
        table_regions=[],
        text_lines=["{{author.tel:int(10)}}"],
    )

    contract = await builder.build(layout)

    field = contract.get_field("author.tel")
    assert field is not None
    assert field.type == FieldType.NUMBER
    assert field.description is None


@pytest.mark.asyncio
async def test_segment_metadata_drives_labels_and_enums(builder):
    layout = RawLayout(
        format="text",
        title="Form",
        version=None,
        tokens=[
            TokenOccurrence(
                token="author.name",
                table_prefix=None,
                column_key=None,
                location={},
                segments=[
                    {"key": "author", "params": {"name": "Author"}, "repeat": False},
                    {"key": "name", "params": {"name": "Full name", "required": True}, "repeat": False},
                ],
            ),
            TokenOccurrence(
                token="items.traffic",
                table_prefix="items",
                column_key="traffic",
                location={},
                segments=[
                    {"key": "items", "params": {"name": "Items", "description": "Traffic rows"}, "repeat": True},
                    {"key": "traffic", "params": {"name": "Traffic", "choice": ["tcp", "udp"]}, "repeat": False},
                ],
            ),
        ],
        scalar_keys=["author.name"],
        table_prefixes=["items"],
        table_regions=[
            TableRegion(
                region_id="text:marker:items",
                location={"type": "inline", "key": "items"},
                loop_tokens=["{{items[].traffic}}"],
                loop_prefix="items",
            )
        ],
        text_lines=[],
    )

    contract = await builder.build(layout)

    author = contract.get_field("author.name")
    items = contract.get_field("items")
    assert author is not None
    assert author.label == "Full name"
    assert author.required is True
    assert items is not None
    assert items.label == "Items"
    assert items.description == "Traffic rows"
    assert items.columns[0].label == "Traffic"
    assert items.columns[0].type == FieldType.ENUM
    assert items.columns[0].enum == ["tcp", "udp"]
