"""Tests for TemplateDescriptionBuilder (S3)."""
from __future__ import annotations
import pytest
from app.services.collection.template_contract import ScalarField, TableField, TableColumn, TemplateContract, FieldType
from app.services.collection.template_description_builder import TemplateDescriptionBuilder


class FakeLLM:
    def __init__(self, response: str = "", fail: bool = False):
        self.response = response
        self.fail = fail
    async def chat(self, messages, *, params=None):
        if self.fail:
            raise RuntimeError("fail")
        return {"content": self.response}


@pytest.fixture
def simple_contract():
    return TemplateContract(fields=[
        ScalarField(key="name", label="Name", type=FieldType.STRING, required=True),
        ScalarField(key="email", label="Email", type=FieldType.STRING, required=False),
    ])


@pytest.fixture
def table_contract():
    return TemplateContract(fields=[
        ScalarField(key="company", label="Company", type=FieldType.STRING, required=True),
        TableField(
            key="items", label="Items", required=True,
            columns=[
                TableColumn(key="name", label="Item", type=FieldType.STRING, required=True),
                TableColumn(key="qty", label="Qty", type=FieldType.NUMBER, required=True),
            ]
        ),
    ])


@pytest.mark.asyncio
async def test_deterministic_simple(simple_contract):
    builder = TemplateDescriptionBuilder(llm=None)
    desc = await builder.build(simple_contract, title="Contact Form")
    assert "Contact Form" in desc
    assert "Name" in desc
    assert "Email" in desc


@pytest.mark.asyncio
async def test_deterministic_with_version(simple_contract):
    builder = TemplateDescriptionBuilder(llm=None)
    desc = await builder.build(simple_contract, title="Invoice", version="2.0")
    assert "Invoice" in desc
    assert "2.0" in desc


@pytest.mark.asyncio
async def test_deterministic_table(table_contract):
    builder = TemplateDescriptionBuilder(llm=None)
    desc = await builder.build(table_contract, title="Sales Order")
    assert "Sales Order" in desc
    assert "Company" in desc
    assert "Items" in desc or "Item" in desc


@pytest.mark.asyncio
async def test_llm_success(simple_contract):
    builder = TemplateDescriptionBuilder(llm=FakeLLM(response="A simple contact form for customers."))
    desc = await builder.build(simple_contract, title="Contact Form")
    assert "contact form" in desc.lower()


@pytest.mark.asyncio
async def test_llm_failure_fallback(simple_contract):
    builder = TemplateDescriptionBuilder(llm=FakeLLM(fail=True))
    desc = await builder.build(simple_contract, title="Invoice")
    assert "Invoice" in desc
    assert "Name" in desc
