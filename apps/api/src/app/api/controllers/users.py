"""
Users API controller
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.api.controllers._base import BaseController, PaginatedResponse
from app.api.schemas.users import (
    UserCreateRequest, UserUpdateRequest, UserSearchRequest, UserResponse,
    UserListResponse, UserStatsResponse, PasswordChangeRequest, PasswordResetRequest,
    PasswordResetConfirmRequest, PATTokenCreateRequest, PATTokenCreateResponse,
    PATTokenListResponse, LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
)
from app.services.users_service_enhanced import UsersService, create_users_service
from app.api.deps import db_session, get_current_user, require_admin

router = APIRouter(prefix="/users", tags=["users"])

def get_users_service(session: Session = Depends(db_session)) -> UsersService:
    """Get users service"""
    return create_users_service(session)

class UsersController(BaseController):
    """Users API controller"""
    
    def __init__(self, service: UsersService):
        super().__init__(service)
    
    async def create_user(self, request: UserCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            # Check admin permissions
            if user_info["user_role"] != "admin":
                raise PermissionError("Admin access required")
            
            user = self.service.create_user(
                login=request.login,
                password=request.password,
                role=request.role.value,
                email=request.email,
                is_active=request.is_active
            )
            
            self._log_api_operation("create_user", user_info, request_id, {
                "created_user_id": str(user.id),
                "created_user_login": user.login
            })
            
            return self._create_success_response(
                data=UserResponse.from_orm(user).dict(),
                message="User created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_user", e, request_id)
    
    async def get_user(self, user_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get user by ID"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(user_id, "user_id")
            
            # Check permissions (admin or own user)
            if user_info["user_role"] != "admin" and user_info["user_id"] != user_id:
                raise PermissionError("Access denied")
            
            user = self.service.get_by_id(user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "user_not_found", "User not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("get_user", user_info, request_id, {"target_user_id": user_id})
            
            return self._create_success_response(
                data=UserResponse.from_orm(user).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_user", e, request_id)
    
    async def update_user(self, user_id: str, request: UserUpdateRequest, 
                         current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Update user"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(user_id, "user_id")
            
            # Check permissions (admin or own user)
            if user_info["user_role"] != "admin" and user_info["user_id"] != user_id:
                raise PermissionError("Access denied")
            
            # Prepare update data
            update_data = {}
            if request.email is not None:
                update_data["email"] = request.email
            if request.role is not None:
                # Only admin can change roles
                if user_info["user_role"] != "admin":
                    raise PermissionError("Only admin can change user roles")
                update_data["role"] = request.role.value
            if request.is_active is not None:
                # Only admin can change active status
                if user_info["user_role"] != "admin":
                    raise PermissionError("Only admin can change user active status")
                update_data["is_active"] = request.is_active
            
            if not update_data:
                raise ValueError("No fields to update")
            
            user = self.service.update(user_id, **update_data)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "user_not_found", "User not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("update_user", user_info, request_id, {
                "target_user_id": user_id,
                "updated_fields": list(update_data.keys())
            })
            
            return self._create_success_response(
                data=UserResponse.from_orm(user).dict(),
                message="User updated successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("update_user", e, request_id)
    
    async def delete_user(self, user_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Delete user"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(user_id, "user_id")
            
            # Check admin permissions
            if user_info["user_role"] != "admin":
                raise PermissionError("Admin access required")
            
            # Prevent self-deletion
            if user_info["user_id"] == user_id:
                raise ValueError("Cannot delete your own account")
            
            result = self.service.delete(user_id)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "user_not_found", "User not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("delete_user", user_info, request_id, {"target_user_id": user_id})
            
            return self._create_success_response(
                data={"deleted": True},
                message="User deleted successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("delete_user", e, request_id)
    
    async def search_users(self, request: UserSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Search users"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            # Check admin permissions
            if user_info["user_role"] != "admin":
                raise PermissionError("Admin access required")
            
            self._validate_pagination_params(request.limit, request.offset)
            
            users = self.service.search_users(
                query=request.query or "",
                role=request.role.value if request.role else None,
                is_active=request.is_active,
                limit=request.limit
            )
            
            total = self.service.count()
            
            self._log_api_operation("search_users", user_info, request_id, {
                "query": request.query,
                "results_count": len(users)
            })
            
            return self._create_success_response(
                data=UserListResponse(
                    users=[UserResponse.from_orm(user).dict() for user in users],
                    total=total,
                    limit=request.limit,
                    offset=request.offset,
                    has_more=request.offset + request.limit < total
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("search_users", e, request_id)
    
    async def get_user_stats(self, user_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get user statistics"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(user_id, "user_id")
            
            # Check permissions (admin or own user)
            if user_info["user_role"] != "admin" and user_info["user_id"] != user_id:
                raise PermissionError("Access denied")
            
            stats = self.service.get_user_stats(user_id)
            
            self._log_api_operation("get_user_stats", user_info, request_id, {"target_user_id": user_id})
            
            return self._create_success_response(
                data=stats,
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_user_stats", e, request_id)
    
    async def change_password(self, user_id: str, request: PasswordChangeRequest, 
                             current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Change user password"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(user_id, "user_id")
            
            # Check permissions (admin or own user)
            if user_info["user_role"] != "admin" and user_info["user_id"] != user_id:
                raise PermissionError("Access denied")
            
            result = self.service.change_password(
                user_id=user_id,
                old_password=request.current_password,
                new_password=request.new_password
            )
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=self._create_error_response(
                        "password_change_failed", "Password change failed", request_id=request_id
                    )
                )
            
            self._log_api_operation("change_password", user_info, request_id, {"target_user_id": user_id})
            
            return self._create_success_response(
                data={"changed": True},
                message="Password changed successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("change_password", e, request_id)
    
    async def reset_password_request(self, request: PasswordResetRequest) -> Dict[str, Any]:
        """Request password reset"""
        request_id = self._generate_request_id()
        
        try:
            result = self.service.reset_password_request(request.email)
            
            self._log_api_operation("reset_password_request", {"user_email": request.email}, request_id)
            
            return self._create_success_response(
                data={"requested": True},
                message="Password reset email sent if account exists",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("reset_password_request", e, request_id)
    
    async def reset_password_confirm(self, request: PasswordResetConfirmRequest) -> Dict[str, Any]:
        """Confirm password reset"""
        request_id = self._generate_request_id()
        
        try:
            result = self.service.reset_password_confirm(
                token=request.token,
                new_password=request.new_password
            )
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=self._create_error_response(
                        "password_reset_failed", "Password reset failed", request_id=request_id
                    )
                )
            
            self._log_api_operation("reset_password_confirm", {}, request_id)
            
            return self._create_success_response(
                data={"reset": True},
                message="Password reset successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("reset_password_confirm", e, request_id)
    
    async def create_pat_token(self, request: PATTokenCreateRequest, 
                              current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Create PAT token"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            token_record, access_token = self.service.create_pat_token(
                user_id=user_info["user_id"],
                name=request.name,
                scopes=request.scopes,
                expires_at=request.expires_at
            )
            
            self._log_api_operation("create_pat_token", user_info, request_id, {
                "token_name": request.name
            })
            
            return self._create_success_response(
                data=PATTokenCreateResponse(
                    token=PATTokenResponse.from_orm(token_record).dict(),
                    access_token=access_token
                ).dict(),
                message="PAT token created successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("create_pat_token", e, request_id)
    
    async def get_pat_tokens(self, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Get user's PAT tokens"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            tokens = self.service.get_user_tokens(user_info["user_id"])
            
            self._log_api_operation("get_pat_tokens", user_info, request_id)
            
            return self._create_success_response(
                data=PATTokenListResponse(
                    tokens=[PATTokenResponse.from_orm(token).dict() for token in tokens],
                    total=len(tokens)
                ).dict(),
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("get_pat_tokens", e, request_id)
    
    async def revoke_pat_token(self, token_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Revoke PAT token"""
        request_id = self._generate_request_id()
        user_info = self._extract_user_info(current_user)
        
        try:
            self._validate_uuid_param(token_id, "token_id")
            
            result = self.service.revoke_pat_token(user_info["user_id"], token_id)
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=self._create_error_response(
                        "token_not_found", "Token not found", request_id=request_id
                    )
                )
            
            self._log_api_operation("revoke_pat_token", user_info, request_id, {"token_id": token_id})
            
            return self._create_success_response(
                data={"revoked": True},
                message="PAT token revoked successfully",
                request_id=request_id
            )
            
        except Exception as e:
            raise self._handle_controller_error("revoke_pat_token", e, request_id)

# API endpoints
@router.post("/", response_model=Dict[str, Any])
async def create_user(
    request: UserCreateRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Create a new user"""
    controller = UsersController(service)
    return await controller.create_user(request, current_user)

@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user by ID"""
    controller = UsersController(service)
    return await controller.get_user(user_id, current_user)

@router.put("/{user_id}", response_model=Dict[str, Any])
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Update user"""
    controller = UsersController(service)
    return await controller.update_user(user_id, request, current_user)

@router.delete("/{user_id}", response_model=Dict[str, Any])
async def delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Delete user"""
    controller = UsersController(service)
    return await controller.delete_user(user_id, current_user)

@router.post("/search", response_model=Dict[str, Any])
async def search_users(
    request: UserSearchRequest,
    current_user: Dict[str, Any] = Depends(require_admin),
    service: UsersService = Depends(get_users_service)
):
    """Search users"""
    controller = UsersController(service)
    return await controller.search_users(request, current_user)

@router.get("/{user_id}/stats", response_model=Dict[str, Any])
async def get_user_stats(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user statistics"""
    controller = UsersController(service)
    return await controller.get_user_stats(user_id, current_user)

@router.post("/{user_id}/change-password", response_model=Dict[str, Any])
async def change_password(
    user_id: str,
    request: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Change user password"""
    controller = UsersController(service)
    return await controller.change_password(user_id, request, current_user)

@router.post("/reset-password", response_model=Dict[str, Any])
async def reset_password_request(
    request: PasswordResetRequest,
    service: UsersService = Depends(get_users_service)
):
    """Request password reset"""
    controller = UsersController(service)
    return await controller.reset_password_request(request)

@router.post("/reset-password/confirm", response_model=Dict[str, Any])
async def reset_password_confirm(
    request: PasswordResetConfirmRequest,
    service: UsersService = Depends(get_users_service)
):
    """Confirm password reset"""
    controller = UsersController(service)
    return await controller.reset_password_confirm(request)

@router.post("/pat-tokens", response_model=Dict[str, Any])
async def create_pat_token(
    request: PATTokenCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Create PAT token"""
    controller = UsersController(service)
    return await controller.create_pat_token(request, current_user)

@router.get("/pat-tokens", response_model=Dict[str, Any])
async def get_pat_tokens(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Get user's PAT tokens"""
    controller = UsersController(service)
    return await controller.get_pat_tokens(current_user)

@router.delete("/pat-tokens/{token_id}", response_model=Dict[str, Any])
async def revoke_pat_token(
    token_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: UsersService = Depends(get_users_service)
):
    """Revoke PAT token"""
    controller = UsersController(service)
    return await controller.revoke_pat_token(token_id, current_user)
