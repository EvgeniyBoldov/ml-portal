from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import CSVValidationError
from app.services.collection_csv_service import CollectionCSVService


def _collection() -> SimpleNamespace:
    return SimpleNamespace(
        fields=[
            {
                "name": "title",
                "data_type": "text",
                "required": True,
            },
            {
                "name": "priority",
                "data_type": "integer",
                "required": False,
            },
        ]
    )


def test_parse_csv_valid_rows_and_types():
    service = CollectionCSVService(_collection())

    valid_rows, errors = service.parse_csv(
        b"title,priority\nAlpha,1\nBeta,2\n",
    )

    assert errors == []
    assert valid_rows == [
        {"title": "Alpha", "priority": 1},
        {"title": "Beta", "priority": 2},
    ]


def test_parse_csv_missing_required_column_raises():
    service = CollectionCSVService(_collection())

    with pytest.raises(CSVValidationError, match="Missing required columns: title"):
        service.parse_csv(b"priority\n1\n")


def test_preview_csv_reports_columns_and_samples():
    service = CollectionCSVService(_collection())

    preview = service.preview_csv(
        b"title,priority,extra\nAlpha,1,ignored\nBeta,2,ignored\n",
        max_rows=1,
    )

    assert preview["columns"] == ["title", "priority", "extra"]
    assert preview["matched_columns"] == ["priority", "title"]
    assert preview["unmatched_columns"] == ["extra"]
    assert preview["missing_required"] == []
    assert preview["sample_rows"] == [{"title": "Alpha", "priority": "1"}]
    assert preview["total_rows"] == 2
