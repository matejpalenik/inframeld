from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_preview_facts_dto import (
    InvitationPreviewFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)


class InvitationPreviewFactsReader(Protocol):
    @abstractmethod
    async def read_preview(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationPreviewFactsDTO | None:
        """Read exact retained intent and current facts in the caller's short read transaction.

        None means no matching digest. Missing or wrong-parent current targets
        produce absent scopes, while missing security metadata is unavailable.
        Labels contain only the baseline Organization, affected Projects and intended
        targets, deduplicated within 201 items. Perform no provider or state writes.
        """
        ...
