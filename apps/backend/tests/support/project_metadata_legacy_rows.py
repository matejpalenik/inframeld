"""Map the actual pre-0014 columns for upgrade fixtures. Never create a schema here."""

from uuid import UUID

from sqlalchemy import String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class LegacyMetadataBase(MappedAsDataclass, DeclarativeBase, kw_only=True, eq=False):
    pass


class LegacyProjectRow(LegacyMetadataBase):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
