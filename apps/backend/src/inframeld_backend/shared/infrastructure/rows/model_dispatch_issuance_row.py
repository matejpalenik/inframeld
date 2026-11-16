from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ModelDispatchIssuanceRow(SharedPersistenceBase):
    """Retain the original issuer for an accounting call across job and credential changes."""

    __tablename__ = "model_dispatch_issuance"

    call_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    attempt_number: Mapped[int] = mapped_column(Integer)
    fence: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    access_revision: Mapped[int] = mapped_column(BigInteger)
    credential_revision: Mapped[int] = mapped_column(BigInteger)
    adapter_revision: Mapped[str] = mapped_column(String(128))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.clock_timestamp()
    )
