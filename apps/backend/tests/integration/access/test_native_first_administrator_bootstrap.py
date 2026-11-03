"""Verify staged Ory proof through installed protected stdin and real PostgreSQL.

This fixture exchange is not an operator proof-acquisition procedure. The current
recipient-proof CLI requires admission and cannot acquire a first-user proof.
"""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.first_administrator_bootstrap_scenarios import bootstrap_scenario
from tests.support.hydra_provider import hydra_test_provider
from tests.support.kratos_browser import create_browser, register_human
from tests.support.project_metadata_maintenance_command import run_project_metadata_maintenance

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode,
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
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires private Kratos/Hydra integration services",
)


@pytest.mark.asyncio
async def test_real_unadmitted_proof_claim_and_current_proof_original_receipt_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with hydra_test_provider() as provider, create_browser() as browser:
        human = await register_human(browser)
        identity = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), human.subject)
        scenario = await bootstrap_scenario(database, identity=identity)
        binding = scenario.binding
        tokens = await provider.issue_tokens(human, browser=browser, credential_binding=binding)
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0
        request: dict[str, object] = {
            "schemaVersion": 1,
            "mode": "bootstrap-first-administrator",
            "expectedInstallationId": str(binding.installation_id.value),
            "operationId": "native-first-administrator",
            "expectedAccessRevision": 0,
            "expectedIdentityId": str(uuid4()),
            "operatorLabel": "Native host operator",
            "reason": "First administrator verification",
            "identityProof": {
                "kind": "hydra-access-token",
                "accessToken": tokens.access_token.value,
            },
        }
        status, denied, diagnostics = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        if tokens.access_token.value.encode() in diagnostics:
            pytest.fail("Proof appeared in command diagnostics.", pytrace=False)
        assert status == 1 and denied.get("code") == "invalid_identity_proof"
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(OrganizationRow)) == 0

        request["expectedIdentityId"] = identity.subject.value
        status, first, diagnostics = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        if tokens.access_token.value.encode() in diagnostics:
            pytest.fail("Proof appeared in command diagnostics.", pytrace=False)
        if status != 0 or first.get("outcome") != "bootstrapped":
            code = first.get("code")
            safe_code = (
                code
                if isinstance(code, str)
                and code in {item.value for item in FirstAdministratorBootstrapErrorCode}
                else "unrecognized"
            )
            pytest.fail(f"Bootstrap status={status}, safe_code={safe_code}", pytrace=False)
        assert first["accessRevision"] == 1
        async with database.session() as session, session.begin():
            assert (
                await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow))
                == 4
            )
            await session.execute(delete(OrganizationActionGrantRow))
            await session.execute(update(OrganizationRow).values(access_revision=9))
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
        status, stale, _ = await run_project_metadata_maintenance(
            request, temporary_postgres_settings
        )
        assert status == 1 and stale.get("code") == "invalid_identity_proof"
        fresh = await provider.issue_tokens(
            human,
            browser=browser,
            credential_binding=replace(
                binding, version=HumanCredentialVersion(binding.version.value + 1)
            ),
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
            assert await session.scalar(select(OrganizationRow.access_revision)) == 9
            assert (
                await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow))
                == 0
            )
