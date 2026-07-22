"""Deterministic parsing of XLSX/XLSM technical anchors."""
from __future__ import annotations

import io

import pytest

from app.services.collection.template_layout_parser import TemplateLayoutParser


def _excel(*, marker: bool = True) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Пользователи"
    ws["A1"] = "Имя"
    ws["B1"] = "Логин"
    ws["D1"] = "Компания: {{company(name='Компания')}}"
    if marker:
        ws["A2"] = "{{users(name='Пользователи')[].name(name='Имя')}}"
        ws["B2"] = "{{users[].login(name='Логин')}}"
    else:
        ws["A2"] = "Анна"
        ws["B2"] = "anna"
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_parses_scalar_and_exact_marker_location() -> None:
    layout = TemplateLayoutParser().parse(_excel(), "users.xlsx")
    assert layout.format == "excel"
    assert {token.token for token in layout.tokens} == {"company", "users.name", "users.login"}
    region = layout.table_regions[0]
    assert region.loop_prefix == "users"
    assert region.location == {"sheet": "Пользователи", "marker_row": 2, "col_start": 1, "col_end": 2}
    assert region.marker_columns["{{users(name='Пользователи')[].name(name='Имя')}}"] == 1
    assert region.marker_columns["{{users[].login(name='Логин')}}"] == 2


def test_headers_without_markers_are_not_a_table() -> None:
    layout = TemplateLayoutParser().parse(_excel(marker=False), "users.xlsx")
    assert layout.table_regions == []


@pytest.mark.parametrize("filename", ["legacy.xls", "letter.docx", "form.txt", "data.csv"])
def test_rejects_non_excel_template_formats(filename: str) -> None:
    with pytest.raises(ValueError, match="Only .xlsx and .xlsm"):
        TemplateLayoutParser().parse(b"not an excel file", filename)
