"""
Model Registry Service for business logic
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
import os
import json
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.model_registry_repo import AsyncModelRegistryRepository
from app.schemas.model_registry import ScanResult, RetireRequest, RetireResponse
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelRegistryService:
    """Service for model registry operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AsyncModelRegistryRepository(session)
        self.settings = get_settings()
    
    async def scan_models_directory(self) -> ScanResult:
        """Scan MODELS_ROOT directory and sync with database"""
        models_root = Path(self.settings.MODELS_ROOT)
        
        if not models_root.exists():
            logger.warning(f"Models directory {models_root} does not exist")
            return ScanResult(
                errors=[{"path": str(models_root), "error": "Directory does not exist"}]
            )
        
        scan_result = ScanResult()
        
        # Get all existing models from DB
        existing_models = await self.repo.list_all()
        existing_model_paths = {model.path: model for model in existing_models}
        
        # Scan filesystem
        fs_model_paths = set()
        
        try:
            for item in models_root.iterdir():
                if not item.is_dir():
                    continue
                
                manifest_path = item / "manifest.json"
                fs_model_paths.add(str(item))
                
                if not manifest_path.exists():
                    scan_result.errors.append({
                        "path": str(item),
                        "error": "manifest.json not found"
                    })
                    continue
                
                try:
                    # Validate and process manifest
                    manifest_data = await self._validate_manifest(manifest_path)
                    if not manifest_data:
                        scan_result.errors.append({
                            "path": str(item),
                            "error": "Invalid manifest.json"
                        })
                        continue
                    
                    # Check if model already exists
                    existing_model = await self.repo.get_by_model(manifest_data["model"])
                    
                    if existing_model:
                        # Update existing model
                        if existing_model.version != manifest_data["version"]:
                            await self.repo.update(existing_model.id, {
                                "version": manifest_data["version"],
                                "vector_dim": manifest_data.get("vector_dim"),
                                "path": str(item),
                                "state": "active" if existing_model.state != "retired" else existing_model.state
                            })
                            scan_result.updated.append(manifest_data["model"])
                        else:
                            # Just update path if it changed
                            if existing_model.path != str(item):
                                await self.repo.update(existing_model.id, {"path": str(item)})
                    else:
                        # Create new model
                        await self.repo.create({
                            "model": manifest_data["model"],
                            "version": manifest_data["version"],
                            "modality": manifest_data["modality"],
                            "vector_dim": manifest_data.get("vector_dim"),
                            "path": str(item),
                            "state": "active"
                        })
                        scan_result.added.append(manifest_data["model"])
                
                except Exception as e:
                    logger.error(f"Error processing {item}: {e}")
                    scan_result.errors.append({
                        "path": str(item),
                        "error": str(e)
                    })
        
        except Exception as e:
            logger.error(f"Error scanning models directory: {e}")
            scan_result.errors.append({
                "path": str(models_root),
                "error": f"Scan error: {str(e)}"
            })
            return scan_result
        
        # Disable models that are no longer in filesystem
        for model_path, model in existing_model_paths.items():
            if model_path not in fs_model_paths and model.state == "active":
                await self.repo.update(model.id, {"state": "disabled"})
                scan_result.disabled.append(model.model)
        
        # Flush all changes (commit handled by UoW)
        await self.session.flush()
        logger.info(f"Scan complete: {len(scan_result.added)} added, {len(scan_result.updated)} updated, {len(scan_result.disabled)} disabled, {len(scan_result.errors)} errors")
        
        return scan_result
    
    async def _validate_manifest(self, manifest_path: Path) -> Optional[Dict[str, Any]]:
        """Validate manifest.json file"""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # Required fields
            required_fields = ["model", "version", "modality"]
            for field in required_fields:
                if field not in manifest:
                    logger.error(f"Missing required field '{field}' in {manifest_path}")
                    return None
            
            # Validate modality
            valid_modalities = ["text", "image", "layout", "table", "rerank"]
            if manifest["modality"] not in valid_modalities:
                logger.error(f"Invalid modality '{manifest['modality']}' in {manifest_path}")
                return None
            
            # Validate vector_dim for embedding models
            if manifest["modality"] == "text" and "vector_dim" not in manifest:
                logger.error(f"Missing vector_dim for text model in {manifest_path}")
                return None
            
            return manifest
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {manifest_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading manifest {manifest_path}: {e}")
            return None
    
    async def get_models(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Get list of models with optional filtering"""
        models = await self.repo.list_all(filters=filters)
        
        result = []
        for model in models:
            tenant_count = await self.repo.count_tenants_using(model.model)
            result.append({
                "id": str(model.id),
                "model": model.model,
                "version": model.version,
                "modality": model.modality,
                "state": model.state,
                "vector_dim": model.vector_dim,
                "path": model.path,
                "default_for_new": model.default_for_new,
                "notes": model.notes,
                "used_by_tenants": tenant_count,
                "created_at": model.created_at,
                "updated_at": model.updated_at
            })
        
        return result
    
    async def update_model_state(self, model_id: str, state: str) -> Optional[Dict[str, Any]]:
        """Update model state"""
        import uuid
        
        valid_states = ["active", "archived", "retired", "disabled"]
        if state not in valid_states:
            raise ValueError(f"Invalid state: {state}")
        
        model = await self.repo.update(uuid.UUID(model_id), {"state": state})
        if not model:
            return None
        
        await self.session.flush()  # Flush state update
        
        tenant_count = await self.repo.count_tenants_using(model.model)
        return {
            "id": str(model.id),
            "model": model.model,
            "version": model.version,
            "modality": model.modality,
            "state": model.state,
            "vector_dim": model.vector_dim,
            "path": model.path,
            "default_for_new": model.default_for_new,
            "notes": model.notes,
            "used_by_tenants": tenant_count,
            "created_at": model.created_at,
            "updated_at": model.updated_at
        }
    
    async def update_model(self, model_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update model with any fields"""
        import uuid
        
        # Validate state if provided
        if "state" in update_data:
            valid_states = ["active", "archived", "retired", "disabled"]
            if update_data["state"] not in valid_states:
                raise ValueError(f"Invalid state: {update_data['state']}")
        
        # Only allow updating specific fields
        allowed_fields = {"state", "default_for_new", "notes"}
        filtered_data = {k: v for k, v in update_data.items() if k in allowed_fields}
        
        if not filtered_data:
            raise ValueError("No valid fields to update")
        
        model = await self.repo.update(uuid.UUID(model_id), filtered_data)
        if not model:
            return None
        
        await self.session.flush()  # Flush model update
        
        tenant_count = await self.repo.count_tenants_using(model.model)
        return {
            "id": str(model.id),
            "model": model.model,
            "version": model.version,
            "modality": model.modality,
            "state": model.state,
            "vector_dim": model.vector_dim,
            "path": model.path,
            "default_for_new": model.default_for_new,
            "notes": model.notes,
            "used_by_tenants": tenant_count,
            "created_at": model.created_at,
            "updated_at": model.updated_at
        }
    
    async def retire_model(self, model_id: str, request: RetireRequest) -> RetireResponse:
        """Retire a model and optionally clean up related data"""
        import uuid
        
        model = await self.repo.get_by_id(uuid.UUID(model_id))
        if not model:
            return RetireResponse(
                success=False,
                message="Model not found"
            )
        
        # Get affected tenants
        affected_tenants = await self.repo.get_tenants_by_model(model.model)
        affected_tenant_ids = [str(t.id) for t in affected_tenants]
        
        # Update model state to retired
        await self.repo.update(model.id, {"state": "retired"})
        
        # Remove from tenant profiles if requested
        if request.remove_from_tenants:
            from app.repositories.tenants_repo_async import AsyncTenantsRepository
            tenant_repo = AsyncTenantsRepository(self.session)
            
            for tenant in affected_tenants:
                update_data = {}
                
                # Remove from embed_models
                if tenant.embed_models and model.model in tenant.embed_models:
                    new_embed_models = [m for m in tenant.embed_models if m != model.model]
                    update_data["embed_models"] = new_embed_models if new_embed_models else None
                
                # Remove rerank_model
                if tenant.rerank_model == model.model:
                    update_data["rerank_model"] = None
                
                if update_data:
                    await tenant_repo.update(tenant.id, **update_data)
        
        # TODO: Implement drop_vectors logic when vector store integration is ready
        if request.drop_vectors:
            logger.info(f"TODO: Drop vectors for model {model.model}")
        
        return RetireResponse(
            success=True,
            affected_tenants=affected_tenant_ids,
            message=f"Model {model.model} retired successfully"
        )
    
    async def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed model information"""
        import uuid
        
        model = await self.repo.get_by_id(uuid.UUID(model_id))
        if not model:
            return None
        
        # Get tenants using this model
        tenants = await self.repo.get_tenants_by_model(model.model)
        
        return {
            "id": str(model.id),
            "model": model.model,
            "version": model.version,
            "modality": model.modality,
            "state": model.state,
            "vector_dim": model.vector_dim,
            "path": model.path,
            "default_for_new": model.default_for_new,
            "notes": model.notes,
            "used_by_tenants": len(tenants),
            "tenants": [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "usage_type": "embed" if t.embed_models and model.model in t.embed_models else "rerank"
                }
                for t in tenants
            ],
            "created_at": model.created_at,
            "updated_at": model.updated_at
        }
