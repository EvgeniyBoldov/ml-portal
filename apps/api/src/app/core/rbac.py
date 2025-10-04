"""
Role-Based Access Control (RBAC) with Permission Flags
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from uuid import UUID
import logging

from app.models.user import Users
from app.models.rag import DocumentScope

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles in the system"""
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"


class DocumentPermission(str, Enum):
    """Document-level permissions"""
    CREATE_LOCAL = "create_local"
    CREATE_GLOBAL = "create_global"
    READ_LOCAL = "read_local"
    READ_GLOBAL = "read_global"
    UPDATE_LOCAL = "update_local"
    UPDATE_GLOBAL = "update_global"
    DELETE_LOCAL = "delete_local"
    DELETE_GLOBAL = "delete_global"


class AdminPermission(str, Enum):
    """Administrative permissions"""
    MANAGE_USERS = "manage_users"
    TRIGGER_REINDEX = "trigger_reindex"


@dataclass
class PermissionCheck:
    """Result of permission check"""
    allowed: bool
    reason: Optional[str] = None
    required_role: Optional[UserRole] = None
    required_flag: Optional[str] = None


class RBACValidator:
    """RBAC validation logic"""
    
    @staticmethod
    def can_read_document(user: Users, document_scope: DocumentScope, document_tenant_id: Optional[UUID]) -> PermissionCheck:
        """
        Check if user can read document based on scope and tenant
        
        Rules:
        - Any authenticated user can read global documents
        - Users can only read local documents from their tenants
        """
        # Global documents are readable by everyone
        if document_scope == DocumentScope.GLOBAL:
            return PermissionCheck(allowed=True)
        
        # For local documents, check tenant membership
        if document_tenant_id:
            user_tenants = getattr(user, 'tenants', [])
            user_tenant_ids = [ut.tenant_id for ut in user_tenants]
            
            if document_tenant_id in user_tenant_ids:
                return PermissionCheck(allowed=True)
            else:
                return PermissionCheck(
                    allowed=False,
                    reason=f"User does not have access to tenant {document_tenant_id}"
                )
        
        return PermissionCheck(
            allowed=False,
            reason="Invalid document tenant configuration"
        )
    
    @staticmethod
    def can_create_document(user: Users, document_scope: DocumentScope, target_tenant_id: Optional[UUID]) -> PermissionCheck:
        """
        Check if user can create document
        
        Rules:
        - Readers cannot create documents
        - Editors can create local documents if they have can_edit_local_docs flag
        - Editor/Admin can create global documents if they have can_edit_global_docs flag
        """
        if user.role not in [UserRole.EDITOR, UserRole.ADMIN]:
            return PermissionCheck(
                allowed=False,
                reason=f"Role {user.role} cannot create documents",
                required_role=UserRole.EDITOR
            )
        
        if document_scope == DocumentScope.LOCAL:
            if not user.can_edit_local_docs:
                return PermissionCheck(
                    allowed=False,
                    reason="User does not have permission to edit local documents",
                    required_flag="can_edit_local_docs"
                )
            
            # Verify user has access to target tenant
            user_tenants = getattr(user, 'tenants', [])
            user_tenant_ids = [ut.tenant_id for ut in user_tenants]
            
            if target_tenant_id not in user_tenant_ids:
                return PermissionCheck(
                    allowed=False,
                    reason=f"User does not belong to tenant {target_tenant_id}"
                )
            
            return PermissionCheck(allowed=True)
        
        elif document_scope == DocumentScope.GLOBAL:
            if not user.can_edit_global_docs:
                return PermissionCheck(
                    allowed=False,
                    reason="User does not have permission to edit global documents",
                    required_flag="can_edit_global_docs"
                )
            
            return PermissionCheck(allowed=True)
        
        return PermissionCheck(
            allowed=False,
            reason="Invalid document scope"
        )
    
    @staticmethod
    def can_update_document(user: Users, document_scope: DocumentScope, document_tenant_id: Optional[UUID], document_user_id: UUID) -> PermissionCheck:
        """
        Check if user can update document
        
        Rules:
        - Same as create, but document must exist
        """
        # First check if user can modify documents of this scope
        create_check = RBACValidator.can_create_document(user, document_scope, document_tenant_id)
        if not create_check.allowed:
            return create_check
        
        # Additional check for document ownership for local documents
        if document_scope == DocumentScope.LOCAL:
            if user.id != document_user_id and user.role != UserRole.ADMIN:
                return PermissionCheck(
                    allowed=False,
                    reason="Users can only update their own local documents"
                )
        
        return PermissionCheck(allowed=True)
    
    @staticmethod
    def can_delete_document(user: Users, document_scope: DocumentScope, document_tenant_id: Optional[UUID], document_user_id: UUID) -> PermissionCheck:
        """Check if user can delete document - same rules as update"""
        return RBACValidator.can_update_document(user, document_scope, document_tenant_id, document_user_id)
    
    @staticmethod
    def can_manage_users(user: Users) -> PermissionCheck:
        """Check if user can manage users and roles"""
        if user.role != UserRole.ADMIN or not user.can_manage_users:
            return PermissionCheck(
                allowed=False,
                reason="User does not have permission to manage users",
                required_role=UserRole.ADMIN,
                required_flag="can_manage_users"
            )
        
        return PermissionCheck(allowed=True)
    
    @staticmethod
    def can_trigger_reindex(user: Users) -> PermissionCheck:
        """Check if user can trigger reindexing operations"""
        if user.role not in [UserRole.EDITOR, UserRole.ADMIN] or not user.can_trigger_reindex:
            return PermissionCheck(
                allowed=False,
                reason="User does not have permission to trigger reindex",
                required_flag="can_trigger_reindex"
            )
        
        return PermissionCheck(allowed=True)
    
    @staticmethod
    def get_user_tenants_for_search(user: Users) -> List[UUID]:
        """
        Get list of tenant IDs that user can search in
        
        Returns:
        - List of user's tenant IDs
        - Global documents are searchable via DocumentScope.GLOBAL in filters
        """
        user_tenants = getattr(user, 'tenants', [])
        return [tenant_obj.tenant_id for tenant_obj in user_tenants]
    
    @staticmethod
    def build_search_filters(user: Users, collection_name: str = "rag_chunks") -> Dict[str, Any]:
        """
        Build Qdrant search filters for user's access scope
        
        Returns filter that includes:
        - User's tenant documents (scope='local')
        - Global documents (scope='global')
        """
        user_tenants = RBACValidator.get_user_tenants_for_search(user)
        
        # Build filter for Qdrant
        should_conditions = []
        
        # Add user's tenant documents
        if user_tenants:
            should_conditions.append({
                "key": "tenant_id",
                "match": {"any": user_tenants}
            })
        
        # Add global documents
        should_conditions.append({
            "key": "scope",
            "match": {"value": DocumentScope.GLOBAL.value}
        })
        
        # Qdrant filter format
        return {
            "must_not": [],  # Add any exclusion rules here
            "should": should_conditions  # At least one condition must match
        }


def require_permission(permission_func):
    """
    Decorator to require specific permission
    
    Usage:
    @require_permission(RBACValidator.can_create_document)
    def create_document(user, scope, tenant_id):
        ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract user from arguments (expect first argument to be user)
            if not args:
                raise ValueError("User argument required for permission check")
            
            user = args[0]
            if not isinstance(user, Users):
                raise ValueError("First argument must be Users instance for permission check")
            
            # Check permission with user and remaining arguments
            permission_check = permission_func(user, *args[1:], **kwargs)
            
            if not permission_check.allowed:
                raise ValueError(f"Permission denied: {permission_check.reason}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator
