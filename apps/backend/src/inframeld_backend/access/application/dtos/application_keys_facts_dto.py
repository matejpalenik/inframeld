from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_account_read_facts_dto import (
    ApplicationAccountReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeysFactsDTO:
    account: ApplicationAccountReadFactsDTO
    keys: tuple[ApplicationKeyMetadataDTO, ...]
