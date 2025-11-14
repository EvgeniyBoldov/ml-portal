# apps/api/src/app/core/audit.py
"""
Audit system for tracking presigned URL generation and access
"""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from sqlalchemy import Column, String, DateTime, Text, Integer, select, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.db import get_db
from core.logging import get_logger

logger = get_logger(__name__)

@dataclass
class PresignedAuditEntry:
    """Audit entry for presigned URL generation"""
    audit_id: str
    user_id: str
    tenant_id: str
    source_id: str
    kind: str  # 'original' or 'canonical'
    ip_address: str
    user_agent: str
    generated_at: datetime
    expires_at: datetime
    url_hash: str  # Hash of the generated URL for security
    success: bool
    error_message: Optional[str] = None

class PresignedAuditLogger:
    """Logger for presigned URL audit events"""
    
    def __init__(self):
        self.logger = get_logger("audit.presigned")
    
    def log_presigned_generation(self, 
                               user_id: str,
                               tenant_id: str,
                               source_id: str,
                               kind: str,
                               ip_address: str,
                               user_agent: str,
                               expires_at: datetime,
                               url_hash: str,
                               success: bool,
                               error_message: Optional[str] = None):
        """Log presigned URL generation event"""
        
        audit_entry = PresignedAuditEntry(
            audit_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            source_id=source_id,
            kind=kind,
            ip_address=ip_address,
            user_agent=user_agent,
            generated_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            url_hash=url_hash,
            success=success,
            error_message=error_message
        )
        
        # Log to structured logger
        self.logger.info(
            "Presigned URL generated",
            audit_type="presigned_generation",
            **asdict(audit_entry)
        )
        
        # Log to database (async)
        asyncio.create_task(self._log_to_database(audit_entry))
    
    async def _log_to_database(self, audit_entry: PresignedAuditEntry):
        """Log audit entry to database"""
        try:
            async with get_db() as session:
                # Create audit record
                audit_record = PresignedAuditRecord(
                    audit_id=audit_entry.audit_id,
                    user_id=audit_entry.user_id,
                    tenant_id=audit_entry.tenant_id,
                    source_id=audit_entry.source_id,
                    kind=audit_entry.kind,
                    ip_address=audit_entry.ip_address,
                    user_agent=audit_entry.user_agent,
                    generated_at=audit_entry.generated_at,
                    expires_at=audit_entry.expires_at,
                    url_hash=audit_entry.url_hash,
                    success=audit_entry.success,
                    error_message=audit_entry.error_message
                )
                
                session.add(audit_record)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to log presigned audit to database: {e}")
    
    def log_presigned_access(self,
                           audit_id: str,
                           ip_address: str,
                           user_agent: str,
                           success: bool,
                           error_message: Optional[str] = None):
        """Log presigned URL access event"""
        
        self.logger.info(
            "Presigned URL accessed",
            audit_type="presigned_access",
            audit_id=audit_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            accessed_at=datetime.now(timezone.utc).isoformat()
        )

# Database model for audit records
Base = declarative_base()

class PresignedAuditRecord(Base):
    """Database model for presigned URL audit records"""
    __tablename__ = 'presigned_audit'
    
    audit_id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    tenant_id = Column(String(36), nullable=False)
    source_id = Column(String(36), nullable=False)
    kind = Column(String(20), nullable=False)  # 'original' or 'canonical'
    ip_address = Column(String(45), nullable=False)  # IPv6 max length
    user_agent = Column(Text, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    url_hash = Column(String(64), nullable=False)  # SHA-256 hash
    success = Column(String(10), nullable=False)  # 'true' or 'false'
    error_message = Column(Text, nullable=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_presigned_audit_user_id', 'user_id'),
        Index('ix_presigned_audit_tenant_id', 'tenant_id'),
        Index('ix_presigned_audit_source_id', 'source_id'),
        Index('ix_presigned_audit_generated_at', 'generated_at'),
        Index('ix_presigned_audit_success', 'success'),
    )

class AuditService:
    """Service for audit operations"""
    
    def __init__(self):
        self.presigned_logger = PresignedAuditLogger()
    
    def log_presigned_generation(self, 
                               user_id: str,
                               tenant_id: str,
                               source_id: str,
                               kind: str,
                               ip_address: str,
                               user_agent: str,
                               expires_at: datetime,
                               url_hash: str,
                               success: bool,
                               error_message: Optional[str] = None):
        """Log presigned URL generation"""
        self.presigned_logger.log_presigned_generation(
            user_id=user_id,
            tenant_id=tenant_id,
            source_id=source_id,
            kind=kind,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            url_hash=url_hash,
            success=success,
            error_message=error_message
        )
    
    def log_presigned_access(self,
                           audit_id: str,
                           ip_address: str,
                           user_agent: str,
                           success: bool,
                           error_message: Optional[str] = None):
        """Log presigned URL access"""
        self.presigned_logger.log_presigned_access(
            audit_id=audit_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message
        )
    
    async def get_audit_stats(self, 
                            tenant_id: Optional[str] = None,
                            user_id: Optional[str] = None,
                            days: int = 30) -> Dict[str, Any]:
        """Get audit statistics"""
        try:
            async with get_db() as session:
                # Calculate date range
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=days)
                
                # Build query
                query = select(PresignedAuditRecord).where(
                    PresignedAuditRecord.generated_at >= start_date,
                    PresignedAuditRecord.generated_at <= end_date
                )
                
                if tenant_id:
                    query = query.where(PresignedAuditRecord.tenant_id == tenant_id)
                if user_id:
                    query = query.where(PresignedAuditRecord.user_id == user_id)
                
                # Get statistics
                total_result = await session.execute(select(func.count()).select_from(query.subquery()))
                total_requests = total_result.scalar()
                
                successful_result = await session.execute(
                    select(func.count()).select_from(
                        query.where(PresignedAuditRecord.success == 'true').subquery()
                    )
                )
                successful_requests = successful_result.scalar()
                failed_result = await session.execute(
                    select(func.count()).select_from(
                        query.where(PresignedAuditRecord.success == 'false').subquery()
                    )
                )
                failed_requests = failed_result.scalar()
                
                # Get by kind
                original_result = await session.execute(
                    select(func.count()).select_from(
                        query.where(PresignedAuditRecord.kind == 'original').subquery()
                    )
                )
                original_requests = original_result.scalar()
                
                canonical_result = await session.execute(
                    select(func.count()).select_from(
                        query.where(PresignedAuditRecord.kind == 'canonical').subquery()
                    )
                )
                canonical_requests = canonical_result.scalar()
                
                return {
                    "period_days": days,
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "failed_requests": failed_requests,
                    "success_rate": successful_requests / max(total_requests, 1),
                    "original_requests": original_requests,
                    "canonical_requests": canonical_requests,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {
                "error": str(e),
                "period_days": days,
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "original_requests": 0,
                "canonical_requests": 0
            }

def get_audit_service() -> AuditService:
    """Get audit service instance"""
    return AuditService()

# Import asyncio for async operations
import asyncio
from datetime import timedelta
from sqlalchemy import Index
