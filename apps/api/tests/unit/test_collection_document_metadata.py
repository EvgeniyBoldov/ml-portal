import pytest

from app.core.exceptions import CollectionDocumentUploadError
from app.models.collection import FieldType
from app.services.collection_document_ingest_service import CollectionDocumentUploadService


class _Collection:
    fields = [
        {"name": "priority", "data_type": FieldType.INTEGER.value, "required": True},
        {"name": "active", "data_type": FieldType.BOOLEAN.value, "required": False},
        {"name": "category", "data_type": FieldType.ENUM.value, "options": ["a", "b"]},
        {"name": "labels", "data_type": FieldType.JSON.value},
    ]


def test_document_metadata_is_typed_before_upload():
    result = CollectionDocumentUploadService._validate_document_metadata(
        _Collection(), {"priority": "7", "active": "true", "category": "a", "labels": ["x"]}
    )
    assert result == {"priority": 7, "active": True, "category": "a", "labels": ["x"]}


@pytest.mark.parametrize(
    "payload",
    [
        {"priority": 1, "unknown": "x"},
        {"priority": "not-an-int"},
        {"priority": 1, "active": "yes"},
        {"priority": 1, "category": "other"},
    ],
)
def test_document_metadata_rejects_invalid_contract(payload):
    with pytest.raises(CollectionDocumentUploadError):
        CollectionDocumentUploadService._validate_document_metadata(_Collection(), payload)
