from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class HumanAdmissionResultReader(Protocol):
    """Recover a retained original result after current admission checks.

    Match installation, exact identity, Org, actor and original operation. Require
    recognized REPLAYABLE/SAFE_RESULT parent metadata and its original expiry.
    Result retention never owns the admitted principal or identity link.
    """

    @abstractmethod
    async def original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanAdmissionResultDTO: ...
