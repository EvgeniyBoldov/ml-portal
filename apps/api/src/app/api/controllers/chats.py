"""
Chats API controller
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.api.controllers._base import BaseController, PaginatedResponse
from app.api.schemas.chats import (
    ChatCreateRequest, ChatUpdateRequest, ChatSearchRequest, ChatResponse,
    ChatListResponse, ChatStatsResponse, ChatWithMessagesResponse,
    ChatMessageCreateRequest, ChatMessageSearchRequest, ChatMessagesListRequest,
    ChatMessageResponse, ChatMessageListResponse
)
from app.services.chats_service_enhanced import ChatsService, ChatMessagesService, create_chats_service, create_chat_messages_service
from app.api.deps import db_session, get_current_user

router = APIRouter(prefix="/chats", tags=["chats"])

def get_chats_service(session: Session = Depends(db_session)) -> ChatsService:
    """Get chats service"""
    return create_chats_service(session)

def get_chat_messages_service(session: Session = Depends(db_session)) -> ChatMessagesService:
    """Get chat messages service"""
    return create_chat_messages_service(session)

class ChatsController(BaseController):
    """Chats API controller"""
    
    def __init__(self, service: ChatsService):
        super().__init__(service)
    
    async def create_chat(self, request: ChatCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new chat"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            chat = self.service.create_chat(
                owner_id=user_info["user_id"],
                name=request.name,
                tags=request.tags
            )
            
            self._log_api_operation("create_chat", user_info, request_id, {
                "chat_id": str(chat.id),
                "chat_name": chat.name
            })
            
            return self._create_success_response(
                data=ChatResponse.from_orm(chat).dict(),
                message="Chat created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_chat", e, request_id)
    
    async def get_chat(self, chat_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get chat by ID"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            chat = self.service.get_chat_with_messages(chat_id, user_info["user_id"])
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "chat_not_found", "Chat not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("get_chat", user_info, request_id, {"chat_id": chat_id})
            
            return self._create_success_response(
                data=ChatResponse.from_orm(chat).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_chat", e, request_id)
    
    async def update_chat(self, chat_id: str, request: ChatUpdateRequest, 
                         current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Update chat"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            # Update name if provided
            if request.name is not None:
                updated_chat = self.service.update_chat_name(chat_id, user_info["user_id"], request.name)
                if not updated_chat:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=self._create_error_response(
                            "chat_not_found", "Chat not found", request_id=request_id
                        )
                    )
            
            # Update tags if provided
            if request.tags is not None:
                updated_chat = self.service.update_chat_tags(chat_id, user_info["user_id"], request.tags)
                if not updated_chat:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=self._create_error_response(
                            "chat_not_found", "Chat not found", request_id=request_id
                        )
                    )
            
            # Get updated chat
            chat = self.service.get_chat_with_messages(chat_id, user_info["user_id"])
            
            self._log_api_operation("update_chat", user_info, request_id, {
                "chat_id": chat_id,
                "updated_fields": [k for k, v in request.dict().items() if v is not None]
            })
            
            return self._create_success_response(
                data=ChatResponse.from_orm(chat).dict(),
                message="Chat updated successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("update_chat", e, request_id)
    
    async def delete_chat(self, chat_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Delete chat"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            result = self.service.delete(chat_id)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "chat_not_found", "Chat not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("delete_chat", user_info, request_id, {"chat_id": chat_id})
            
            return self._create_success_response(
                data={"deleted": True},
                message="Chat deleted successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("delete_chat", e, request_id)
    
    async def get_user_chats(self, request: ChatSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get user's chats"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_pagination_params(request.limit, request.offset)
            
            if request.query:
                chats = self.service.search_chats(user_info["user_id"], request.query, request.limit)
            elif request.tag:
                chats = self.service.get_chats_by_tag(user_info["user_id"], request.tag, request.limit)
            else:
                chats = self.service.get_user_chats(user_info["user_id"], None, request.limit)
            
            total = len(chats)  # This is approximate, in real implementation we'd count properly
            
            self._log_api_operation("get_user_chats", user_info, request_id, {
                "query": request.query,
                "tag": request.tag,
                "results_count": len(chats)
            })
            
            return self._create_success_response(
                data=ChatListResponse(
                    chats=[ChatResponse.from_orm(chat).dict() for chat in chats],
                    total=total,
                    limit=request.limit,
                    offset=request.offset,
                    has_more=request.offset + request.limit < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_user_chats", e, request_id)
    
    async def get_chat_stats(self, chat_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get chat statistics"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            # Check access
            chat = self.service.get_chat_with_messages(chat_id, user_info["user_id"])
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "chat_not_found", "Chat not found", request_id=request_id
                    )
                )
            
            # Get stats using messages service
            messages_service = ChatMessagesService(self.service.session)
            stats = messages_service.get_chat_stats(chat_id, user_info["user_id"])
            
            self._log_api_operation("get_chat_stats", user_info, request_id, {"chat_id": chat_id})
            
            return self._create_success_response(
                data=stats,
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_chat_stats", e, request_id)

class ChatMessagesController(BaseController):
    """Chat messages API controller"""
    
    def __init__(self, service: ChatMessagesService):
        super().__init__(service)
    
    async def create_message(self, chat_id: str, request: ChatMessageCreateRequest, 
                           current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new chat message"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            message = self.service.create_message(
                chat_id=chat_id,
                user_id=user_info["user_id"],
                role=request.role.value,
                content=request.content,
                model=request.model,
                tokens_in=request.tokens_in,
                tokens_out=request.tokens_out,
                meta=request.meta
            )
            
            self._log_api_operation("create_message", user_info, request_id, {
                "chat_id": chat_id,
                "message_id": str(message.id),
                "role": request.role.value
            })
            
            return self._create_success_response(
                data=ChatMessageResponse.from_orm(message).dict(),
                message="Message created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_message", e, request_id)
    
    async def get_chat_messages(self, chat_id: str, request: ChatMessagesListRequest, 
                               current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get chat messages"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            
            messages, next_cursor = self.service.get_chat_messages(
                chat_id=chat_id,
                user_id=user_info["user_id"],
                limit=request.limit,
                cursor=request.cursor
            )
            
            # Filter by role if specified
            if request.role:
                messages = [m for m in messages if m.role == request.role.value]
            
            self._log_api_operation("get_chat_messages", user_info, request_id, {
                "chat_id": chat_id,
                "results_count": len(messages),
                "role_filter": request.role.value if request.role else None
            })
            
            return self._create_success_response(
                data=ChatMessageListResponse(
                    messages=[ChatMessageResponse.from_orm(msg).dict() for msg in messages],
                    total=len(messages),
                    limit=request.limit,
                    cursor=next_cursor,
                    has_more=next_cursor is not None
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_chat_messages", e, request_id)
    
    async def search_messages(self, chat_id: str, request: ChatMessageSearchRequest, 
                             current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Search messages in chat"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(chat_id, "chat_id")
            self._validate_pagination_params(request.limit, request.offset)
            
            messages = self.service.search_messages(
                chat_id=chat_id,
                user_id=user_info["user_id"],
                query=request.query
            )
            
            # Filter by role if specified
            if request.role:
                messages = [m for m in messages if m.role == request.role.value]
            
            # Apply pagination
            total = len(messages)
            start = request.offset
            end = start + request.limit
            messages = messages[start:end]
            
            self._log_api_operation("search_messages", user_info, request_id, {
                "chat_id": chat_id,
                "query": request.query,
                "results_count": len(messages)
            })
            
            return self._create_success_response(
                data=ChatMessageListResponse(
                    messages=[ChatMessageResponse.from_orm(msg).dict() for msg in messages],
                    total=total,
                    limit=request.limit,
                    cursor=None,
                    has_more=end < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("search_messages", e, request_id)

# API endpoints
@router.post("/", response_model=Dict[str, Any])
async def create_chat(
    request: ChatCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Create a new chat"""
    controller = ChatsController(service)
    return await controller.create_chat(request, current_user)

@router.get("/{chat_id}", response_model=Dict[str, Any])
async def get_chat(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Get chat by ID"""
    controller = ChatsController(service)
    return await controller.get_chat(chat_id, current_user)

@router.put("/{chat_id}", response_model=Dict[str, Any])
async def update_chat(
    chat_id: str,
    request: ChatUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Update chat"""
    controller = ChatsController(service)
    return await controller.update_chat(chat_id, request, current_user)

@router.delete("/{chat_id}", response_model=Dict[str, Any])
async def delete_chat(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Delete chat"""
    controller = ChatsController(service)
    return await controller.delete_chat(chat_id, current_user)

@router.post("/search", response_model=Dict[str, Any])
async def get_user_chats(
    request: ChatSearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Get user's chats"""
    controller = ChatsController(service)
    return await controller.get_user_chats(request, current_user)

@router.get("/{chat_id}/stats", response_model=Dict[str, Any])
async def get_chat_stats(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatsService = Depends(get_chats_service)
):
    """Get chat statistics"""
    controller = ChatsController(service)
    return await controller.get_chat_stats(chat_id, current_user)

# Message endpoints
@router.post("/{chat_id}/messages", response_model=Dict[str, Any])
async def create_message(
    chat_id: str,
    request: ChatMessageCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatMessagesService = Depends(get_chat_messages_service)
):
    """Create a new chat message"""
    controller = ChatMessagesController(service)
    return await controller.create_message(chat_id, request, current_user)

@router.get("/{chat_id}/messages", response_model=Dict[str, Any])
async def get_chat_messages(
    chat_id: str,
    request: ChatMessagesListRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatMessagesService = Depends(get_chat_messages_service)
):
    """Get chat messages"""
    controller = ChatMessagesController(service)
    return await controller.get_chat_messages(chat_id, request, current_user)

@router.post("/{chat_id}/messages/search", response_model=Dict[str, Any])
async def search_messages(
    chat_id: str,
    request: ChatMessageSearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChatMessagesService = Depends(get_chat_messages_service)
):
    """Search messages in chat"""
    controller = ChatMessagesController(service)
    return await controller.search_messages(chat_id, request, current_user)
