from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanLifecycleFactsDTO(AuthorizedOperationScope[None]):
    """Observe exact actor/target scope and original cleanup after coordination.

    Cleanup confirmation is observation, never dispatch or restoration authority.
    """

    installation_id: InstallationId
    organization_id: OrganizationId
    access_revision: int
    action_id: ActionId
    actor: Principal
    actor_has_pending_recovery: bool
    actor_credential_facts: HumanCredentialFactsDTO | None
    actor_has_action: bool
    target: Principal | None
    target_identity: VerifiedHumanIdentityDTO | None
    target_version: HumanCredentialVersion | None
    current_suspension: HumanSuspension | None
    required_cleanup_confirmed: bool
    has_newer_recovery_block: bool
    project_id: None = None
