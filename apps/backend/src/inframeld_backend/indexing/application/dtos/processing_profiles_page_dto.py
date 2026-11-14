from dataclasses import dataclass

from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO


@dataclass(frozen=True, slots=True)
class ProcessingProfilesPageDTO:
    items: tuple[ProcessingProfileDTO, ...]
    next_cursor: str | None
