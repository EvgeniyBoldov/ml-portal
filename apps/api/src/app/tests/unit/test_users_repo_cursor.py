"""
Unit tests for AsyncUsersRepository cursor encoding/decoding
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.repositories.users_repo import AsyncUsersRepository


class TestAsyncUsersRepositoryCursor:
    """Test cursor encoding/decoding functionality"""

    @pytest.fixture
    def users_repo(self):
        """Create AsyncUsersRepository with mock session"""
        mock_session = MagicMock()
        return AsyncUsersRepository(mock_session)

    def test_encode_cursor_basic(self, users_repo):
        """Test basic cursor encoding"""
        data = {
            "created_at": "2024-01-01T12:00:00+00:00",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        
        cursor = users_repo._encode_cursor(data)
        
        # Should be base64 encoded
        assert isinstance(cursor, str)
        assert len(cursor) > 0
        
        # Should be decodable
        decoded = users_repo._decode_cursor(cursor)
        assert decoded["created_at"] == datetime.fromisoformat("2024-01-01T12:00:00+00:00")
        assert decoded["id"] == uuid.UUID("123e4567-e89b-12d3-a456-426614174000")

    def test_decode_cursor_basic(self, users_repo):
        """Test basic cursor decoding"""
        data = {
            "created_at": "2024-01-01T12:00:00+00:00",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        
        cursor = users_repo._encode_cursor(data)
        decoded = users_repo._decode_cursor(cursor)
        
        assert isinstance(decoded["created_at"], datetime)
        assert isinstance(decoded["id"], uuid.UUID)
        assert decoded["created_at"].isoformat() == "2024-01-01T12:00:00+00:00"
        assert str(decoded["id"]) == "123e4567-e89b-12d3-a456-426614174000"

    def test_decode_cursor_with_z_suffix(self, users_repo):
        """Test cursor decoding with Z suffix"""
        data = {
            "created_at": "2024-01-01T12:00:00Z",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        
        cursor = users_repo._encode_cursor(data)
        decoded = users_repo._decode_cursor(cursor)
        
        assert isinstance(decoded["created_at"], datetime)
        assert decoded["created_at"].isoformat() == "2024-01-01T12:00:00+00:00"

    def test_decode_cursor_invalid_base64(self, users_repo):
        """Test cursor decoding with invalid base64"""
        with pytest.raises(ValueError, match="invalid_cursor"):
            users_repo._decode_cursor("invalid_base64!")

    def test_decode_cursor_invalid_json(self, users_repo):
        """Test cursor decoding with invalid JSON"""
        import base64
        invalid_json = base64.b64encode(b"invalid json").decode()
        
        with pytest.raises(ValueError, match="invalid_cursor"):
            users_repo._decode_cursor(invalid_json)

    def test_decode_cursor_missing_fields(self, users_repo):
        """Test cursor decoding with missing required fields"""
        import base64
        import json
        
        incomplete_data = {"created_at": "2024-01-01T12:00:00Z"}
        cursor = base64.b64encode(json.dumps(incomplete_data).encode()).decode()
        
        with pytest.raises(ValueError, match="invalid_cursor"):
            users_repo._decode_cursor(cursor)

    def test_decode_cursor_invalid_uuid(self, users_repo):
        """Test cursor decoding with invalid UUID"""
        import base64
        import json
        
        invalid_data = {
            "created_at": "2024-01-01T12:00:00Z",
            "id": "not-a-uuid"
        }
        cursor = base64.b64encode(json.dumps(invalid_data).encode()).decode()
        
        with pytest.raises(ValueError, match="invalid_cursor"):
            users_repo._decode_cursor(cursor)

    def test_decode_cursor_invalid_datetime(self, users_repo):
        """Test cursor decoding with invalid datetime"""
        import base64
        import json
        
        invalid_data = {
            "created_at": "not-a-datetime",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        cursor = base64.b64encode(json.dumps(invalid_data).encode()).decode()
        
        with pytest.raises(ValueError, match="invalid_cursor"):
            users_repo._decode_cursor(cursor)

    def test_cursor_roundtrip_complex(self, users_repo):
        """Test cursor roundtrip with complex data"""
        test_cases = [
            {
                "created_at": "2024-01-01T12:00:00.123456+00:00",
                "id": "123e4567-e89b-12d3-a456-426614174000"
            },
            {
                "created_at": "2024-12-31T23:59:59.999999Z",
                "id": "00000000-0000-0000-0000-000000000000"
            },
            {
                "created_at": "2023-06-15T08:30:45.000000+05:30",
                "id": "ffffffff-ffff-ffff-ffff-ffffffffffff"
            }
        ]
        
        for original_data in test_cases:
            cursor = users_repo._encode_cursor(original_data)
            decoded = users_repo._decode_cursor(cursor)
            
            # Re-encode to verify consistency
            reencoded_cursor = users_repo._encode_cursor({
                "created_at": decoded["created_at"].isoformat(),
                "id": str(decoded["id"])
            })
            
            # Note: cursor may differ due to timezone format normalization
            # but the decoded data should be equivalent
            expected_datetime = datetime.fromisoformat(original_data["created_at"].replace('Z', '+00:00'))
            assert decoded["created_at"] == expected_datetime
            assert str(decoded["id"]) == original_data["id"]

    def test_cursor_with_timezone_handling(self, users_repo):
        """Test cursor handling with different timezones"""
        # Test with UTC
        utc_data = {
            "created_at": "2024-01-01T12:00:00+00:00",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        cursor = users_repo._encode_cursor(utc_data)
        decoded = users_repo._decode_cursor(cursor)
        assert decoded["created_at"].tzinfo is not None
        
        # Test with different timezone
        tz_data = {
            "created_at": "2024-01-01T12:00:00+05:30",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        cursor = users_repo._encode_cursor(tz_data)
        decoded = users_repo._decode_cursor(cursor)
        assert decoded["created_at"].tzinfo is not None
