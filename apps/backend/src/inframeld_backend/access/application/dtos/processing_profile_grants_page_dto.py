from dataclasses import dataclass

from inframeld_backend.access.application.dtos.processing_profile_grant_item_dto import (
    ProcessingProfileGrantItemDTO,
)


@dataclass(frozen=True, slots=True)
class ProcessingProfileGrantsPageDTO:
    items: tuple[ProcessingProfileGrantItemDTO, ...]
    next_cursor: str | None
