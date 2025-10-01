"""
Enhanced base repository with production-grade features:
- Tenant isolation
- Optimistic locking
- Cursor-based pagination
- Error mapping
- Bulk operations
"""
from __future__ import annotations
from typing import Tuple, List, Any, Optional, Dict, Type, TypeVar, Generic, Union
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, update, delete
from sqlalchemy.exc import IntegrityError, NoResultFound
from datetime import datetime
import uuid
import base64
import json
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

# Domain exceptions
class RepositoryError(Exception):
    """Base repository error"""
    pass

class NotFoundError(RepositoryError):
    """Entity not found"""
    pass

class DuplicateError(RepositoryError):
    """Duplicate entity error"""
    pass

class ConcurrencyError(RepositoryError):
    """Optimistic locking conflict"""
    pass

class ForeignKeyViolationError(RepositoryError):
    """Foreign key constraint violation"""
    pass


class Repository(Generic[T]):
    """Simple base repository without tenant isolation"""
    
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
            self.session.rollback()
            logger.error(f"Failed to create {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to create {self.model.__name__}: {str(e)}")
    
    def get_by_id(self, id: Union[str, uuid.UUID]) -> Optional[T]:
        """Get record by ID"""
        try:
            return self.session.get(self.model, id)
        except Exception as e:
            logger.error(f"Failed to get {self.model.__name__} by ID {id}: {e}")
            return None
    
    def list(self, filters: Optional[Dict[str, Any]] = None, 
             order_by: Optional[str] = None, limit: Optional[int] = None) -> List[T]:
        """List records with optional filters"""
        query = self.session.query(self.model)
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)
        
        if order_by:
            if order_by.startswith('-'):
                column = getattr(self.model, order_by[1:])
                query = query.order_by(desc(column))
            else:
                column = getattr(self.model, order_by)
                query = query.order_by(asc(column))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def update(self, id: Union[str, uuid.UUID], **kwargs) -> Optional[T]:
        """Update record by ID"""
        try:
            instance = self.get_by_id(id)
            if not instance:
                return None
            
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            self.session.flush()
            self.session.refresh(instance)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return instance
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to update {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to update {self.model.__name__}: {str(e)}")
    
    def delete(self, id: Union[str, uuid.UUID]) -> bool:
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
            self.session.rollback()
            logger.error(f"Failed to delete {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to delete {self.model.__name__}: {str(e)}")


class AsyncRepository(Generic[T]):
    """Simple async base repository without tenant isolation"""
    
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
            await self.session.rollback()
            logger.error(f"Failed to create {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to create {self.model.__name__}: {str(e)}")
    
    async def get_by_id(self, id: Union[str, uuid.UUID]) -> Optional[T]:
        """Get record by ID"""
        try:
            return await self.session.get(self.model, id)
        except Exception as e:
            logger.error(f"Failed to get {self.model.__name__} by ID {id}: {e}")
            return None
    
    async def list(self, filters: Optional[Dict[str, Any]] = None, 
                   order_by: Optional[str] = None, limit: Optional[int] = None) -> List[T]:
        """List records with optional filters"""
        query = select(self.model)
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
        
        if order_by:
            if order_by.startswith('-'):
                column = getattr(self.model, order_by[1:])
                query = query.order_by(desc(column))
            else:
                column = getattr(self.model, order_by)
                query = query.order_by(asc(column))
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def update(self, id: Union[str, uuid.UUID], **kwargs) -> Optional[T]:
        """Update record by ID"""
        try:
            instance = await self.get_by_id(id)
            if not instance:
                return None
            
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            await self.session.flush()
            await self.session.refresh(instance)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return instance
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to update {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to update {self.model.__name__}: {str(e)}")
    
    async def delete(self, id: Union[str, uuid.UUID]) -> bool:
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
            await self.session.rollback()
            logger.error(f"Failed to delete {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to delete {self.model.__name__}: {str(e)}")


class TenantRepository(Generic[T]):
    """Base repository with mandatory tenant isolation"""
    
    def __init__(self, session: Session, model: Type[T], tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.model = model
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    def _ensure_tenant_filter(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ensure tenant_id is always in filters"""
        if filters is None:
            filters = {}
        filters['tenant_id'] = self.tenant_id
        return filters
    
    def _apply_filters(self, stmt, filters: Dict[str, Any]):
        """Apply filters to query"""
        for field_name, value in filters.items():
            if not hasattr(self.model, field_name):
                continue
                
            field = getattr(self.model, field_name)
            
            if isinstance(value, dict):
                # Support operators like {'gte': 100, 'lte': 200}
                if 'gte' in value:
                    stmt = stmt.where(field >= value['gte'])
                if 'lte' in value:
                    stmt = stmt.where(field <= value['lte'])
                if 'gt' in value:
                    stmt = stmt.where(field > value['gt'])
                if 'lt' in value:
                    stmt = stmt.where(field < value['lt'])
                if 'in' in value:
                    stmt = stmt.where(field.in_(value['in']))
                if 'like' in value:
                    stmt = stmt.where(field.like(value['like']))
                if 'ilike' in value:
                    stmt = stmt.where(field.ilike(value['ilike']))
            elif isinstance(value, list):
                stmt = stmt.where(field.in_(value))
            else:
                stmt = stmt.where(field == value)
        
        return stmt
    
    def _apply_ordering(self, stmt, order_by: Optional[str] = None):
        """Apply ordering to query"""
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
            # Default stable ordering
            stmt = stmt.order_by(desc(self.model.created_at), desc(self.model.id))
        
        return stmt
    
    def _encode_cursor(self, entity: T) -> str:
        """Encode cursor from entity"""
        cursor_data = {
            'created_at': entity.created_at.isoformat(),
            'id': str(entity.id)
        }
        return base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        """Decode cursor to filters"""
        try:
            cursor_data = json.loads(base64.b64decode(cursor.encode()).decode())
            return {
                'created_at': {'lt': datetime.fromisoformat(cursor_data['created_at'])},
                'id': {'lt': uuid.UUID(cursor_data['id'])}
            }
        except Exception:
            raise ValueError("Invalid cursor format")
    
    def create(self, tenant_id: uuid.UUID, **kwargs) -> T:
        """Create a new record with tenant isolation"""
        try:
            kwargs['tenant_id'] = tenant_id
            instance = self.model(**kwargs)
            self.session.add(instance)
            self.session.flush()
            self.session.refresh(instance)
            logger.debug(f"Created {self.model.__name__}: {instance.id}")
            return instance
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error creating {self.model.__name__}: {e}")
            self.session.rollback()
            raise RepositoryError(f"Failed to create {self.model.__name__}: {str(e)}")
    
    def get_by_id(self, tenant_id: uuid.UUID, id: Any) -> Optional[T]:
        """Get record by ID with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            result = self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by ID {id}: {e}")
            return None
    
    def update(self, tenant_id: uuid.UUID, id: Any, expected_version: Optional[int] = None, **kwargs) -> Optional[T]:
        """Update record with optimistic locking"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            
            # Add version check for optimistic locking
            if expected_version is not None and hasattr(self.model, 'version'):
                filters['version'] = expected_version
            
            # Build update statement
            update_stmt = update(self.model).where(
                and_(
                    self.model.tenant_id == tenant_id,
                    self.model.id == id
                )
            )
            
            # Add version check
            if expected_version is not None and hasattr(self.model, 'version'):
                update_stmt = update_stmt.where(self.model.version == expected_version)
                kwargs['version'] = expected_version + 1
            
            # Apply updates
            result = self.session.execute(update_stmt.values(**kwargs))
            
            if result.rowcount == 0:
                if expected_version is not None:
                    raise ConcurrencyError(f"Concurrent modification detected for {self.model.__name__} {id}")
                else:
                    raise NotFoundError(f"{self.model.__name__} {id} not found")
            
            # Refresh the updated entity
            self.session.flush()
            updated_entity = self.get_by_id(tenant_id, id)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return updated_entity
            
        except ConcurrencyError:
            raise
        except NotFoundError:
            raise
        except IntegrityError as e:
            logger.error(f"Integrity error updating {self.model.__name__}: {e}")
            self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            self.session.rollback()
            raise RepositoryError(f"Failed to update {self.model.__name__}: {str(e)}")
    
    def delete(self, tenant_id: uuid.UUID, id: Any) -> bool:
        """Delete record with tenant isolation"""
        try:
            delete_stmt = delete(self.model).where(
                and_(
                    self.model.tenant_id == tenant_id,
                    self.model.id == id
                )
            )
            result = self.session.execute(delete_stmt)
            
            if result.rowcount == 0:
                return False
            
            logger.debug(f"Deleted {self.model.__name__}: {id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            self.session.rollback()
            raise RepositoryError(f"Failed to delete {self.model.__name__}: {str(e)}")
    
    def list(self, tenant_id: uuid.UUID, filters: Optional[Dict[str, Any]] = None,
             order_by: Optional[str] = None, limit: int = 100, 
             cursor: Optional[str] = None) -> Tuple[List[T], Optional[str]]:
        """List records with cursor-based pagination"""
        try:
            filters = self._ensure_tenant_filter(filters or {})
            
            # Apply cursor filters
            if cursor:
                cursor_filters = self._decode_cursor(cursor)
                filters.update(cursor_filters)
            
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            stmt = self._apply_ordering(stmt, order_by)
            stmt = stmt.limit(limit + 1)  # Get one extra to check if there are more
            
            result = self.session.execute(stmt)
            entities = result.scalars().all()
            
            # Check if there are more results
            has_more = len(entities) > limit
            if has_more:
                entities = entities[:limit]
                next_cursor = self._encode_cursor(entities[-1])
            else:
                next_cursor = None
            
            return entities, next_cursor
            
        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            return [], None
    
    def count(self, tenant_id: uuid.UUID, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter(filters or {})
            stmt = select(func.count(self.model.id))
            stmt = self._apply_filters(stmt, filters)
            result = self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            return 0
    
    def exists(self, tenant_id: uuid.UUID, id: Any) -> bool:
        """Check if record exists with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            stmt = select(self.model.id)
            stmt = self._apply_filters(stmt, filters)
            result = self.session.execute(stmt)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking existence of {self.model.__name__} {id}: {e}")
            return False
    
    def bulk_create(self, tenant_id: uuid.UUID, entities_data: List[Dict[str, Any]]) -> List[T]:
        """Bulk create entities"""
        try:
            entities = []
            for data in entities_data:
                data['tenant_id'] = tenant_id
                entity = self.model(**data)
                entities.append(entity)
            
            self.session.add_all(entities)
            self.session.flush()
            
            for entity in entities:
                self.session.refresh(entity)
            
            logger.debug(f"Bulk created {len(entities)} {self.model.__name__} entities")
            return entities
            
        except IntegrityError as e:
            logger.error(f"Integrity error bulk creating {self.model.__name__}: {e}")
            self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error bulk creating {self.model.__name__}: {e}")
            self.session.rollback()
            raise RepositoryError(f"Failed to bulk create {self.model.__name__}: {str(e)}")
    
    def upsert(self, tenant_id: uuid.UUID, unique_fields: Dict[str, Any], **kwargs) -> T:
        """Upsert entity based on unique fields"""
        try:
            # Try to find existing entity
            filters = self._ensure_tenant_filter(unique_fields)
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            result = self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing
                kwargs['tenant_id'] = tenant_id
                for key, value in kwargs.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                
                self.session.flush()
                self.session.refresh(existing)
                logger.debug(f"Upserted (updated) {self.model.__name__}: {existing.id}")
                return existing
            else:
                # Create new
                kwargs.update(unique_fields)
                return self.create(tenant_id, **kwargs)
                
        except IntegrityError as e:
            logger.error(f"Integrity error upserting {self.model.__name__}: {e}")
            self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error upserting {self.model.__name__}: {e}")
            self.session.rollback()
            raise RepositoryError(f"Failed to upsert {self.model.__name__}: {str(e)}")
    
    def _map_integrity_error(self, e: IntegrityError):
        """Map database integrity errors to domain errors"""
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        
        if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
            raise DuplicateError(f"Duplicate entity: {error_msg}")
        elif 'foreign key' in error_msg.lower():
            raise ForeignKeyViolationError(f"Foreign key violation: {error_msg}")
        else:
            raise RepositoryError(f"Database integrity error: {error_msg}")


class AsyncTenantRepository(Generic[T]):
    """Async base repository with mandatory tenant isolation"""
    
    def __init__(self, session: AsyncSession, model: Type[T], tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.model = model
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    def _ensure_tenant_filter(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ensure tenant_id is always in filters"""
        if filters is None:
            filters = {}
        filters['tenant_id'] = self.tenant_id
        return filters
    
    def _apply_filters(self, stmt, filters: Dict[str, Any]):
        """Apply filters to query"""
        for field_name, value in filters.items():
            if not hasattr(self.model, field_name):
                continue
                
            field = getattr(self.model, field_name)
            
            if isinstance(value, dict):
                # Support operators like {'gte': 100, 'lte': 200}
                if 'gte' in value:
                    stmt = stmt.where(field >= value['gte'])
                if 'lte' in value:
                    stmt = stmt.where(field <= value['lte'])
                if 'gt' in value:
                    stmt = stmt.where(field > value['gt'])
                if 'lt' in value:
                    stmt = stmt.where(field < value['lt'])
                if 'in' in value:
                    stmt = stmt.where(field.in_(value['in']))
                if 'like' in value:
                    stmt = stmt.where(field.like(value['like']))
                if 'ilike' in value:
                    stmt = stmt.where(field.ilike(value['ilike']))
            elif isinstance(value, list):
                stmt = stmt.where(field.in_(value))
            else:
                stmt = stmt.where(field == value)
        
        return stmt
    
    def _apply_ordering(self, stmt, order_by: Optional[str] = None):
        """Apply ordering to query"""
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
            # Default stable ordering
            stmt = stmt.order_by(desc(self.model.created_at), desc(self.model.id))
        
        return stmt
    
    def _encode_cursor(self, entity: T) -> str:
        """Encode cursor from entity"""
        cursor_data = {
            'created_at': entity.created_at.isoformat(),
            'id': str(entity.id)
        }
        return base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        """Decode cursor to filters"""
        try:
            cursor_data = json.loads(base64.b64decode(cursor.encode()).decode())
            return {
                'created_at': {'lt': datetime.fromisoformat(cursor_data['created_at'])},
                'id': {'lt': uuid.UUID(cursor_data['id'])}
            }
        except Exception:
            raise ValueError("Invalid cursor format")
    
    async def create(self, tenant_id: uuid.UUID, **kwargs) -> T:
        """Create a new record with tenant isolation"""
        try:
            kwargs['tenant_id'] = tenant_id
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            await self.session.refresh(instance)
            logger.debug(f"Created {self.model.__name__}: {instance.id}")
            return instance
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise RepositoryError(f"Failed to create {self.model.__name__}: {str(e)}")
    
    async def get_by_id(self, tenant_id: uuid.UUID, id: Any) -> Optional[T]:
        """Get record by ID with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by ID {id}: {e}")
            return None
    
    async def update(self, tenant_id: uuid.UUID, id: Any, expected_version: Optional[int] = None, **kwargs) -> Optional[T]:
        """Update record with optimistic locking"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            
            # Add version check for optimistic locking
            if expected_version is not None and hasattr(self.model, 'version'):
                filters['version'] = expected_version
            
            # Build update statement
            update_stmt = update(self.model).where(
                and_(
                    self.model.tenant_id == tenant_id,
                    self.model.id == id
                )
            )
            
            # Add version check
            if expected_version is not None and hasattr(self.model, 'version'):
                update_stmt = update_stmt.where(self.model.version == expected_version)
                kwargs['version'] = expected_version + 1
            
            # Apply updates
            result = await self.session.execute(update_stmt.values(**kwargs))
            
            if result.rowcount == 0:
                if expected_version is not None:
                    raise ConcurrencyError(f"Concurrent modification detected for {self.model.__name__} {id}")
                else:
                    raise NotFoundError(f"{self.model.__name__} {id} not found")
            
            # Refresh the updated entity
            await self.session.flush()
            updated_entity = await self.get_by_id(tenant_id, id)
            logger.debug(f"Updated {self.model.__name__}: {id}")
            return updated_entity
            
        except ConcurrencyError:
            raise
        except NotFoundError:
            raise
        except IntegrityError as e:
            logger.error(f"Integrity error updating {self.model.__name__}: {e}")
            await self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise RepositoryError(f"Failed to update {self.model.__name__}: {str(e)}")
    
    async def delete(self, tenant_id: uuid.UUID, id: Any) -> bool:
        """Delete record with tenant isolation"""
        try:
            delete_stmt = delete(self.model).where(
                and_(
                    self.model.tenant_id == tenant_id,
                    self.model.id == id
                )
            )
            result = await self.session.execute(delete_stmt)
            
            if result.rowcount == 0:
                return False
            
            logger.debug(f"Deleted {self.model.__name__}: {id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise RepositoryError(f"Failed to delete {self.model.__name__}: {str(e)}")
    
    async def list(self, tenant_id: uuid.UUID, filters: Optional[Dict[str, Any]] = None,
                   order_by: Optional[str] = None, limit: int = 100, 
                   cursor: Optional[str] = None) -> Tuple[List[T], Optional[str]]:
        """List records with cursor-based pagination"""
        try:
            filters = self._ensure_tenant_filter(filters or {})
            
            # Apply cursor filters
            if cursor:
                cursor_filters = self._decode_cursor(cursor)
                filters.update(cursor_filters)
            
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            stmt = self._apply_ordering(stmt, order_by)
            stmt = stmt.limit(limit + 1)  # Get one extra to check if there are more
            
            result = await self.session.execute(stmt)
            entities = result.scalars().all()
            
            # Check if there are more results
            has_more = len(entities) > limit
            if has_more:
                entities = entities[:limit]
                next_cursor = self._encode_cursor(entities[-1])
            else:
                next_cursor = None
            
            return entities, next_cursor
            
        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            return [], None
    
    async def count(self, tenant_id: uuid.UUID, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter(filters or {})
            stmt = select(func.count(self.model.id))
            stmt = self._apply_filters(stmt, filters)
            result = await self.session.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            return 0
    
    async def exists(self, tenant_id: uuid.UUID, id: Any) -> bool:
        """Check if record exists with tenant isolation"""
        try:
            filters = self._ensure_tenant_filter({'id': id})
            stmt = select(self.model.id)
            stmt = self._apply_filters(stmt, filters)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking existence of {self.model.__name__} {id}: {e}")
            return False
    
    async def bulk_create(self, tenant_id: uuid.UUID, entities_data: List[Dict[str, Any]]) -> List[T]:
        """Bulk create entities"""
        try:
            entities = []
            for data in entities_data:
                data['tenant_id'] = tenant_id
                entity = self.model(**data)
                entities.append(entity)
            
            self.session.add_all(entities)
            await self.session.flush()
            
            for entity in entities:
                await self.session.refresh(entity)
            
            logger.debug(f"Bulk created {len(entities)} {self.model.__name__} entities")
            return entities
            
        except IntegrityError as e:
            logger.error(f"Integrity error bulk creating {self.model.__name__}: {e}")
            await self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error bulk creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise RepositoryError(f"Failed to bulk create {self.model.__name__}: {str(e)}")
    
    async def upsert(self, tenant_id: uuid.UUID, unique_fields: Dict[str, Any], **kwargs) -> T:
        """Upsert entity based on unique fields"""
        try:
            # Try to find existing entity
            filters = self._ensure_tenant_filter(unique_fields)
            stmt = select(self.model)
            stmt = self._apply_filters(stmt, filters)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing
                kwargs['tenant_id'] = tenant_id
                for key, value in kwargs.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                
                await self.session.flush()
                await self.session.refresh(existing)
                logger.debug(f"Upserted (updated) {self.model.__name__}: {existing.id}")
                return existing
            else:
                # Create new
                kwargs.update(unique_fields)
                return await self.create(tenant_id, **kwargs)
                
        except IntegrityError as e:
            logger.error(f"Integrity error upserting {self.model.__name__}: {e}")
            await self.session.rollback()
            self._map_integrity_error(e)
        except Exception as e:
            logger.error(f"Error upserting {self.model.__name__}: {e}")
            await self.session.rollback()
            raise RepositoryError(f"Failed to upsert {self.model.__name__}: {str(e)}")
    
    def _map_integrity_error(self, e: IntegrityError):
        """Map database integrity errors to domain errors"""
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        
        if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
            raise DuplicateError(f"Duplicate entity: {error_msg}")
        elif 'foreign key' in error_msg.lower():
            raise ForeignKeyViolationError(f"Foreign key violation: {error_msg}")
        else:
            raise RepositoryError(f"Database integrity error: {error_msg}")
