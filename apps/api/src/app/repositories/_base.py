from __future__ import annotations
from typing import Tuple, List, Any, Optional, Dict, Type, TypeVar, Generic
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.exc import IntegrityError, NoResultFound
from datetime import datetime
import uuid
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations"""
    
    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model
    
    def create(self, **kwargs) -> T:
        """Create a new record"""
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            self.session.flush()
            self.session.refresh(instance)
            logger.debug(f"Created {self.model.__name__}: {instance.id}")
            return instance
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            self.session.rollback()
            raise
        except Exception as e:
            logger.error(f"Error creating {self.model.__name__}: {e}")
            self.session.rollback()
            raise
    
    def get_by_id(self, id: Any) -> Optional[T]:
        """Get record by ID"""
        try:
            return self.session.get(self.model, id)
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by ID {id}: {e}")
            return None
    
    def get_by_field(self, field_name: str, value: Any) -> Optional[T]:
        """Get record by field value"""
        try:
            field = getattr(self.model, field_name)
            stmt = select(self.model).where(field == value)
            return self.session.execute(stmt).scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by {field_name}={value}: {e}")
            return None
    
    def update(self, id: Any, **kwargs) -> Optional[T]:
        """Update record by ID"""
        try:
            instance = self.get_by_id(id)
            if not instance:
                return None
            
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            # Update timestamp if exists
            if hasattr(instance, 'updated_at'):
                instance.updated_at = datetime.utcnow()
            
            self.session.flush()
            self.session.refresh(instance)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return instance
        except Exception as e:
            logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            self.session.rollback()
            raise
    
    def delete(self, id: Any) -> bool:
        """Delete record by ID"""
        try:
            instance = self.get_by_id(id)
            if not instance:
                return False
            
            self.session.delete(instance)
            self.session.flush()
            logger.debug(f"Deleted {self.model.__name__}: {id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            self.session.rollback()
            raise
    
    def list(self, filters: Optional[Dict[str, Any]] = None, 
             order_by: Optional[str] = None, limit: int = 100, 
             offset: int = 0) -> List[T]:
        """List records with filters and pagination"""
        try:
            stmt = select(self.model)
            
            # Apply filters
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            stmt = stmt.where(field.in_(value))
                        else:
                            stmt = stmt.where(field == value)
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    field_name = order_by[1:]
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        stmt = stmt.order_by(desc(field))
                else:
                    if hasattr(self.model, order_by):
                        field = getattr(self.model, order_by)
                        stmt = stmt.order_by(asc(field))
            else:
                # Default ordering by ID
                stmt = stmt.order_by(desc(self.model.id))
            
            # Apply pagination
            stmt = stmt.offset(offset).limit(limit)
            
            result = self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            return []
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with filters"""
        try:
            stmt = select(func.count(self.model.id))
            
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            stmt = stmt.where(field.in_(value))
                        else:
                            stmt = stmt.where(field == value)
            
            result = self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            return 0
    
    def exists(self, id: Any) -> bool:
        """Check if record exists by ID"""
        try:
            stmt = select(self.model.id).where(self.model.id == id)
            result = self.session.execute(stmt).scalar_one_or_none()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking existence of {self.model.__name__} {id}: {e}")
            return False
    
    def search(self, query: str, search_fields: List[str], 
               limit: int = 100, offset: int = 0) -> List[T]:
        """Search records by text in specified fields"""
        try:
            stmt = select(self.model)
            conditions = []
            
            for field_name in search_fields:
                if hasattr(self.model, field_name):
                    field = getattr(self.model, field_name)
                    conditions.append(field.ilike(f"%{query}%"))
            
            if conditions:
                stmt = stmt.where(or_(*conditions))
            
            stmt = stmt.offset(offset).limit(limit)
            result = self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error searching {self.model.__name__}: {e}")
            return []


class AsyncBaseRepository(Generic[T]):
    """Async base repository with common CRUD operations"""
    
    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model
    
    async def create(self, **kwargs) -> T:
        """Create a new record"""
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            logger.debug(f"Created {self.model.__name__}: {instance.id}")
            return instance
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise
        except Exception as e:
            logger.error(f"Error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise
    
    async def get_by_id(self, id: Any) -> Optional[T]:
        """Get record by ID"""
        try:
            return await self.session.get(self.model, id)
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by ID {id}: {e}")
            return None
    
    async def get_by_field(self, field_name: str, value: Any) -> Optional[T]:
        """Get record by field value"""
        try:
            field = getattr(self.model, field_name)
            stmt = select(self.model).where(field == value)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by {field_name}={value}: {e}")
            return None
    
    async def update(self, id: Any, **kwargs) -> Optional[T]:
        """Update record by ID"""
        try:
            instance = await self.get_by_id(id)
            if not instance:
                return None
            
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            # Update timestamp if exists
            if hasattr(instance, 'updated_at'):
                instance.updated_at = datetime.utcnow()
            
            await self.session.flush()
            await self.session.refresh(instance)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return instance
        except Exception as e:
            logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise
    
    async def delete(self, id: Any) -> bool:
        """Delete record by ID"""
        try:
            instance = await self.get_by_id(id)
            if not instance:
                return False
            
            await self.session.delete(instance)
            await self.session.flush()
            logger.debug(f"Deleted {self.model.__name__}: {id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise
    
    async def list(self, filters: Optional[Dict[str, Any]] = None, 
                   order_by: Optional[str] = None, limit: int = 100, 
                   offset: int = 0) -> List[T]:
        """List records with filters and pagination"""
        try:
            stmt = select(self.model)
            
            # Apply filters
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            stmt = stmt.where(field.in_(value))
                        else:
                            stmt = stmt.where(field == value)
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    field_name = order_by[1:]
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        stmt = stmt.order_by(desc(field))
                else:
                    if hasattr(self.model, order_by):
                        field = getattr(self.model, order_by)
                        stmt = stmt.order_by(asc(field))
            else:
                # Default ordering by ID
                stmt = stmt.order_by(desc(self.model.id))
            
            # Apply pagination
            stmt = stmt.offset(offset).limit(limit)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            return []
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with filters"""
        try:
            stmt = select(func.count(self.model.id))
            
            if filters:
                for field_name, value in filters.items():
                    if hasattr(self.model, field_name):
                        field = getattr(self.model, field_name)
                        if isinstance(value, list):
                            stmt = stmt.where(field.in_(value))
                        else:
                            stmt = stmt.where(field == value)
            
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            return 0
    
    async def exists(self, id: Any) -> bool:
        """Check if record exists by ID"""
        try:
            stmt = select(self.model.id).where(self.model.id == id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking existence of {self.model.__name__} {id}: {e}")
            return False


# Backward compatibility
class BaseRepo(BaseRepository):
    """Backward compatibility alias"""
    def __init__(self, session: Session):
        super().__init__(session, None)  # Will be overridden in subclasses

    def count(self, selectable) -> int:
        """Legacy count method"""
        return self.session.execute(select(func.count()).select_from(selectable.subquery())).scalar_one()
