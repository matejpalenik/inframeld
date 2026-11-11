"""Qualify real private Ory proof at the installed host-maintenance boundary.

The staged test OAuth exchange does not claim production CLI login/provisioning delivery.
"""

import os
from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import HttpUrl
from sqlalchemy import delete, func, select, update
from tests.support.hydra_provider import API_AUDIENCE, HYDRA_ISSUER, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import create_browser, register_human
from tests.support.project_metadata_maintenance_command import run_project_metadata_maintenance
from tests.support.project_metadata_scenarios import (
    seed_metadata_repair_recipient,
    seed_stranded_repair_target,
)

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.stranded_authority_repair_receipt_row import (
    StrandedAuthorityRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.settings.human_authentication_settings import (
    HumanAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires private Kratos/Hydra integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_kind",
    ["metadata", "organization", "project", "group-manager", "group-action", "application-account"],
)
async def test_real_recipient_proof_current_generation_and_proof_independent_receipt_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings, target_kind: str
) -> None:
    async with hydra_test_provider() as provider, create_browser() as browser:
        human = await register_human(browser)
        identity = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), human.subject)
        if target_kind == "metadata":
            seed, binding = await seed_metadata_repair_recipient(database, identity)
            recipient_id = seed.principal_id
            project_id = seed.project_id
            organization_id = seed.organization_id
            revision = 0
            responsibility: dict[str, object] = {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(project_id.value)},
                "actionId": "edit-project-metadata",
            }
            group_id = None
            application_id = None
            action = "edit-project-metadata"
        else:
            access, native_command, _ = await seed_stranded_repair_target(
                database, target_kind, identity=identity
            )
            binding = access.authentication_evidence
            assert isinstance(binding, HumanOAuthCredentialBindingDTO)
            recipient_id = access.actor_principal_id
            observed = native_command.responsibility
            revision = native_command.expected_access_revision
            project_id = None
            group_id = None
            application_id = None
            async with database.session() as session:
                actor = await session.get(PrincipalRow, recipient_id.value)
                assert actor is not None
                organization_id = OrganizationId(actor.organization_id)
            if isinstance(observed, GroupManagerRepairResponsibilityDTO):
                project_id = observed.project_id
                group_id = observed.access_group_id
                action = None
                responsibility = {
                    "kind": "group-manager",
                    "projectId": str(project_id.value),
                    "accessGroupId": str(group_id.value),
                }
            else:
                action = observed.action_id.value
                target = observed.target
                if isinstance(target, OrganizationGrantTargetDTO):
                    scope = {
                        "kind": "organization",
                        "organizationId": str(target.organization_id.value),
                    }
                elif isinstance(target, ProjectGrantTargetDTO):
                    project_id = target.project_id
                    scope = {"kind": "project", "projectId": str(project_id.value)}
                elif isinstance(target, AccessGroupGrantTargetDTO):
                    project_id, group_id = target.project_id, target.access_group_id
                    scope = {
                        "kind": "access-group",
                        "projectId": str(project_id.value),
                        "accessGroupId": str(group_id.value),
                    }
                    async with database.session() as session, session.begin():
                        await session.scalar(
                            select(ProjectRow.id)
                            .where(ProjectRow.id == project_id.value)
                            .with_for_update()
                        )
                        await session.execute(
                            delete(GroupManagerRow).where(
                                GroupManagerRow.project_id == project_id.value,
                                GroupManagerRow.group_id == group_id.value,
                            )
                        )
                        await session.execute(
                            update(ProjectRow)
                            .where(ProjectRow.id == project_id.value)
                            .values(access_revision=ProjectRow.access_revision + 1)
                        )
                    revision += 1
                else:
                    assert isinstance(target, ApplicationAccountGrantTargetDTO)
                    project_id, application_id = target.project_id, target.application_principal_id
                    scope = {
                        "kind": "application-account",
                        "projectId": str(project_id.value),
                        "applicationPrincipalId": str(application_id.value),
                    }
                responsibility = {"kind": "action-grantor", "target": scope, "actionId": action}
        tokens = await provider.issue_tokens(human, browser=browser, credential_binding=binding)
        assert await provider.token_is_active(tokens.access_token)
        components = create_access_components(
            KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                admin_url=HttpUrl(KRATOS_ADMIN_URL),
                authority=identity.authority,
            ),
            HydraSettings(
                admin_url=HttpUrl(HYDRA_ADMIN_URL), issuer=HYDRA_ISSUER, api_audience=API_AUDIENCE
            ),
            database,
            human_authentication_settings=HumanAuthenticationSettings(),
        )
        try:
            authenticator = components.access_token_authenticator
            assert authenticator is not None
            verified = await authenticator.authenticate(tokens.access_token)
            assert verified.actor_principal_id == recipient_id
        finally:
            for client in (
                components.kratos_client,
                components.kratos_admin_client,
                components.hydra_client,
            ):
                if client is not None:
                    client.rest_client.pool_manager.clear()

        request: dict[str, object] = {
            "schemaVersion": 1,
            "mode": "repair-stranded-authority",
            "expectedInstallationId": str(binding.installation_id.value),
            "operationId": "native-authority-repair",
            "operatorLabel": "Native host operator",
            "reason": "Repair exact reviewed Access responsibility",
            "expectedAccessRevision": revision,
            "expectedIdentityId": str(UUID(identity.subject.value)),
            "identityProof": {
                "kind": "hydra-access-token",
                "accessToken": tokens.access_token.value,
            },
            "responsibility": responsibility,
        }
        status, invalid, _ = await run_project_metadata_maintenance(
            request | {"expectedAccessRevision": 1.0}, temporary_postgres_settings
        )
        assert status == 2 and invalid["code"] == "invalid_input"
        status, rejected, _ = await run_project_metadata_maintenance(
            request | {"expectedIdentityId": str(UUID(int=1))}, temporary_postgres_settings
        )
        assert status == 1 and rejected["code"] == "invalid_identity_proof"
        rejected_tokens = await provider.issue_tokens(
            human, browser=browser, credential_binding=binding
        )
        await provider.revoke_access_token(rejected_tokens.access_token)
        assert not await provider.token_is_active(rejected_tokens.access_token)
        status, rejected, _ = await run_project_metadata_maintenance(
            request
            | {
                "identityProof": {
                    "kind": "hydra-access-token",
                    "accessToken": rejected_tokens.access_token.value,
                }
            },
            temporary_postgres_settings,
        )
        assert status == 1 and rejected["code"] == "invalid_identity_proof"
        async with database.session() as session:
            assert (
                await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow))
                == 0
            )
        status, first, diagnostics = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        if tokens.access_token.value.encode() in diagnostics:
            pytest.fail("Recipient proof appeared in private command diagnostics.", pytrace=False)
        if status != 0 or first.get("outcome") != "repaired":
            code = first.get("code")
            safe_code = (
                code
                if isinstance(code, str)
                and code in {value.value for value in StrandedAuthorityMaintenanceErrorCode}
                else "unrecognized"
            )
            pytest.fail(f"Maintenance status={status}, safe_code={safe_code}", pytrace=False)
        recovery_request = {
            "schemaVersion": 1,
            "mode": "resume-recovery-cleanup",
            "expectedInstallationId": request["expectedInstallationId"],
            "operationId": request["operationId"],
            "operatorLabel": request["operatorLabel"],
            "reason": request["reason"],
            "recoveryOperationId": "unrelated-recovery",
        }
        status, conflict, _ = await run_project_metadata_maintenance(
            recovery_request, temporary_postgres_settings
        )
        assert status == 1 and conflict["code"] == "idempotency_key_reused"
        assert first["responsibility"] == responsibility
        assert first["principalId"] == str(recipient_id.value)
        assert first["accessRevision"] == revision + 1
        async with database.session() as session:
            if project_id is None:
                assert action is not None
                organization_grant = await session.get(
                    OrganizationActionGrantRow, (organization_id.value, recipient_id.value, action)
                )
                assert organization_grant is not None
                assert (
                    organization_grant.organization_id,
                    organization_grant.recipient_principal_id,
                    organization_grant.recipient_kind,
                    organization_grant.action,
                    organization_grant.can_grant,
                ) == (organization_id.value, recipient_id.value, PrincipalKind.HUMAN, action, True)
                stored_revision = await session.scalar(
                    select(OrganizationRow.access_revision).where(
                        OrganizationRow.id == organization_id.value
                    )
                )
                audit_kind, audit_target = "organization", organization_id.value
            else:
                stored_revision = await session.scalar(
                    select(ProjectRow.access_revision).where(ProjectRow.id == project_id.value)
                )
                audit_kind, audit_target = "project", project_id.value
                if target_kind == "group-manager":
                    assert group_id is not None
                    member = await session.get(
                        GroupMembershipRow, (project_id.value, group_id.value, recipient_id.value)
                    )
                    manager = await session.get(
                        GroupManagerRow, (project_id.value, group_id.value, recipient_id.value)
                    )
                    assert member is not None and manager is not None
                    assert (member.project_id, member.group_id, member.principal_id) == (
                        project_id.value,
                        group_id.value,
                        recipient_id.value,
                    )
                    assert (
                        manager.project_id,
                        manager.group_id,
                        manager.principal_id,
                        manager.principal_kind,
                    ) == (project_id.value, group_id.value, recipient_id.value, PrincipalKind.HUMAN)
                    audit_kind, audit_target = "access_group", group_id.value
                elif target_kind == "group-action":
                    assert group_id is not None and action is not None
                    group_grant = await session.get(
                        GroupActionGrantRow,
                        (project_id.value, group_id.value, recipient_id.value, action),
                    )
                    assert group_grant is not None
                    assert (
                        group_grant.project_id,
                        group_grant.group_id,
                        group_grant.recipient_principal_id,
                        group_grant.recipient_kind,
                        group_grant.action,
                        group_grant.can_grant,
                    ) == (
                        project_id.value,
                        group_id.value,
                        recipient_id.value,
                        PrincipalKind.HUMAN,
                        action,
                        True,
                    )
                    audit_kind, audit_target = "access_group", group_id.value
                elif target_kind == "application-account":
                    assert application_id is not None and action is not None
                    application_grant = await session.get(
                        ApplicationActionGrantRow,
                        (project_id.value, application_id.value, recipient_id.value, action),
                    )
                    assert application_grant is not None
                    assert (
                        application_grant.project_id,
                        application_grant.application_principal_id,
                        application_grant.recipient_principal_id,
                        application_grant.recipient_kind,
                        application_grant.action,
                        application_grant.can_grant,
                    ) == (
                        project_id.value,
                        application_id.value,
                        recipient_id.value,
                        PrincipalKind.HUMAN,
                        action,
                        True,
                    )
                    audit_kind, audit_target = "application_account", application_id.value
                else:
                    assert action is not None
                    project_grant = await session.get(
                        ProjectActionGrantRow, (project_id.value, recipient_id.value, action)
                    )
                    assert project_grant is not None
                    assert (
                        project_grant.project_id,
                        project_grant.recipient_principal_id,
                        project_grant.recipient_kind,
                        project_grant.action,
                        project_grant.can_grant,
                    ) == (project_id.value, recipient_id.value, PrincipalKind.HUMAN, action, True)
            assert stored_revision == first["accessRevision"] == revision + 1
            original_key = (binding.installation_id.value, "native-authority-repair")
            parent = await session.get(HostMaintenanceReceiptRow, original_key)
            assert parent is not None
            assert (
                parent.authority,
                parent.subject,
                parent.mode,
                parent.outcome,
                parent.operator_label,
                parent.reason,
            ) == (
                identity.authority.value,
                identity.subject.value,
                "repair-stranded-authority",
                "repaired",
                request["operatorLabel"],
                request["reason"],
            )
            legacy_original = await session.get(ProjectMetadataRepairReceiptRow, original_key)
            broader_original = await session.get(StrandedAuthorityRepairReceiptRow, original_key)
            if target_kind == "metadata":
                assert (
                    legacy_original is not None
                    and broader_original is None
                    and project_id is not None
                )
                assert (
                    legacy_original.organization_id,
                    legacy_original.project_id,
                    legacy_original.recipient_id,
                    legacy_original.expected_identity_id,
                    legacy_original.before_revision,
                    legacy_original.after_revision,
                ) == (
                    organization_id.value,
                    project_id.value,
                    recipient_id.value,
                    UUID(identity.subject.value),
                    revision,
                    first["accessRevision"],
                )
            else:
                assert broader_original is not None and legacy_original is None
                assert (
                    broader_original.organization_id,
                    broader_original.recipient_id,
                    broader_original.expected_identity_id,
                    broader_original.before_revision,
                    broader_original.after_revision,
                ) == (
                    organization_id.value,
                    recipient_id.value,
                    UUID(identity.subject.value),
                    revision,
                    first["accessRevision"],
                )
                assert (
                    broader_original.responsibility_kind,
                    broader_original.target_kind,
                    broader_original.project_id,
                    broader_original.access_group_id,
                    broader_original.application_account_id,
                    broader_original.action_id,
                ) == (
                    responsibility["kind"],
                    audit_kind.replace("_", "-"),
                    None if project_id is None else project_id.value,
                    None if group_id is None else group_id.value,
                    None if application_id is None else application_id.value,
                    action,
                )
            audits = (
                await session.scalars(
                    select(AccessAuditEventRow).where(
                        AccessAuditEventRow.correlation_id == "native-authority-repair"
                    )
                )
            ).all()
            assert len(audits) == 1
            audit = audits[0]
            assert (
                audit.organization_id,
                audit.project_id,
                audit.affected_principal_id,
                audit.target_kind,
                audit.target_id,
                audit.action,
                audit.actor_kind,
                audit.actor_reference,
                audit.reason,
            ) == (
                organization_id.value,
                None if project_id is None else project_id.value,
                recipient_id.value,
                audit_kind,
                audit_target,
                action,
                "operator",
                request["operatorLabel"],
                request["reason"],
            )
            assert audit.event_type == (
                "project_metadata_authority_repaired"
                if target_kind == "metadata"
                else "stranded_authority_repaired"
            )
            assert audit.before_values == {"access_revision": revision}
            assert audit.after_values == (
                {"access_revision": first["accessRevision"], "member": True, "manager": True}
                if target_kind == "group-manager"
                else {"access_revision": first["accessRevision"], "can_grant": True}
            )
        async with database.session() as session, session.begin():
            if project_id is None:
                await session.execute(
                    delete(OrganizationActionGrantRow).where(
                        OrganizationActionGrantRow.organization_id == organization_id.value,
                        OrganizationActionGrantRow.recipient_principal_id == recipient_id.value,
                        OrganizationActionGrantRow.action == action,
                    )
                )
                await session.execute(
                    update(OrganizationRow)
                    .where(OrganizationRow.id == organization_id.value)
                    .values(access_revision=OrganizationRow.access_revision + 1)
                )
            else:
                if target_kind == "group-manager":
                    assert group_id is not None
                    await session.execute(
                        delete(GroupManagerRow).where(
                            GroupManagerRow.project_id == project_id.value,
                            GroupManagerRow.group_id == group_id.value,
                        )
                    )
                    await session.execute(
                        delete(GroupMembershipRow).where(
                            GroupMembershipRow.project_id == project_id.value,
                            GroupMembershipRow.group_id == group_id.value,
                        )
                    )
                elif target_kind == "group-action":
                    assert group_id is not None
                    await session.execute(
                        delete(GroupActionGrantRow).where(
                            GroupActionGrantRow.project_id == project_id.value,
                            GroupActionGrantRow.group_id == group_id.value,
                            GroupActionGrantRow.action == action,
                        )
                    )
                elif target_kind == "application-account":
                    assert application_id is not None
                    await session.execute(
                        delete(ApplicationActionGrantRow).where(
                            ApplicationActionGrantRow.project_id == project_id.value,
                            ApplicationActionGrantRow.application_principal_id
                            == application_id.value,
                            ApplicationActionGrantRow.action == action,
                        )
                    )
                else:
                    await session.execute(
                        delete(ProjectActionGrantRow).where(
                            ProjectActionGrantRow.project_id == project_id.value,
                            ProjectActionGrantRow.action == action,
                        )
                    )
                await session.execute(
                    update(ProjectRow)
                    .where(ProjectRow.id == project_id.value)
                    .values(access_revision=ProjectRow.access_revision + 1)
                )
        refreshed = await provider.refresh_tokens(tokens)
        assert refreshed is not None
        request["identityProof"] = {
            "kind": "hydra-access-token",
            "accessToken": refreshed.access_token.value,
        }
        status, replay, _ = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        assert status == 0 and replay == first
        async with database.session() as session, session.begin():
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=binding.installation_id, identity=identity
            )
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == binding.installation_id.value,
                    HumanCredentialVersionRow.authority == identity.authority.value,
                    HumanCredentialVersionRow.subject == identity.subject.value,
                )
                .values(version=binding.version.value + 1)
            )
        assert await provider.token_is_active(refreshed.access_token)
        status, denied, _ = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        assert status == 1 and denied["code"] == "invalid_identity_proof"
        fresh_binding = replace(binding, version=HumanCredentialVersion(binding.version.value + 1))
        fresh = await provider.issue_tokens(
            human, browser=browser, credential_binding=fresh_binding
        )
        request["identityProof"] = {
            "kind": "hydra-access-token",
            "accessToken": fresh.access_token.value,
        }
        status, recovered, _ = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        assert status == 0 and recovered == first
        async with database.session() as session:
            assert (
                await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow))
                == 1
            )
            if target_kind == "group-manager":
                assert group_id is not None
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(GroupManagerRow)
                        .where(GroupManagerRow.group_id == group_id.value)
                    )
                    == 0
                )
            elif target_kind == "group-action":
                assert group_id is not None
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(GroupActionGrantRow)
                        .where(
                            GroupActionGrantRow.group_id == group_id.value,
                            GroupActionGrantRow.action == action,
                        )
                    )
                    == 0
                )
            elif target_kind == "application-account":
                assert application_id is not None
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ApplicationActionGrantRow)
                        .where(
                            ApplicationActionGrantRow.application_principal_id
                            == application_id.value,
                            ApplicationActionGrantRow.action == action,
                        )
                    )
                    == 0
                )
            elif target_kind == "organization":
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(OrganizationActionGrantRow)
                        .where(
                            OrganizationActionGrantRow.organization_id == organization_id.value,
                            OrganizationActionGrantRow.action == action,
                        )
                    )
                    == 0
                )
            else:
                assert project_id is not None
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ProjectActionGrantRow)
                        .where(
                            ProjectActionGrantRow.project_id == project_id.value,
                            ProjectActionGrantRow.action == action,
                        )
                    )
                    == 0
                )
