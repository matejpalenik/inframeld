from dataclasses import dataclass

from inframeld_backend.access.application.dtos.grant_recipient_dto import GrantRecipientDTO


@dataclass(frozen=True, slots=True)
class GrantRecipientsPageDTO:
    items: tuple[GrantRecipientDTO, ...]
    next_cursor: str | None
