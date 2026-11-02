from uuid import UUID

from sqlalchemy import BigInteger, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ArtifactStorageCapacityRow(SharedPersistenceBase):
    __tablename__ = "artifact_storage_capacity"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    spool_reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    protected_reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    occupied_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
