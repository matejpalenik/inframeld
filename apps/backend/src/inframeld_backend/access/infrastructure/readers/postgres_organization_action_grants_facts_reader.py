from typing import override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_assignment_dto import (
    OrganizationActionGrantAssignmentDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grants_page_facts_dto import (
    OrganizationActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.protocols.organization_action_grants_facts_reader import (
    OrganizationActionGrantsFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresOrganizationActionGrantsFactsReader(OrganizationActionGrantsFactsReader):
    """Observe stored assignments and current authority in one bounded snapshot.

    The lateral page retains the actor header when continuation is empty and
    deliberately preserves assignments to recipients who are no longer eligible.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> OrganizationActionGrantsPageFactsDTO | None:
        assignment = aliased(OrganizationActionGrantRow, name="stored_assignment")
        page = select(assignment).where(
            assignment.organization_id == OrganizationRow.id,
            assignment.action == action_id.value,
        )
        if after is not None:
            page = page.where(assignment.recipient_principal_id > after.value)
        bounded = (
            page.order_by(assignment.recipient_principal_id)
            .limit(limit + 1)
            .correlate(OrganizationRow)
            .lateral("assignments_page")
        )
        stored = aliased(OrganizationActionGrantRow, bounded)
        delegated = (
            exists()
            .where(
                OrganizationActionGrantRow.organization_id == OrganizationRow.id,
                OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                OrganizationActionGrantRow.recipient_kind == PrincipalRow.kind,
                OrganizationActionGrantRow.action == action_id.value,
                OrganizationActionGrantRow.can_grant.is_(True),
            )
            .correlate(PrincipalRow, OrganizationRow)
        )
        evidence = access.authentication_evidence
        linked = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else Nullable(literal(None, BigInteger))
        )
        statement = (
            select(
                PrincipalRow,
                Nullable(InstallationIdentityRow.installation_id),
                delegated,
                ProjectPrincipalQueries.pending(
                    PrincipalRow.id, InstallationIdentityRow.installation_id
                ),
                linked,
                version,
                Nullable(stored),
            )
            .select_from(PrincipalRow)
            .join(
                OrganizationRow,
                and_(
                    OrganizationRow.id == organization_id.value,
                    OrganizationRow.id == PrincipalRow.organization_id,
                ),
            )
            .outerjoin(InstallationIdentityRow, InstallationIdentityRow.singleton_key == 1)
            .outerjoin(bounded, true())
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .order_by(stored.recipient_principal_id)
            .execution_options(populate_existing=True, autoflush=False)
        )
        try:
            rows = (await self._session.execute(statement)).tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error
        if not rows:
            return None
        principal, installed, can_grant, pending, matches, current_version, _ = rows[0]
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")

        return OrganizationActionGrantsPageFactsDTO(
            installation_id=InstallationId(installed),
            organization_id=OrganizationId(principal.organization_id),
            action_id=action_id,
            actor_can_grant=can_grant,
            actor=Principal(
                id=PrincipalId(principal.id),
                organization_id=OrganizationId(principal.organization_id),
                kind=principal.kind,
                status=principal.status,
            ),
            actor_has_pending_recovery=pending,
            actor_oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                binding_matches_actor=matches,
                current_version=HumanCredentialVersion(current_version)
                if current_version is not None
                else None,
            )
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else None,
            items=tuple(
                OrganizationActionGrantAssignmentDTO(
                    recipient_principal_id=PrincipalId(item.recipient_principal_id),
                    action_id=ActionId(item.action),
                    can_grant=item.can_grant,
                )
                for _, _, _, _, _, _, item in rows
                if item is not None
            ),
        )
