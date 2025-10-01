"""
Enhanced chats service with comprehensive business logic
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import json

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services._base import BaseService, AsyncBaseService, RepositoryService, AsyncRepositoryService
from app.repositories.chats_repo import (
    ChatsRepository, ChatMessagesRepository,
    create_chats_repository, create_chat_messages_repository,
    create_async_chats_repository, create_async_chat_messages_repository
)
from app.models.chat import Chats, ChatMessages
from app.core.logging import get_logger

logger = get_logger(__name__)

class ChatsService(RepositoryService[Chats]):
    """Enhanced chats service with comprehensive business logic"""
    
    def __init__(self, session: Session):
        self.chats_repo = create_chats_repository(session)
        self.messages_repo = create_chat_messages_repository(session)
        super().__init__(session, self.chats_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for chat creation"""
        return ["owner_id"]
    
    def _process_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process chat creation data"""
        processed = data.copy()
        
        # Sanitize name
        if "name" in processed and processed["name"]:
            processed["name"] = self._sanitize_string(processed["name"], 200)
        
        # Sanitize tags
        if "tags" in processed and processed["tags"]:
            if not isinstance(processed["tags"], list):
                raise ValueError("Tags must be a list")
            processed["tags"] = [self._sanitize_string(tag, 50) for tag in processed["tags"]]
        
        # Set default values
        processed.setdefault("tags", [])
        processed.setdefault("created_at", self._get_current_time())
        processed.setdefault("updated_at", self._get_current_time())
        
        return processed
    
    def _process_update_data(self, data: Dict[str, Any], existing_entity: Chats) -> Dict[str, Any]:
        """Process chat update data"""
        processed = data.copy()
        
        # Sanitize name if provided
        if "name" in processed and processed["name"]:
            processed["name"] = self._sanitize_string(processed["name"], 200)
        
        # Sanitize tags if provided
        if "tags" in processed and processed["tags"]:
            if not isinstance(processed["tags"], list):
                raise ValueError("Tags must be a list")
            processed["tags"] = [self._sanitize_string(tag, 50) for tag in processed["tags"]]
        
        # Update timestamp
        processed["updated_at"] = self._get_current_time()
        
        return processed
    
    def _can_delete(self, entity: Chats) -> bool:
        """Check if chat can be deleted"""
        # Chats can always be deleted (messages will be cascade deleted)
        return True
    
    def create_chat(self, owner_id: str, name: Optional[str] = None, 
                   tags: Optional[List[str]] = None) -> Chats:
        """Create a new chat"""
        try:
            if not self._validate_uuid(owner_id):
                raise ValueError("Invalid owner ID format")
            
            # Validate name length
            if name and len(name) > 200:
                raise ValueError("Chat name too long (max 200 characters)")
            
            # Validate tags
            if tags:
                if not isinstance(tags, list):
                    raise ValueError("Tags must be a list")
                if len(tags) > 10:
                    raise ValueError("Too many tags (max 10)")
                for tag in tags:
                    if not isinstance(tag, str) or len(tag) > 50:
                        raise ValueError("Invalid tag format")
            
            chat = self.chats_repo.create_chat(
                owner_id=owner_id,
                name=name,
                tags=tags or []
            )
            
            self._log_operation("create_chat", str(chat.id), {
                "owner_id": owner_id,
                "name": name,
                "tags_count": len(tags or [])
            })
            
            return chat
            
        except Exception as e:
            self._handle_error("create_chat", e, {"owner_id": owner_id, "name": name})
            raise
    
    def get_user_chats(self, user_id: str, query: Optional[str] = None, 
                      limit: int = 100) -> List[Chats]:
        """Get chats for a user with optional search"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            chats = self.chats_repo.get_user_chats(user_id, query, limit)
            
            self._log_operation("get_user_chats", user_id, {
                "query": query,
                "count": len(chats)
            })
            
            return chats
            
        except Exception as e:
            self._handle_error("get_user_chats", e, {"user_id": user_id, "query": query})
            raise
    
    def get_chat_with_messages(self, chat_id: str, user_id: str) -> Optional[Chats]:
        """Get chat with messages, ensuring user has access"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            chat = self.chats_repo.get_chat_with_messages(chat_id)
            if not chat:
                return None
            
            # Check ownership
            if str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            self._log_operation("get_chat_with_messages", chat_id, {"user_id": user_id})
            return chat
            
        except Exception as e:
            self._handle_error("get_chat_with_messages", e, {"chat_id": chat_id, "user_id": user_id})
            raise
    
    def update_chat_name(self, chat_id: str, user_id: str, name: str) -> Optional[Chats]:
        """Update chat name"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            if len(name) > 200:
                raise ValueError("Chat name too long (max 200 characters)")
            
            updated_chat = self.chats_repo.update_chat_name(chat_id, name)
            
            if updated_chat:
                self._log_operation("update_chat_name", chat_id, {
                    "user_id": user_id,
                    "new_name": name
                })
            
            return updated_chat
            
        except Exception as e:
            self._handle_error("update_chat_name", e, {"chat_id": chat_id, "user_id": user_id})
            raise
    
    def update_chat_tags(self, chat_id: str, user_id: str, tags: List[str]) -> Optional[Chats]:
        """Update chat tags"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            # Validate tags
            if not isinstance(tags, list):
                raise ValueError("Tags must be a list")
            if len(tags) > 10:
                raise ValueError("Too many tags (max 10)")
            
            sanitized_tags = []
            for tag in tags:
                if not isinstance(tag, str) or len(tag) > 50:
                    raise ValueError("Invalid tag format")
                sanitized_tags.append(self._sanitize_string(tag, 50))
            
            updated_chat = self.chats_repo.update_chat_tags(chat_id, sanitized_tags)
            
            if updated_chat:
                self._log_operation("update_chat_tags", chat_id, {
                    "user_id": user_id,
                    "tags_count": len(sanitized_tags)
                })
            
            return updated_chat
            
        except Exception as e:
            self._handle_error("update_chat_tags", e, {"chat_id": chat_id, "user_id": user_id})
            raise
    
    def search_chats(self, user_id: str, query: str, limit: int = 50) -> List[Chats]:
        """Search user's chats"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            if not query or len(query.strip()) < 2:
                raise ValueError("Search query too short (min 2 characters)")
            
            chats = self.chats_repo.search_chats(user_id, query, limit)
            
            self._log_operation("search_chats", user_id, {
                "query": query,
                "count": len(chats)
            })
            
            return chats
            
        except Exception as e:
            self._handle_error("search_chats", e, {"user_id": user_id, "query": query})
            raise
    
    def get_chats_by_tag(self, user_id: str, tag: str, limit: int = 50) -> List[Chats]:
        """Get chats by tag"""
        try:
            if not self._validate_uuid(user_id):
                raise ValueError("Invalid user ID format")
            
            if not tag or len(tag.strip()) < 1:
                raise ValueError("Tag cannot be empty")
            
            chats = self.chats_repo.get_chats_by_tag(user_id, tag, limit)
            
            self._log_operation("get_chats_by_tag", user_id, {
                "tag": tag,
                "count": len(chats)
            })
            
            return chats
            
        except Exception as e:
            self._handle_error("get_chats_by_tag", e, {"user_id": user_id, "tag": tag})
            raise


class ChatMessagesService(BaseService):
    """Service for chat messages"""
    
    def __init__(self, session: Session):
        super().__init__(session)
        self.messages_repo = create_chat_messages_repository(session)
        self.chats_repo = create_chats_repository(session)
    
    def create_message(self, chat_id: str, user_id: str, role: str, content: Dict[str, Any],
                      model: Optional[str] = None, tokens_in: Optional[int] = None,
                      tokens_out: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> ChatMessages:
        """Create a new chat message"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Validate role
            valid_roles = ["user", "assistant", "system"]
            if role not in valid_roles:
                raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
            # Check chat ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            # Validate content
            if not content or not isinstance(content, dict):
                raise ValueError("Content must be a non-empty dictionary")
            
            # Sanitize model name
            if model:
                model = self._sanitize_string(model, 100)
            
            # Create message
            message = self.messages_repo.create_message(
                chat_id=chat_id,
                role=role,
                content=content,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                meta=meta
            )
            
            self._log_operation("create_message", str(message.id), {
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role
            })
            
            return message
            
        except Exception as e:
            self._handle_error("create_message", e, {
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role
            })
            raise
    
    def get_chat_messages(self, chat_id: str, user_id: str, limit: int = 50,
                         cursor: Optional[str] = None) -> Tuple[List[ChatMessages], Optional[str]]:
        """Get messages for a chat with pagination"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check chat ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            messages, next_cursor = self.messages_repo.get_chat_messages(
                chat_id, limit, cursor
            )
            
            self._log_operation("get_chat_messages", chat_id, {
                "user_id": user_id,
                "count": len(messages),
                "has_cursor": cursor is not None
            })
            
            return messages, next_cursor
            
        except Exception as e:
            self._handle_error("get_chat_messages", e, {
                "chat_id": chat_id,
                "user_id": user_id
            })
            raise
    
    def get_messages_by_role(self, chat_id: str, user_id: str, role: str, 
                            limit: int = 50) -> List[ChatMessages]:
        """Get messages by role"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check chat ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            # Validate role
            valid_roles = ["user", "assistant", "system"]
            if role not in valid_roles:
                raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            
            messages = self.messages_repo.get_messages_by_role(chat_id, role, limit)
            
            self._log_operation("get_messages_by_role", chat_id, {
                "user_id": user_id,
                "role": role,
                "count": len(messages)
            })
            
            return messages
            
        except Exception as e:
            self._handle_error("get_messages_by_role", e, {
                "chat_id": chat_id,
                "user_id": user_id,
                "role": role
            })
            raise
    
    def search_messages(self, chat_id: str, user_id: str, query: str, 
                       limit: int = 50) -> List[ChatMessages]:
        """Search messages in a chat"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check chat ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            if not query or len(query.strip()) < 2:
                raise ValueError("Search query too short (min 2 characters)")
            
            messages = self.messages_repo.search_messages(chat_id, query, limit)
            
            self._log_operation("search_messages", chat_id, {
                "user_id": user_id,
                "query": query,
                "count": len(messages)
            })
            
            return messages
            
        except Exception as e:
            self._handle_error("search_messages", e, {
                "chat_id": chat_id,
                "user_id": user_id,
                "query": query
            })
            raise
    
    def get_chat_stats(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        """Get chat statistics"""
        try:
            if not self._validate_uuid(chat_id) or not self._validate_uuid(user_id):
                raise ValueError("Invalid ID format")
            
            # Check chat ownership
            chat = self.chats_repo.get_by_id(chat_id)
            if not chat or str(chat.owner_id) != user_id:
                raise ValueError("Access denied")
            
            # Get message counts
            total_messages = self.messages_repo.count_messages(chat_id)
            user_messages = len(self.messages_repo.get_messages_by_role(chat_id, "user", 1000))
            assistant_messages = len(self.messages_repo.get_messages_by_role(chat_id, "assistant", 1000))
            
            stats = {
                "chat_id": chat_id,
                "name": chat.name,
                "tags": chat.tags,
                "created_at": chat.created_at,
                "last_message_at": chat.last_message_at,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages
            }
            
            return stats
            
        except Exception as e:
            self._handle_error("get_chat_stats", e, {"chat_id": chat_id, "user_id": user_id})
            raise


# Async versions
class AsyncChatsService(AsyncRepositoryService[Chats]):
    """Async chats service"""
    
    def __init__(self, session: AsyncSession):
        self.chats_repo = create_async_chats_repository(session)
        super().__init__(session, self.chats_repo)
    
    def _get_required_fields(self) -> List[str]:
        """Required fields for chat creation"""
        return ["owner_id"]
    
    async def create_chat(self, owner_id: str, name: Optional[str] = None, 
                         tags: Optional[List[str]] = None) -> Chats:
        """Create a new chat"""
        try:
            if not self._validate_uuid(owner_id):
                raise ValueError("Invalid owner ID format")
            
            if name and len(name) > 200:
                raise ValueError("Chat name too long (max 200 characters)")
            
            if tags and len(tags) > 10:
                raise ValueError("Too many tags (max 10)")
            
            chat = await self.chats_repo.create_chat(
                owner_id=owner_id,
                name=name,
                tags=tags or []
            )
            
            self._log_operation("create_chat", str(chat.id), {
                "owner_id": owner_id,
                "name": name
            })
            
            return chat
            
        except Exception as e:
            self._handle_error("create_chat", e, {"owner_id": owner_id, "name": name})
            raise


# Factory functions
def create_chats_service(session: Session) -> ChatsService:
    """Create chats service"""
    return ChatsService(session)

def create_chat_messages_service(session: Session) -> ChatMessagesService:
    """Create chat messages service"""
    return ChatMessagesService(session)

def create_async_chats_service(session: AsyncSession) -> AsyncChatsService:
    """Create async chats service"""
    return AsyncChatsService(session)
