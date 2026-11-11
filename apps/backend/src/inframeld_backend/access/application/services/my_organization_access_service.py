from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.my_organization_access_dto import (
    MyOrganizationAccessDTO,
)
from inframeld_backend.access.application.protocols.my_organization_access_reader import (
    MyOrganizationAccessReader,
)
from inframeld_backend.access.application.protocols.organization_access_facts_reader import (
    OrganizationAccessFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class MyOrganizationAccessService(MyOrganizationAccessReader):
    def __init__(self, organization_access_facts_reader: OrganizationAccessFactsReader) -> None:
        self._organization_access_facts_reader = organization_access_facts_reader

    @override
    async def read(self, *, access: AccessContextDTO) -> MyOrganizationAccessDTO:
        facts = await self._organization_access_facts_reader.read(access=access)
        if facts is None:
            raise ResourceNotFoundError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Organization facts changed the authenticated actor.")

        PrincipalAccessEvaluationService.require_human(access=access, principal=facts.principal)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if (
            facts.principal.kind is not PrincipalKind.HUMAN
            or not PrincipalAccessPolicy.may_use_product(eligibility)
        ):
            raise AccessDeniedError()

        return MyOrganizationAccessDTO(
            facts.principal.organization_id,
            facts.principal.id,
            facts.access_revision,
            facts.grants,
        )
