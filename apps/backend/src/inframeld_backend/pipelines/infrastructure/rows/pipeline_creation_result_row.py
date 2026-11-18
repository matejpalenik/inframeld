from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class PipelineCreationResultRow(SharedPersistenceBase):
    """Preserve the original settings revision, labels and initial assignments."""

    __tablename__ = "pipeline_creation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    creator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    pipeline_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    configuration_revision: Mapped[int] = mapped_column(BigInteger)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    project_access_revision: Mapped[int] = mapped_column(BigInteger)
    initial_actions: Mapped[list[str]] = mapped_column(JSONB)
    can_grant: Mapped[bool] = mapped_column(Boolean)
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
