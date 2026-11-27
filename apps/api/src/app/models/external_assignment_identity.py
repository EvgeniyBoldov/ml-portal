"""Verified external identity links owned by the portal."""
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExternalAssignmentIdentity(Base):
    __tablename__ = "external_assignment_identities"
    __table_args__ = (UniqueConstraint("source", "user_id", name="uq_assignment_source_user"),)

    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
