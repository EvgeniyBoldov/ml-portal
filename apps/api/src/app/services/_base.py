"""
Base service classes with common functionality
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, TypeVar, Generic
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories._base import BaseRepository, AsyncBaseRepository

logger = get_logger(__name__)

T = TypeVar('T')

class BaseService(ABC):
    """Base service class with common functionality"""
    
    def __init__(self, session: Session):
        self.session = session
        self.logger = get_logger(self.__class__.__name__)
    
    def _generate_id(self) -> str:
        """Generate a new UUID string"""
        return str(uuid.uuid4())
    
    def _get_current_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(timezone.utc)
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]) -> None:
        """Validate that required fields are present"""
        missing_fields = [field for field in required_fields if field not in data or data[field] is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
    
    def _sanitize_string(self, value: str, max_length: Optional[int] = None) -> str:
        """Sanitize string input"""
        if not isinstance(value, str):
            value = str(value)
        
        # Remove leading/trailing whitespace
        value = value.strip()
        
        # Truncate if too long
        if max_length and len(value) > max_length:
            value = value[:max_length]
            self.logger.warning(f"String truncated to {max_length} characters")
        
        return value
    
    def _validate_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_uuid(self, value: str) -> bool:
        """Validate UUID format"""
        try:
            uuid.UUID(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _log_operation(self, operation: str, entity_id: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log service operation"""
        log_data = {
            "operation": operation,
            "entity_id": entity_id,
            "service": self.__class__.__name__
        }
        if details:
            log_data.update(details)
        
        self.logger.info(f"Service operation: {operation}", extra=log_data)
    
    def _handle_error(self, operation: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Handle and log service errors"""
        error_data = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "service": self.__class__.__name__
        }
        if context:
            # Filter out keys that conflict with LogRecord attributes
            filtered_context = {k: v for k, v in context.items() 
                              if k not in ["name", "message", "asctime", "levelname", "levelno", "pathname", "filename", "module", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process", "getMessage", "exc_info", "exc_text", "stack_info"]}
            error_data.update(filtered_context)
        
        self.logger.error(f"Service error in {operation}: {error}", extra=error_data)


class AsyncBaseService(ABC):
    """Async base service class"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = get_logger(self.__class__.__name__)
    
    def _generate_id(self) -> str:
        """Generate a new UUID string"""
        return str(uuid.uuid4())
    
    def _get_current_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(timezone.utc)
    
    def _validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]) -> None:
        """Validate that required fields are present"""
        missing_fields = [field for field in required_fields if field not in data or data[field] is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
    
    def _sanitize_string(self, value: str, max_length: Optional[int] = None) -> str:
        """Sanitize string input"""
        if not isinstance(value, str):
            value = str(value)
        
        value = value.strip()
        
        if max_length and len(value) > max_length:
            value = value[:max_length]
            self.logger.warning(f"String truncated to {max_length} characters")
        
        return value
    
    def _validate_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_uuid(self, value: str) -> bool:
        """Validate UUID format"""
        try:
            uuid.UUID(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _log_operation(self, operation: str, entity_id: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log service operation"""
        log_data = {
            "operation": operation,
            "entity_id": entity_id,
            "service": self.__class__.__name__
        }
        if details:
            log_data.update(details)
        
        self.logger.info(f"Service operation: {operation}", extra=log_data)
    
    def _handle_error(self, operation: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Handle and log service errors"""
        error_data = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "service": self.__class__.__name__
        }
        if context:
            # Filter out keys that conflict with LogRecord attributes
            filtered_context = {k: v for k, v in context.items() 
                              if k not in ["name", "message", "asctime", "levelname", "levelno", "pathname", "filename", "module", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process", "getMessage", "exc_info", "exc_text", "stack_info"]}
            error_data.update(filtered_context)
        
        self.logger.error(f"Service error in {operation}: {error}", extra=error_data)


class RepositoryService(BaseService, Generic[T]):
    """Service that wraps a repository with business logic"""
    
    def __init__(self, session: Session, repository: BaseRepository[T]):
        super().__init__(session)
        self.repository = repository
    
    def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by ID with validation"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            entity = self.repository.get_by_id(entity_id)
            if entity:
                self._log_operation("get_by_id", entity_id)
            return entity
        except Exception as e:
            self._handle_error("get_by_id", e, {"entity_id": entity_id})
            raise
    
    def create(self, data: Dict[str, Any]) -> T:
        """Create entity with validation and business logic"""
        try:
            # Validate required fields
            required_fields = self._get_required_fields()
            self._validate_required_fields(data, required_fields)
            
            # Apply business logic
            processed_data = self._process_create_data(data)
            
            # Create entity
            entity = self.repository.create(**processed_data)
            
            self._log_operation("create", str(entity.id), {"data_keys": list(data.keys())})
            return entity
        except Exception as e:
            self._handle_error("create", e, {"data_keys": list(data.keys())})
            raise
    
    def update(self, entity_id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update entity with validation and business logic"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            # Check if entity exists
            existing_entity = self.repository.get_by_id(entity_id)
            if not existing_entity:
                return None
            
            # Apply business logic
            processed_data = self._process_update_data(data, existing_entity)
            
            # Update entity
            entity = self.repository.update(entity_id, **processed_data)
            
            if entity:
                self._log_operation("update", entity_id, {"data_keys": list(data.keys())})
            
            return entity
        except Exception as e:
            self._handle_error("update", e, {"entity_id": entity_id, "data_keys": list(data.keys())})
            raise
    
    def delete(self, entity_id: str) -> bool:
        """Delete entity with business logic"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            # Check if entity exists
            existing_entity = self.repository.get_by_id(entity_id)
            if not existing_entity:
                return False
            
            # Apply business logic
            if not self._can_delete(existing_entity):
                raise ValueError("Entity cannot be deleted due to business rules")
            
            # Delete entity
            result = self.repository.delete(entity_id)
            
            if result:
                self._log_operation("delete", entity_id)
            
            return result
        except Exception as e:
            self._handle_error("delete", e, {"entity_id": entity_id})
            raise
    
    def list(self, filters: Optional[Dict[str, Any]] = None, 
             order_by: Optional[str] = None, limit: int = 100, 
             offset: int = 0) -> List[T]:
        """List entities with business logic"""
        try:
            # Apply business logic to filters
            processed_filters = self._process_list_filters(filters or {})
            
            entities = self.repository.list(
                filters=processed_filters,
                order_by=order_by,
                limit=limit,
                offset=offset
            )
            
            self._log_operation("list", "multiple", {
                "count": len(entities),
                "filters": processed_filters
            })
            
            return entities
        except Exception as e:
            self._handle_error("list", e, {"filters": filters})
            raise
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count entities with business logic"""
        try:
            processed_filters = self._process_list_filters(filters or {})
            count = self.repository.count(filters=processed_filters)
            
            self._log_operation("count", "multiple", {"count": count, "filters": processed_filters})
            return count
        except Exception as e:
            self._handle_error("count", e, {"filters": filters})
            raise
    
    @abstractmethod
    def _get_required_fields(self) -> List[str]:
        """Get list of required fields for creation"""
        pass
    
    def _process_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data before creation (override in subclasses)"""
        return data
    
    def _process_update_data(self, data: Dict[str, Any], existing_entity: T) -> Dict[str, Any]:
        """Process data before update (override in subclasses)"""
        return data
    
    def _process_list_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Process filters before listing (override in subclasses)"""
        return filters
    
    def _can_delete(self, entity: T) -> bool:
        """Check if entity can be deleted (override in subclasses)"""
        return True


class AsyncRepositoryService(AsyncBaseService, Generic[T]):
    """Async service that wraps a repository with business logic"""
    
    def __init__(self, session: AsyncSession, repository: AsyncBaseRepository[T]):
        super().__init__(session)
        self.repository = repository
    
    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by ID with validation"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            entity = await self.repository.get_by_id(entity_id)
            if entity:
                self._log_operation("get_by_id", entity_id)
            return entity
        except Exception as e:
            self._handle_error("get_by_id", e, {"entity_id": entity_id})
            raise
    
    async def create(self, data: Dict[str, Any]) -> T:
        """Create entity with validation and business logic"""
        try:
            required_fields = self._get_required_fields()
            self._validate_required_fields(data, required_fields)
            
            processed_data = self._process_create_data(data)
            entity = await self.repository.create(**processed_data)
            
            self._log_operation("create", str(entity.id), {"data_keys": list(data.keys())})
            return entity
        except Exception as e:
            self._handle_error("create", e, {"data_keys": list(data.keys())})
            raise
    
    async def update(self, entity_id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update entity with validation and business logic"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            existing_entity = await self.repository.get_by_id(entity_id)
            if not existing_entity:
                return None
            
            processed_data = self._process_update_data(data, existing_entity)
            entity = await self.repository.update(entity_id, **processed_data)
            
            if entity:
                self._log_operation("update", entity_id, {"data_keys": list(data.keys())})
            
            return entity
        except Exception as e:
            self._handle_error("update", e, {"entity_id": entity_id, "data_keys": list(data.keys())})
            raise
    
    async def delete(self, entity_id: str) -> bool:
        """Delete entity with business logic"""
        if not self._validate_uuid(entity_id):
            raise ValueError("Invalid entity ID format")
        
        try:
            existing_entity = await self.repository.get_by_id(entity_id)
            if not existing_entity:
                return False
            
            if not self._can_delete(existing_entity):
                raise ValueError("Entity cannot be deleted due to business rules")
            
            result = await self.repository.delete(entity_id)
            
            if result:
                self._log_operation("delete", entity_id)
            
            return result
        except Exception as e:
            self._handle_error("delete", e, {"entity_id": entity_id})
            raise
    
    async def list(self, filters: Optional[Dict[str, Any]] = None, 
                   order_by: Optional[str] = None, limit: int = 100, 
                   offset: int = 0) -> List[T]:
        """List entities with business logic"""
        try:
            processed_filters = self._process_list_filters(filters or {})
            entities = await self.repository.list(
                filters=processed_filters,
                order_by=order_by,
                limit=limit,
                offset=offset
            )
            
            self._log_operation("list", "multiple", {
                "count": len(entities),
                "filters": processed_filters
            })
            
            return entities
        except Exception as e:
            self._handle_error("list", e, {"filters": filters})
            raise
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count entities with business logic"""
        try:
            processed_filters = self._process_list_filters(filters or {})
            count = await self.repository.count(filters=processed_filters)
            
            self._log_operation("count", "multiple", {"count": count, "filters": processed_filters})
            return count
        except Exception as e:
            self._handle_error("count", e, {"filters": filters})
            raise
    
    @abstractmethod
    def _get_required_fields(self) -> List[str]:
        """Get list of required fields for creation"""
        pass
    
    def _process_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data before creation (override in subclasses)"""
        return data
    
    def _process_update_data(self, data: Dict[str, Any], existing_entity: T) -> Dict[str, Any]:
        """Process data before update (override in subclasses)"""
        return data
    
    def _process_list_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Process filters before listing (override in subclasses)"""
        return filters
    
    def _can_delete(self, entity: T) -> bool:
        """Check if entity can be deleted (override in subclasses)"""
        return True
