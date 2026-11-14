from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.http.requests.generation_model_settings_request import (
    GenerationModelSettingsRequest,
)
from inframeld_backend.shared.http.requests.model_rate_request import ModelRateRequest


class ModelSettingsMapper:
    """Convert exact native model inputs into their application records."""

    @staticmethod
    def generation(request: GenerationModelSettingsRequest) -> GenerationModelSettingsDTO:
        return GenerationModelSettingsDTO(
            output_tokens=request.output_tokens,
            temperature=request.temperature,
            structured_output=request.structured_output,
            role=request.role,
        )

    @staticmethod
    def rate(request: ModelRateRequest) -> SpendingRateDTO:
        return SpendingRateDTO(request.category, request.unit, request.usd_per_unit)
