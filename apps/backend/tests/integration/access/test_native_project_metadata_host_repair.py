"""Qualify real private Ory proof at the installed host-maintenance boundary.

The staged test OAuth exchange does not claim production CLI login/provisioning delivery.
"""

import os
from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import HttpUrl
from sqlalchemy import delete, select, update
from tests.support.hydra_provider import API_AUDIENCE, HYDRA_ISSUER, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import create_browser, register_human
from tests.support.project_metadata_maintenance_command import run_project_metadata_maintenance
from tests.support.project_metadata_scenarios import seed_metadata_repair_recipient

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
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
async def test_real_recipient_proof_current_generation_and_proof_independent_receipt_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with hydra_test_provider() as provider, create_browser() as browser:
        human = await register_human(browser)
        identity = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), human.subject)
        seed, binding = await seed_metadata_repair_recipient(database, identity)
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
            assert verified.actor_principal_id == seed.principal_id
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
            "operationId": "native-metadata-repair",
            "operatorLabel": "Native host operator",
            "reason": "Repair exact metadata responsibility",
            "expectedAccessRevision": 0,
            "expectedIdentityId": str(UUID(identity.subject.value)),
            "identityProof": {
                "kind": "hydra-access-token",
                "accessToken": tokens.access_token.value,
            },
            "responsibility": {
                "kind": "action-grantor",
                "target": {"kind": "project", "projectId": str(seed.project_id.value)},
                "actionId": "edit-project-metadata",
            },
        }
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
                and code in {value.value for value in ProjectMetadataMaintenanceErrorCode}
                else "unrecognized"
            )
            pytest.fail(f"Maintenance status={status}, safe_code={safe_code}", pytrace=False)
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value
                )
            )
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
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
                await session.scalars(
                    select(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == seed.project_id.value
                    )
                )
            ).all() == []
