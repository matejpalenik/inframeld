from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_grant_item_dto import (
    ModelConnectionGrantItemDTO,
)


@dataclass(frozen=True, slots=True)
class ModelConnectionGrantsPageDTO:
    items: tuple[ModelConnectionGrantItemDTO, ...]
    next_cursor: str | None
