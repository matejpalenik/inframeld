from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_usage_item_dto import (
    ModelConnectionUsageItemDTO,
)


@dataclass(frozen=True, slots=True)
class ModelConnectionUsagePageDTO:
    items: tuple[ModelConnectionUsageItemDTO, ...]
    next_cursor: str | None
