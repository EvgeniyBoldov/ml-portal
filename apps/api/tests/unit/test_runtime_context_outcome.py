from __future__ import annotations

from app.runtime.context_outcome import _verified_artifacts


def test_verified_artifact_projection_normalizes_legacy_reference_shape() -> None:
    artifacts = _verified_artifacts({
        "verified": {
            "artifact_refs": [{
                "artifact_ref": "artifact-1", "name": "report.xlsx",
                "content_type": "application/vnd.ms-excel", "size_bytes": 42,
            }],
        },
        "artifacts": [{"artifact_id": "unverified-and-ignored"}],
    })

    assert artifacts == [{
        "artifact_id": "artifact-1", "file_name": "report.xlsx",
        "content_type": "application/vnd.ms-excel", "size_bytes": 42,
        "role": "generated",
    }]
