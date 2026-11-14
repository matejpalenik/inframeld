from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO


@dataclass(frozen=True, slots=True)
class ModelConnectionsPageDTO:
    items: tuple[ModelConnectionDTO, ...]
    next_cursor: str | None
