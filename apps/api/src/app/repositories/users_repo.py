
from __future__ import annotations
from typing import Optional, Dict, Any
import uuid
import base64
import json
from datetime import datetime
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import Users
from models.tenant import UserTenants

class AsyncUsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = Users

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[Users]:
        """Get user by ID."""
        return await self.session.get(Users, user_id)

    async def get_by_login(self, login: str) -> Optional[Users]:
        res = await self.session.execute(select(Users).where(Users.login == login))
        return res.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Users]:
        res = await self.session.execute(select(Users).where(Users.email == email))
        return res.scalar_one_or_none()

    async def create(self, **kwargs) -> Users:
        """Create a new user."""
        user = Users(**kwargs)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def add_to_tenant(self, user_id, tenant_id, is_default: bool = False) -> None:
        # Create UserTenants object and add to session
        user_tenant = UserTenants(
            id=uuid.uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            is_default=is_default
        )
        self.session.add(user_tenant)
    
    async def is_user_in_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Check if user is in tenant"""
        result = await self.session.execute(
            select(UserTenants).where(
                    UserTenants.user_id == user_id,
                    UserTenants.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def list_by_tenant(self, tenant_id: uuid.UUID, limit: int = 10, cursor: Optional[uuid.UUID] = None):
        """List users by tenant with pagination"""
        # Validate limit
        if limit <= 0 or limit > 100:
            raise ValueError("limit_out_of_range")
        
        # Validate and decode cursor if provided
        cursor_id = None
        if cursor is not None:
            if isinstance(cursor, uuid.UUID):
                cursor_id = cursor
            else:
                try:
                    # Try to decode as encoded cursor
                    cursor_data = self._decode_cursor(str(cursor))
                    cursor_id = cursor_data["id"]
                except (ValueError, KeyError):
                    try:
                        # Try to parse as UUID string
                        cursor_id = uuid.UUID(str(cursor))
                    except ValueError:
                        raise ValueError("invalid_cursor")
        
        query = select(Users).join(UserTenants).where(UserTenants.tenant_id == tenant_id)
        
        if cursor_id:
            # Use decoded cursor ID for pagination
            query = query.where(Users.id > cursor_id)
        
        query = query.order_by(Users.id).limit(limit)
        
        result = await self.session.execute(query)
        users = result.scalars().all()
        
        # Check if there are more users by querying one more
        if len(users) == limit and len(users) > 0:
            # Query one more to see if there are additional users
            next_query = select(Users).join(UserTenants).where(UserTenants.tenant_id == tenant_id)
            if cursor_id:
                next_query = next_query.where(Users.id > cursor_id)
            next_query = next_query.order_by(Users.id).limit(1).offset(limit)
            next_result = await self.session.execute(next_query)
            has_more = next_result.scalar_one_or_none() is not None
            if has_more:
                # Encode cursor with user data
                last_user = users[-1]
                cursor_data = {
                    "created_at": last_user.created_at,
                    "id": last_user.id
                }
                next_cursor = self._encode_cursor(cursor_data)
            else:
                next_cursor = None
        else:
            next_cursor = None
        
        return users, next_cursor
    
    def _encode_cursor(self, data: Dict[str, Any]) -> str:
        """Encode cursor data to base64 string"""
        # Convert datetime to ISO string and UUID to string
        encoded_data = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                encoded_data[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                encoded_data[key] = str(value)
            else:
                encoded_data[key] = value
        
        json_str = json.dumps(encoded_data)
        return base64.b64encode(json_str.encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Dict[str, Any]:
        """Decode cursor from base64 string"""
        try:
            json_str = base64.b64decode(cursor.encode()).decode()
            data = json.loads(json_str)
            
            # Check for required fields
            if "id" not in data or "created_at" not in data:
                raise ValueError("invalid_cursor")
            
            # Convert back to proper types
            decoded_data = {}
            for key, value in data.items():
                if key == "created_at":
                    decoded_data[key] = datetime.fromisoformat(value)
                elif key == "id":
                    decoded_data[key] = uuid.UUID(value)
                else:
                    decoded_data[key] = value
            
            return decoded_data
        except Exception:
            raise ValueError("invalid_cursor")
    
    async def get_default_tenant(self, user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get default tenant for user"""
        result = await self.session.execute(
            select(UserTenants.tenant_id).where(
                UserTenants.user_id == user_id,
                UserTenants.is_default == True
            )
        )
        return result.scalar_one_or_none()
    
    async def set_default_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Set default tenant for user"""
        from sqlalchemy import update
        
        # First, unset all defaults for this user
        await self.session.execute(
            update(UserTenants)
            .where(
                UserTenants.user_id == user_id,
                UserTenants.is_default == True
            )
            .values(is_default=False)
        )
        
        # Then set the new default
        await self.session.execute(
            update(UserTenants)
            .where(
                UserTenants.user_id == user_id,
                UserTenants.tenant_id == tenant_id
            )
            .values(is_default=True)
        )
    
    async def list_users(self, limit: int = 10, cursor: Optional[str] = None):
        """List all users with pagination"""
        # Validate limit
        if limit <= 0 or limit > 100:
            raise ValueError("limit_out_of_range")
        
        # Validate and decode cursor if provided
        cursor_id = None
        if cursor is not None:
            try:
                cursor_id = uuid.UUID(str(cursor))
            except ValueError:
                raise ValueError("invalid_cursor")
        
        query = select(Users)
        
        if cursor_id:
            query = query.where(Users.id > cursor_id)
        
        query = query.order_by(Users.id).limit(limit)
        
        result = await self.session.execute(query)
        users = result.scalars().all()
        
        return users
    
    async def remove_from_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        """Remove user from tenant"""
        from sqlalchemy import delete
        result = await self.session.execute(
            delete(UserTenants).where(
                UserTenants.user_id == user_id,
                UserTenants.tenant_id == tenant_id
            )
        )
        return result.rowcount > 0
