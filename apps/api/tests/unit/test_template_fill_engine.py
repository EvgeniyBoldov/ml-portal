"""The fill engine uses only explicit XLSX/XLSM marker rows."""
from __future__ import annotations

import io

import pytest

from app.services.collection.template_contract import (
    AnchorStrategy, MarkerAnchor, ScalarField, TableAnchor, TableColumn, TableField, TemplateContract,
)
from app.services.collection.template_fill_engine import TemplateFillEngine


def _contract() -> TemplateContract:
    return TemplateContract(fields=[
        ScalarField(key="company", label="Company"),
        TableField(
            key="users", label="Users", min_rows=0,
            anchor=TableAnchor(
                sheet="Users", strategy=AnchorStrategy.MARKER,
                marker=MarkerAnchor(
                    row=2,
                    loop_tokens=["{{users[].name}}", "{{users[].login}}"],
                    columns={"{{users[].name}}": 1, "{{users[].login}}": 2},
                ),
            ),
            columns=[TableColumn(key="name", label="Name"), TableColumn(key="login", label="Login")],
        ),
    ])


def _workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Users"
    ws["A1"] = "Имя"
    ws["B1"] = "Логин"
    ws["A2"] = "{{users[].name}}"
    ws["B2"] = "{{users[].login}}"
    ws["D1"] = "Компания: {{company}}"
    ws.row_dimensions[2].height = 31
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_repeats_exact_marker_row_and_preserves_its_style() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    result = TemplateFillEngine(_contract()).fill(
        _workbook(), {"company": "Acme", "users": [{"name": "Анна", "login": "anna"}, {"name": "Борис", "login": "boris"}]}, "users.xlsx"
    )
    assert result.success, result.error
    ws = openpyxl.load_workbook(io.BytesIO(result.content)).active
    assert [ws["A2"].value, ws["B2"].value] == ["Анна", "anna"]
    assert [ws["A3"].value, ws["B3"].value] == ["Борис", "boris"]
    assert ws.row_dimensions[3].height == 31
    assert ws["D1"].value == "Компания: Acme"


def test_missing_optional_table_deletes_technical_marker_row() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    result = TemplateFillEngine(_contract()).fill(_workbook(), {"company": "Acme"}, "users.xlsx")
    assert result.success, result.error
    ws = openpyxl.load_workbook(io.BytesIO(result.content)).active
    assert ws["A1"].value == "Имя"
    assert ws["A2"].value is None
    assert all("{{" not in str(cell.value or "") for row in ws.iter_rows() for cell in row)


def test_missing_optional_scalar_removes_technical_token() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    result = TemplateFillEngine(_contract()).fill(_workbook(), {"users": []}, "users.xlsx")
    assert result.success, result.error
    ws = openpyxl.load_workbook(io.BytesIO(result.content)).active
    assert ws["D1"].value == "Компания: "


def test_non_excel_template_is_rejected() -> None:
    result = TemplateFillEngine(_contract()).fill(b"x", {}, "users.docx")
    assert not result.success
    assert "xlsx" in str(result.error)
