"""Unit tests for TemplateAnalyzeService."""
from __future__ import annotations

import pytest

from app.services.collection.template_analyze_service import TemplateAnalyzeService


@pytest.fixture
def service():
    return TemplateAnalyzeService()


def test_analyze_text_plain(service):
    content = b"Hello {{name}}, your code is {{code}}."
    result = service.analyze_bytes(content, "greeting.txt")

    assert result["title"] == "greeting"
    assert result["kind_hint"] == "text"
    assert result["draft_schema"] is not None
    fields = {f["name"] for f in result["draft_schema"]["fields"]}
    assert "name" in fields
    assert "code" in fields


def test_analyze_text_with_version(service):
    content = b"Template v2.1\nUser: {{user}}"
    result = service.analyze_bytes(content, "report.txt")

    assert result["version"] == "2.1"
    assert "user" in {f["name"] for f in result["draft_schema"]["fields"]}


def test_analyze_text_no_placeholders(service):
    content = b"Just a static text file."
    result = service.analyze_bytes(content, "static.txt")

    assert result["title"] == "static"
    assert result["draft_schema"] is None
    assert result["version"] is None


def test_analyze_excel_mocked(service, monkeypatch):
    """Smoke-test that Excel path is reachable when openpyxl is present."""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl not installed")

    import io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Name"
    ws["B1"] = "Value"
    ws["A2"] = "{{name}}"
    ws["B2"] = "{{amount}}"
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()

    result = service.analyze_bytes(buf.getvalue(), "data.xlsx")
    assert result["kind_hint"] == "excel"
    assert result["draft_schema"] is not None
    fields = {f["name"] for f in result["draft_schema"]["fields"]}
    assert "name" in fields
    assert "amount" in fields


def test_analyze_word_mocked(service, monkeypatch):
    """Smoke-test that Word path is reachable when python-docx is present."""
    try:
        import docx
    except ImportError:
        pytest.skip("python-docx not installed")

    import io
    doc = docx.Document()
    doc.add_paragraph("Hello {{customer}}")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "{{item}}"
    table.rows[0].cells[1].text = "{{price}}"
    buf = io.BytesIO()
    doc.save(buf)

    result = service.analyze_bytes(buf.getvalue(), "letter.docx")
    assert result["kind_hint"] == "word"
    assert result["draft_schema"] is not None
    fields = {f["name"] for f in result["draft_schema"]["fields"]}
    assert "customer" in fields
    assert "item" in fields
    assert "price" in fields
