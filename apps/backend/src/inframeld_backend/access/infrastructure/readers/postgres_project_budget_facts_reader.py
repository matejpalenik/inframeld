import asyncio
from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectBudgetFactsReader(ProjectActionFactsReader):
    """Read fresh budget facts under identity, Organization and shared Project coordination."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._application_key_profile = application_key_profile

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Budget facts require the caller's active transaction.")
        try:
            async with asyncio.timeout(5):
                return await self._read(access, action_id, target)
        except TimeoutError:
            raise DependencyUnavailableError(
                "Budget authorization exceeded its database deadline."
            ) from None

    async def _read(
        self, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        """Observe current budget authority in the requested Project scope."""
        installation = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        evidence = access.authentication_evidence
        if isinstance(evidence, (HumanOAuthCredentialBindingDTO, BrowserSessionAuthenticationDTO)):
            await PostgresIdentityCoordinator(self._session).acquire(
                installation_id=InstallationId(installation), identity=evidence.identity
            )

        organization_id = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization_id is None:
            return None
        organization = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization_id)
            .with_for_update(read=True)
        )
        if organization is None:
            return None
        project = await self._session.scalar(
            select(ProjectRow.id)
            .where(
                ProjectRow.id == target.project_id.value, ProjectRow.organization_id == organization
            )
            .with_for_update(read=True)
        )
        if project is None:
            return None

        facts = await PostgresProjectActionFactsReader(
            self._session, application_key_profile=self._application_key_profile
        ).read_action_facts(access=access, action_id=action_id, target=target)
        if facts is not None and facts.principal.organization_id.value != organization:
            raise RuntimeError("Budget facts changed their Organization scope.")
        return facts
