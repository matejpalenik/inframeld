from typing import override
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_writer import (
    FirstAdministratorBootstrapWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.first_administrator_bootstrap_policy import (
    FirstAdministratorBootstrapPolicy,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow


class PostgresFirstAdministratorBootstrapWriter(FirstAdministratorBootstrapWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def bootstrap(
        self,
        *,
        facts: FirstAdministratorBootstrapFactsDTO,
        receipt: FirstAdministratorBootstrapReceiptDTO,
    ) -> bool:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Bootstrap persistence requires an active caller transaction.")
        result = receipt.result
        if (
            facts.installation_id != result.installation_id
            or facts.identity != receipt.identity
            or facts.principal is not None
            or facts.has_business_state
            or facts.has_bootstrap_claim
            or facts.credential_state.has_pending_recovery
            or receipt.expected_identity_id != UUID(receipt.identity.subject.value)
            or receipt.before_revision != 0
            or result.access_revision != 1
        ):
            raise RuntimeError("Bootstrap persistence has no coherent pristine authorization.")
        inserted = await self._session.scalar(
            insert(HostMaintenanceReceiptRow)
            .values(
                installation_id=result.installation_id.value,
                operator_request_id=result.operation_id.value,
                authority=receipt.identity.authority.value,
                subject=receipt.identity.subject.value,
                mode="bootstrap-first-administrator",
                recovery_operation_id=None,
                operator_label=receipt.operator_label,
                reason=receipt.reason,
                authorized_at=receipt.authorized_at,
                outcome="bootstrapped",
                released=None,
                run_id=None,
                deadline=None,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    HostMaintenanceReceiptRow.installation_id,
                    HostMaintenanceReceiptRow.operator_request_id,
                ]
            )
            .returning(HostMaintenanceReceiptRow.operator_request_id)
        )
        if inserted is None:
            return False

        organization = OrganizationRow(
            id=result.organization_id.value,
            name=FirstAdministratorBootstrapPolicy.ORGANIZATION_NAME,
        )
        self._session.add(organization)
        await self._session.flush()
        locked = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization.id)
            .with_for_update()
        )
        if locked != organization.id or organization.access_revision != 0:
            raise RuntimeError("The new installation Organization has no initial revision.")
        organization.access_revision = result.access_revision
        self._session.add(
            PrincipalRow(
                id=result.recipient_id.value,
                organization_id=organization.id,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name=receipt.identity.subject.value,
            )
        )
        await self._session.flush()
        self._session.add(
            HumanIdentityLinkRow(
                authority=receipt.identity.authority.value,
                subject=receipt.identity.subject.value,
                organization_id=organization.id,
                principal_id=result.recipient_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        for action in FirstAdministratorBootstrapPolicy.ORGANIZATION_ACTIONS:
            self._session.add(
                OrganizationActionGrantRow(
                    organization_id=organization.id,
                    recipient_principal_id=result.recipient_id.value,
                    action=action,
                    recipient_kind=PrincipalKind.HUMAN,
                    can_grant=True,
                    assigned_by_principal_id=None,
                )
            )
        self._session.add(
            FirstAdministratorBootstrapReceiptRow(
                installation_id=result.installation_id.value,
                operator_request_id=result.operation_id.value,
                organization_id=organization.id,
                organization_name=organization.name,
                recipient_id=result.recipient_id.value,
                expected_identity_id=receipt.expected_identity_id,
                request_fingerprint=receipt.fingerprint.value,
                before_revision=receipt.before_revision,
                after_revision=result.access_revision,
            )
        )
        await self._session.flush()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization.id,
                actor_kind="operator",
                actor_reference=receipt.operator_label,
                affected_principal_id=result.recipient_id.value,
                event_type="first_administrator_bootstrapped",
                target_kind="organization",
                target_id=organization.id,
                before_values={"access_revision": 0},
                after_values={
                    "access_revision": 1,
                    "actions": list(FirstAdministratorBootstrapPolicy.ORGANIZATION_ACTIONS),
                },
                reason=receipt.reason,
                correlation_id=result.operation_id.value,
            )
        )
        await self._session.flush()
        return True
