from uuid import UUID

from sqlalchemy import BigInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class HumanCredentialVersionRow(AccessPersistenceBase):
    """Keep one durable generation independently of local account admission."""

    __tablename__ = "human_credential_versions"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    authority: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
