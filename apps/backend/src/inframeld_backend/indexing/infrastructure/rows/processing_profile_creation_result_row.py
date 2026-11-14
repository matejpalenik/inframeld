from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ProcessingProfileCreationResultRow(SharedPersistenceBase):
    """Keep the original creator assignments and revision when current authority changes."""

    __tablename__ = "processing_profile_creation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    creator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    processing_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    project_access_revision: Mapped[int] = mapped_column(BigInteger)
    initial_actions: Mapped[list[str]] = mapped_column(JSONB)
    can_grant: Mapped[bool] = mapped_column(Boolean)
