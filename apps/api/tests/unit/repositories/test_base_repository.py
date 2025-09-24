"""
Unit tests for base repository
"""
import pytest
from unittest.mock import Mock, patch
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.repositories._base import BaseRepository, AsyncBaseRepository
from app.models.user import Users


class TestBaseRepository:
    """Test base repository functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repository = BaseRepository(self.mock_session, Users)
        
        # Mock user instance
        self.mock_user = Mock(spec=Users)
        self.mock_user.id = "user123"
        self.mock_user.login = "testuser"
        self.mock_user.email = "test@example.com"
        self.mock_user.created_at = datetime.now()
    
    def test_create_success(self):
        """Test successful record creation"""
        user_data = {
            "login": "newuser",
            "email": "newuser@example.com",
            "role": "reader"
        }
        
        with patch.object(self.repository, 'model', Users) as mock_model:
            # Setup mocks
            mock_model.return_value = self.mock_user
            self.mock_session.add.return_value = None
            self.mock_session.flush.return_value = None
            self.mock_session.refresh.return_value = None
            
            # Call function
            result = self.repository.create(**user_data)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_model.assert_called_once_with(**user_data)
            self.mock_session.add.assert_called_once_with(self.mock_user)
            self.mock_session.flush.assert_called_once()
            self.mock_session.refresh.assert_called_once_with(self.mock_user)
    
    def test_create_integrity_error(self):
        """Test record creation with integrity error"""
        user_data = {
            "login": "newuser",
            "email": "newuser@example.com",
            "role": "reader"
        }
        
        with patch.object(self.repository, 'model') as mock_model:
            # Setup mocks
            mock_model.return_value = self.mock_user
            self.mock_session.add.side_effect = IntegrityError("statement", "params", "orig")
            
            # Call function and expect exception
            with pytest.raises(IntegrityError):
                self.repository.create(**user_data)
            
            # Verify rollback was called
            self.mock_session.rollback.assert_called_once()
    
    def test_create_general_error(self):
        """Test record creation with general error"""
        user_data = {
            "login": "newuser",
            "email": "newuser@example.com",
            "role": "reader"
        }
        
        with patch.object(self.repository, 'model') as mock_model:
            # Setup mocks
            mock_model.return_value = self.mock_user
            self.mock_session.add.side_effect = Exception("Database error")
            
            # Call function and expect exception
            with pytest.raises(Exception):
                self.repository.create(**user_data)
            
            # Verify rollback was called
            self.mock_session.rollback.assert_called_once()
    
    def test_get_by_id_success(self):
        """Test successful get by ID"""
        user_id = "user123"
        
        # Setup mocks
        self.mock_session.get.return_value = self.mock_user
        
        # Call function
        result = self.repository.get_by_id(user_id)
        
        # Assertions
        assert result == self.mock_user
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
    
    def test_get_by_id_not_found(self):
        """Test get by ID when record not found"""
        user_id = "nonexistent"
        
        # Setup mocks
        self.mock_session.get.return_value = None
        
        # Call function
        result = self.repository.get_by_id(user_id)
        
        # Assertions
        assert result is None
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
    
    def test_get_by_id_error(self):
        """Test get by ID with error"""
        user_id = "user123"
        
        # Setup mocks
        self.mock_session.get.side_effect = Exception("Database error")
        
        # Call function
        result = self.repository.get_by_id(user_id)
        
        # Assertions
        assert result is None
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
    
    def test_get_by_field_success(self):
        """Test successful get by field"""
        field_name = "login"
        field_value = "testuser"
        
        # Setup mocks
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = self.mock_user
        self.mock_session.query.return_value = mock_query
        
        # Call function
        result = self.repository.get_by_field(field_name, field_value)
        
        # Assertions
        assert result == self.mock_user
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
        mock_query.filter.assert_called_once()
        mock_query.filter.return_value.first.assert_called_once()
    
    def test_get_by_field_not_found(self):
        """Test get by field when record not found"""
        field_name = "login"
        field_value = "nonexistent"
        
        # Setup mocks
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        self.mock_session.query.return_value = mock_query
        
        # Call function
        result = self.repository.get_by_field(field_name, field_value)
        
        # Assertions
        assert result is None
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
        mock_query.filter.assert_called_once()
        mock_query.filter.return_value.first.assert_called_once()
    
    def test_get_by_field_error(self):
        """Test get by field with error"""
        field_name = "login"
        field_value = "testuser"
        
        # Setup mocks
        self.mock_session.query.side_effect = Exception("Database error")
        
        # Call function
        result = self.repository.get_by_field(field_name, field_value)
        
        # Assertions
        assert result is None
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
    
    def test_get_all_success(self):
        """Test successful get all records"""
        mock_users = [self.mock_user]
        
        # Setup mocks
        mock_query = Mock()
        mock_query.all.return_value = mock_users
        self.mock_session.query.return_value = mock_query
        
        # Call function
        result = self.repository.get_all()
        
        # Assertions
        assert result == mock_users
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
        mock_query.all.assert_called_once()
    
    def test_get_all_error(self):
        """Test get all with error"""
        # Setup mocks
        self.mock_session.query.side_effect = Exception("Database error")
        
        # Call function
        result = self.repository.get_all()
        
        # Assertions
        assert result == []
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
    
    def test_update_success(self):
        """Test successful record update"""
        user_id = "user123"
        update_data = {"email": "updated@example.com"}
        
        # Setup mocks
        self.mock_session.get.return_value = self.mock_user
        self.mock_session.flush.return_value = None
        self.mock_session.refresh.return_value = None
        
        # Call function
        result = self.repository.update(user_id, **update_data)
        
        # Assertions
        assert result == self.mock_user
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
        self.mock_session.flush.assert_called_once()
        self.mock_session.refresh.assert_called_once_with(self.mock_user)
    
    def test_update_not_found(self):
        """Test update when record not found"""
        user_id = "nonexistent"
        update_data = {"email": "updated@example.com"}
        
        # Setup mocks
        self.mock_session.get.return_value = None
        
        # Call function
        result = self.repository.update(user_id, **update_data)
        
        # Assertions
        assert result is None
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
    
    def test_delete_success(self):
        """Test successful record deletion"""
        user_id = "user123"
        
        # Setup mocks
        self.mock_session.get.return_value = self.mock_user
        self.mock_session.delete.return_value = None
        self.mock_session.flush.return_value = None
        
        # Call function
        result = self.repository.delete(user_id)
        
        # Assertions
        assert result is True
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
        self.mock_session.delete.assert_called_once_with(self.mock_user)
        self.mock_session.flush.assert_called_once()
    
    def test_delete_not_found(self):
        """Test delete when record not found"""
        user_id = "nonexistent"
        
        # Setup mocks
        self.mock_session.get.return_value = None
        
        # Call function
        result = self.repository.delete(user_id)
        
        # Assertions
        assert result is False
        
        # Verify calls
        self.mock_session.get.assert_called_once_with(Users, user_id)
    
    def test_count_success(self):
        """Test successful count"""
        expected_count = 5
        
        # Setup mocks
        mock_query = Mock()
        mock_query.count.return_value = expected_count
        self.mock_session.query.return_value = mock_query
        
        # Call function
        result = self.repository.count()
        
        # Assertions
        assert result == expected_count
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
        mock_query.count.assert_called_once()
    
    def test_count_error(self):
        """Test count with error"""
        # Setup mocks
        self.mock_session.query.side_effect = Exception("Database error")
        
        # Call function
        result = self.repository.count()
        
        # Assertions
        assert result == 0
        
        # Verify calls
        self.mock_session.query.assert_called_once_with(Users)
