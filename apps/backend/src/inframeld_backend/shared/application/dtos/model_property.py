from inframeld_backend.shared.application.dtos.conflicting_model_property_dto import (
    ConflictingModelPropertyDTO,
)
from inframeld_backend.shared.application.dtos.known_model_property_dto import KnownModelPropertyDTO
from inframeld_backend.shared.application.dtos.unknown_model_property_dto import (
    UnknownModelPropertyDTO,
)

type ModelProperty[T] = (
    KnownModelPropertyDTO[T] | UnknownModelPropertyDTO | ConflictingModelPropertyDTO[T]
)
