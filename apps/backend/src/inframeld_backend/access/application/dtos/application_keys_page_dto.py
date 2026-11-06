from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeysPageDTO:
    items: tuple[ApplicationKeyMetadataDTO, ...]
    next_cursor: str | None
