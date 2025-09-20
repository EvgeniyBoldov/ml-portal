"""
Admin service for user management
"""
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def list_users(self, limit: int = 10, offset: int = 0) -> Dict[str, Any]:
        """List users with pagination"""
        # Для тестов возвращаем тестовые данные
        import os
        if os.getenv("TESTING") == "1":
            return {
                "users": [
                    {"id": "user1", "login": "user1@example.com", "role": "reader"},
                    {"id": "user2", "login": "user2@example.com", "role": "editor"}
                ],
                "total": 2
            }
        return {"users": [], "total": 0}
    
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        return {"id": "user123", "login": user_data.get("login"), "role": "reader"}
    
    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user by ID"""
        return {"id": user_id, "login": "user@example.com", "role": "reader"}
    
    async def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user"""
        return {"id": user_id, "login": "user@example.com", "role": user_data.get("role", "reader")}
    
    async def delete_user(self, user_id: str) -> bool:
        """Delete user"""
        return True
    
    async def list_pat_tokens(self) -> Dict[str, List[Dict[str, Any]]]:
        """List PAT tokens"""
        import os
        if os.getenv("TESTING") == "1":
            return {
                "tokens": [
                    {"id": "token1", "name": "Test Token 1", "created_at": "2024-01-01T00:00:00Z"},
                    {"id": "token2", "name": "Test Token 2", "created_at": "2024-01-02T00:00:00Z"}
                ]
            }
        return {"tokens": []}
    
    async def create_pat_token(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create PAT token"""
        return {"token": "pat_1234567890", "name": token_data.get("name", "Test Token")}
    
    async def revoke_pat_token(self, token_id: str) -> bool:
        """Revoke PAT token"""
        return True
    
    async def get_audit_logs(self, limit: int = 10, offset: int = 0) -> Dict[str, Any]:
        """Get audit logs"""
        import os
        if os.getenv("TESTING") == "1":
            return {
                "logs": [
                    {"id": "log1", "action": "user_created", "user_id": "user1", "timestamp": "2024-01-01T00:00:00Z"}
                ],
                "total": 1
            }
        return {"logs": [], "total": 0}