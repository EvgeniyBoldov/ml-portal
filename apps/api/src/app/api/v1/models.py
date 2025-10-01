"""
Models endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user
from app.core.security import UserCtx

router = APIRouter(tags=["models"])

@router.get("/models/llm")
def list_llm_models(
    session: Session = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    """List available LLM models with role isolation (G4/G5 compliant)"""
    try:
        # TODO: Implement actual model listing with role-based filtering
        # For now, simulate model listing based on user role
        
        # Get user role for model filtering
        user_role = user.role
        
        # Base models available to all users
        base_models = [
            {
                "id": "gpt-3.5-turbo",
                "name": "GPT-3.5 Turbo",
                "provider": "openai",
                "version": "1.0",
                "context_window": 4096,
                "capabilities": ["chat"],
                "cost_per_token": 0.0015,
                "available": True
            },
            {
                "id": "llama-2-7b",
                "name": "Llama 2 7B",
                "provider": "local",
                "version": "1.0",
                "context_window": 4096,
                "capabilities": ["chat"],
                "cost_per_token": 0.0,
                "available": True
            }
        ]
        
        # Premium models available to editors and admins
        premium_models = []
        if user_role in ["editor", "admin"]:
            premium_models = [
                {
                    "id": "gpt-4",
                    "name": "GPT-4",
                    "provider": "openai",
                    "version": "1.0",
                    "context_window": 8192,
                    "capabilities": ["chat", "analysis"],
                    "cost_per_token": 0.03,
                    "available": True
                },
                {
                    "id": "claude-3-sonnet",
                    "name": "Claude 3 Sonnet",
                    "provider": "anthropic",
                    "version": "1.0",
                    "context_window": 200000,
                    "capabilities": ["chat", "analysis", "long_context"],
                    "cost_per_token": 0.015,
                    "available": True
                }
            ]
        
        # Admin-only models
        admin_models = []
        if user_role == "admin":
            admin_models = [
                {
                    "id": "gpt-4-turbo",
                    "name": "GPT-4 Turbo",
                    "provider": "openai",
                    "version": "1.0",
                    "context_window": 128000,
                    "capabilities": ["chat", "analysis", "vision"],
                    "cost_per_token": 0.01,
                    "available": True
                }
            ]
        
        all_models = base_models + premium_models + admin_models
        
        return {
            "models": all_models,
            "user_role": user_role,
            "total_count": len(all_models)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list LLM models: {str(e)}")

@router.get("/models/embeddings")
def list_embedding_models(
    session: Session = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    """List available embedding models with role isolation (G4/G5 compliant)"""
    try:
        # TODO: Implement actual embedding model listing with role-based filtering
        # For now, simulate embedding model listing based on user role
        
        # Get user role for model filtering
        user_role = user.role
        
        # Base embedding models available to all users
        base_models = [
            {
                "id": "text-embedding-ada-002",
                "name": "Ada 002",
                "provider": "openai",
                "dimensions": 1536,
                "version": "1.0",
                "cost_per_1k_tokens": 0.0001,
                "available": True,
                "capabilities": ["text", "search"]
            },
            {
                "id": "multilingual-e5-small",
                "name": "Multilingual E5 Small",
                "provider": "local",
                "dimensions": 384,
                "version": "1.0",
                "cost_per_1k_tokens": 0.0,
                "available": True,
                "capabilities": ["text", "multilingual"]
            }
        ]
        
        # Premium embedding models available to editors and admins
        premium_models = []
        if user_role in ["editor", "admin"]:
            premium_models = [
                {
                    "id": "text-embedding-3-large",
                    "name": "Embedding 3 Large",
                    "provider": "openai",
                    "dimensions": 3072,
                    "version": "1.0",
                    "cost_per_1k_tokens": 0.00013,
                    "available": True,
                    "capabilities": ["text", "search", "high_quality"]
                },
                {
                    "id": "multilingual-e5-large",
                    "name": "Multilingual E5 Large",
                    "provider": "local",
                    "dimensions": 1024,
                    "version": "1.0",
                    "cost_per_1k_tokens": 0.0,
                    "available": True,
                    "capabilities": ["text", "multilingual", "high_quality"]
                }
            ]
        
        # Admin-only embedding models
        admin_models = []
        if user_role == "admin":
            admin_models = [
                {
                    "id": "text-embedding-3-large-256",
                    "name": "Embedding 3 Large (256 dim)",
                    "provider": "openai",
                    "dimensions": 256,
                    "version": "1.0",
                    "cost_per_1k_tokens": 0.00013,
                    "available": True,
                    "capabilities": ["text", "search", "high_quality", "compressed"]
                }
            ]
        
        all_models = base_models + premium_models + admin_models
        
        return {
            "models": all_models,
            "user_role": user_role,
            "total_count": len(all_models)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list embedding models: {str(e)}")
