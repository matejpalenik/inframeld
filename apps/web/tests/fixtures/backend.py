"""Run the unchanged production application against this disposable fixture database."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from inframeld_backend.bootstrap.application_settings import ApplicationSettings


def write_proof_inputs(
    directory: Path,
    *,
    installation_id: UUID,
    identity_id: UUID,
    principal_id: UUID,
    project_id: UUID,
    certificate_authority: str,
    environment: dict[str, str],
    operation_id: str = "native-recipient-proof",
) -> None:
    """Prepare only the driver's strict proof-free intent and private execution context."""
    directory.mkdir(mode=0o700)
    host = {
        "schemaVersion": 1,
        "api": "https://inframeld.account.test:8443",
        "issuer": "https://hydra.account.test:8443/",
        "clientId": "inframeld-cli",
        "installationId": str(installation_id),
        "expectedIdentityId": str(identity_id),
        "certificateAuthorities": [certificate_authority],
        "proxy": None,
    }
    request = {
        "schemaVersion": 1,
        "mode": "repair-stranded-authority",
        "expectedInstallationId": str(installation_id),
        "operationId": operation_id,
        "operatorLabel": "Private native fixture",
        "reason": "Restore reviewed metadata authority",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(identity_id),
        "responsibility": {
            "kind": "action-grantor",
            "target": {"kind": "project", "projectId": str(project_id)},
            "actionId": "edit-project-metadata",
        },
    }
    files: dict[str, object] = {
        "host.json": host,
        "request.json": request,
        "exec.json": {
            "program": "/opt/backend/.venv/bin/inframeld-maintenance",
            "args": [],
            "environment": environment,
        },
        "expected.json": {"principalId": str(principal_id)},
    }
    created: list[Path] = []
    try:
        for name, value in files.items():
            content = json.dumps(value).encode()
            if len(content) > 65_536:
                raise ValueError("The private input exceeded its bound.")
            path = directory / name
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as destination:
                os.fchmod(destination.fileno(), 0o600)
                destination.write(content)
    except BaseException:
        for path in created:
            path.unlink()
        directory.rmdir()
        raise


def write_bootstrap_inputs(
    directory: Path,
    *,
    installation_id: UUID,
    identity_id: UUID,
    certificate_authority: str,
    environment: dict[str, str],
    operation_id: str = "native-bootstrap-original",
) -> None:
    """Freeze proof-free intent under the same private file bounds as repair."""
    directory.mkdir(mode=0o700)
    request = {
        "schemaVersion": 1,
        "mode": "bootstrap-first-administrator",
        "expectedInstallationId": str(installation_id),
        "operationId": operation_id,
        "operatorLabel": "Private native fixture",
        "reason": "Reviewed first admission",
        "expectedAccessRevision": 0,
        "expectedIdentityId": str(identity_id),
    }
    files: dict[str, object] = {
        "request.json": request,
        "host.json": {
            "schemaVersion": 1,
            "api": "https://inframeld.account.test:8443",
            "issuer": "https://hydra.account.test:8443/",
            "clientId": "inframeld-cli",
            "installationId": str(installation_id),
            "expectedIdentityId": str(identity_id),
            "certificateAuthorities": [certificate_authority],
            "proxy": None,
        },
        "exec.json": {
            "program": "/opt/backend/.venv/bin/inframeld-maintenance",
            "args": [],
            "environment": environment,
        },
    }
    for name, value in files.items():
        raw = json.dumps(value).encode()
        if len(raw) > 65_536:
            raise ValueError("Private input exceeded its bound.")
        descriptor = os.open(
            directory / name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)


def validate_bootstrap_result(
    raw: bytes, request: dict[str, object], expected_code: str | None = None
) -> dict[str, object] | None:
    """Check the existing public envelope, original receipt and separate cleanup facts."""
    if len(raw) > 65_536:
        raise ValueError("Bootstrap output exceeded its bound.")
    envelope = _object(
        json.loads(raw, object_pairs_hook=_unique),
        {"schemaVersion", "mode", "outcome", "data", "error", "warnings"},
    )
    if (
        envelope["schemaVersion"] != 1
        or envelope["mode"] != "execute"
        or envelope["warnings"] != []
    ):
        raise ValueError("Unexpected bootstrap envelope.")
    data = _object(
        envelope["data"],
        {"maintenance", "currentSession", "credentialCleanup", "consumerErrorCode"},
    )
    maintenance = _object(data["maintenance"], {"effect", "processCleanup", "failure"})
    if data["credentialCleanup"] != "confirmed" or maintenance["processCleanup"] != "confirmed":
        raise ValueError("Bootstrap cleanup is not confirmed.")
    if expected_code is not None:
        if expected_code not in {"already_bootstrapped", "idempotency_key_reused"}:
            raise ValueError("Unsupported controlled denial.")
        error = _object(envelope["error"], {"source", "code", "message"})
        if (
            envelope["outcome"] != "uncertain"
            or error["source"] != "cli"
            or error["code"] != "bootstrap_unconfirmed"
            or data["consumerErrorCode"] != expected_code
            or maintenance["failure"] != "exit"
            or maintenance["effect"]
            != {"status": "unknown", "operation_id": request["operationId"]}
        ):
            raise ValueError("The exact consumer denial was not established.")
        return None
    effect = _object(maintenance["effect"], {"status", "receipt"})
    receipt = _object(
        effect["receipt"],
        {
            "schemaVersion",
            "mode",
            "operationId",
            "installationId",
            "principalId",
            "accessRevision",
            "outcome",
        },
    )
    if (
        envelope["outcome"] != "succeeded"
        or envelope["error"] is not None
        or data["consumerErrorCode"] is not None
        or maintenance["failure"] is not None
        or effect["status"] != "committed"
        or receipt["schemaVersion"] != 1
        or receipt["mode"] != "bootstrap-first-administrator"
        or receipt["outcome"] != "bootstrapped"
        or receipt["operationId"] != request["operationId"]
        or receipt["installationId"] != request["expectedInstallationId"]
        or type(receipt["accessRevision"]) is not int
        or receipt["accessRevision"] != 1
        or data["currentSession"] != {"status": "admitted", "principalId": receipt["principalId"]}
    ):
        raise ValueError("The original claim/session result does not match.")
    UUID(str(receipt["principalId"]))
    return receipt


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate fixture fields so the independently observed result has one meaning."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate fixture response field.")
        result[key] = value
    return result


def _object(value: object, keys: set[str]) -> dict[str, object]:
    """Require the exact fixture response fields before trusting its proof observations."""
    if not isinstance(value, dict) or set(cast("dict[str, object]", value)) != keys:
        raise ValueError("Unexpected fixture response shape.")
    return cast("dict[str, object]", value)


def validate_proof_result(
    raw: bytes, request: dict[str, object], principal_id: UUID
) -> dict[str, object]:
    """Require the exact original committed receipt and independent cleanup facts."""
    if len(raw) > 65_536:
        raise ValueError("The fixture response exceeded its bound.")
    value = _object(json.loads(raw, object_pairs_hook=_unique), {"schemaVersion", "result"})
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise ValueError("Unsupported fixture response version.")
    result = _object(value["result"], {"maintenance", "credentialCleanup"})
    maintenance = _object(result["maintenance"], {"effect", "processCleanup", "failure"})
    if (
        result["credentialCleanup"] != "confirmed"
        or maintenance["processCleanup"] != "confirmed"
        or maintenance["failure"] is not None
    ):
        raise ValueError("The fixture cleanup was not confirmed.")
    effect = _object(maintenance["effect"], {"status", "receipt"})
    if effect["status"] != "committed":
        raise ValueError("No committed fixture receipt.")
    receipt = _object(
        effect["receipt"],
        {
            "schemaVersion",
            "mode",
            "operationId",
            "installationId",
            "principalId",
            "accessRevision",
            "outcome",
            "responsibility",
        },
    )
    revision = request["expectedAccessRevision"]
    if type(revision) is not int or type(receipt["accessRevision"]) is not int:
        raise ValueError("Invalid fixture revision.")
    expected = {
        "schemaVersion": 1,
        "mode": request["mode"],
        "operationId": request["operationId"],
        "installationId": request["expectedInstallationId"],
        "principalId": str(principal_id),
        "accessRevision": revision + 1,
        "outcome": "repaired",
        "responsibility": request["responsibility"],
    }
    if type(receipt["schemaVersion"]) is not int or receipt != expected:
        raise ValueError("The receipt did not match the original fixture request.")
    return receipt


def validate_denied_result(raw: bytes) -> None:
    """Recognize only the unchanged production denial result, never a generic failure."""
    if len(raw) > 65_536:
        raise ValueError("The denied result exceeded its bound.")
    value = _object(json.loads(raw, object_pairs_hook=_unique), {"schemaVersion", "error"})
    error = _object(value["error"], {"kind", "resourceCleanup", "credentialCleanup"})
    if (
        type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or error
        != {
            "kind": "denied",
            "resourceCleanup": "not-needed",
            "credentialCleanup": "not-needed",
        }
    ):
        raise ValueError("The production denial was not confirmed.")


def settings() -> ApplicationSettings:
    from inframeld_backend.bootstrap.application_settings import ApplicationSettings

    configured = ApplicationSettings.model_validate({})
    if (configured.database.host, configured.database.name) != (
        "postgres",
        "account_ui_test",
    ):
        raise RuntimeError("Account qualification requires its private disposable database.")
    return configured


async def seed(configured: ApplicationSettings, subject: UUID) -> tuple[UUID, UUID, UUID] | None:
    from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
        VerifiedHumanIdentityDTO,
    )
    from inframeld_backend.access.domain.value_objects.identity_authority import (
        IdentityAuthority,
    )
    from inframeld_backend.access.domain.value_objects.identity_subject import (
        IdentitySubject,
    )
    from inframeld_backend.shared.infrastructure.resources.database import Database

    database = Database(configured.database)
    await database.startup()
    try:
        if os.getenv("INFRAMELD_ACCOUNT_PROOF_MODE") == "1":
            from tests.support.project_metadata_scenarios import (
                seed_metadata_repair_recipient,
            )

            identity = VerifiedHumanIdentityDTO(
                IdentityAuthority("kratos:account-ui-test"),
                IdentitySubject(str(subject)),
            )
            recipient, binding = await seed_metadata_repair_recipient(database, identity)
            if (
                configured.hydra is None
                or configured.hydra.issuer.value != "https://hydra.account.test:8443/"
                or configured.hydra.api_audience.value != "https://inframeld.account.test:8443"
            ):
                raise RuntimeError("The private proof profile does not match its trusted setup.")
            return (
                binding.installation_id.value,
                recipient.principal_id.value,
                recipient.project_id.value,
            )
        from tests.support.first_administrator_bootstrap_scenarios import (
            bootstrap_scenario,
            bootstrap_service,
        )

        # Only fixture authority uses controlled proof. Browser mutations authenticate normally.
        scenario = await bootstrap_scenario(
            database,
            identity=VerifiedHumanIdentityDTO(
                IdentityAuthority("kratos:account-ui-test"),
                IdentitySubject(str(subject)),
            ),
            operation="account-fixture-initial-administrator",
        )
        async with database.session() as session:
            result = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        descriptor = os.open(
            "/run/account-fixture/issuer.json",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w") as destination:
            json.dump(
                {
                    "installationId": str(result.installation_id.value),
                    "organizationId": str(result.organization_id.value),
                    "principalId": str(result.recipient_id.value),
                },
                destination,
            )
    finally:
        await database.shutdown()


def prepare_proof_inputs(identifiers: tuple[UUID, UUID, UUID], subject: UUID) -> None:
    """Keep synchronous private file preparation outside database/resource awaits."""
    installation_id, principal_id, project_id = identifiers
    names = (
        "PYTHONPATH",
        "INFRAMELD_ENVIRONMENT",
        "INFRAMELD_LOG_LEVEL",
        "INFRAMELD_DATABASE__HOST",
        "INFRAMELD_DATABASE__NAME",
        "INFRAMELD_DATABASE__USER",
        "INFRAMELD_DATABASE__PASSWORD",
        "INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE",
        "INFRAMELD_KRATOS__PUBLIC_URL",
        "INFRAMELD_KRATOS__ADMIN_URL",
        "INFRAMELD_KRATOS__AUTHORITY",
        "INFRAMELD_HYDRA__ADMIN_URL",
        "INFRAMELD_HYDRA__PUBLIC_URL",
        "INFRAMELD_HYDRA__ISSUER",
        "INFRAMELD_HYDRA__API_AUDIENCE",
    )
    certificate = Path("/run/account-trust/ca.pem").read_text()
    environment = {name: os.environ[name] for name in names}
    for name, operation in (
        ("recipient-proof-denied", "native-recipient-proof-denied"),
        ("recipient-proof", "native-recipient-proof"),
    ):
        write_proof_inputs(
            Path("/run/account-secrets") / name,
            installation_id=installation_id,
            identity_id=subject,
            principal_id=principal_id,
            project_id=project_id,
            certificate_authority=certificate,
            environment=environment,
            operation_id=operation,
        )


async def verify_proof_result(
    configured: ApplicationSettings,
    request: dict[str, object],
    principal_id: UUID,
    receipt: dict[str, object] | None,
) -> None:
    """Check the returned proof against independent committed database facts."""
    from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
    from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
        AccessAuditEventRow,
    )
    from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
        HostMaintenanceReceiptRow,
    )
    from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
        ProjectActionGrantRow,
    )
    from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
        ProjectMetadataRepairReceiptRow,
    )
    from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
    from inframeld_backend.shared.infrastructure.resources.database import Database
    from sqlalchemy import select

    responsibility = cast("dict[str, object]", request["responsibility"])
    target = cast("dict[str, object]", responsibility["target"])
    project_id = UUID(str(target["projectId"]))
    installation_id = UUID(str(request["expectedInstallationId"]))
    operation_id = str(request["operationId"])
    database = Database(configured.database)
    await database.startup()
    try:
        async with database.session() as session:
            project = await session.get(ProjectRow, project_id)
            original = await session.get(HostMaintenanceReceiptRow, (installation_id, operation_id))
            repaired = await session.get(
                ProjectMetadataRepairReceiptRow, (installation_id, operation_id)
            )
            grants = (
                await session.scalars(
                    select(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == project_id,
                        ProjectActionGrantRow.action == "edit-project-metadata",
                    )
                )
            ).all()
            audits = (
                await session.scalars(
                    select(AccessAuditEventRow).where(
                        AccessAuditEventRow.project_id == project_id,
                    )
                )
            ).all()
            if receipt is None:
                project_receipts = (
                    await session.scalars(
                        select(ProjectMetadataRepairReceiptRow).where(
                            ProjectMetadataRepairReceiptRow.project_id == project_id
                        )
                    )
                ).all()
                if (
                    project is None
                    or original is not None
                    or repaired is not None
                    or project_receipts
                    or grants
                    or audits
                ):
                    raise RuntimeError("A denied attempt created maintenance effects.")
                if (
                    project.access_revision != 0
                    or project.metadata_revision != 0
                    or project.name != "Legacy Support"
                    or project.resource_name is not None
                ):
                    raise RuntimeError("A denied attempt changed the reviewed Project.")
                return
            if (
                project is None
                or original is None
                or repaired is None
                or len(grants) != 1
                or len(audits) != 1
            ):
                raise RuntimeError("The committed proof records are incomplete.")
            grant, audit = grants[0], audits[0]
            if (
                project.access_revision != receipt["accessRevision"]
                or project.metadata_revision != 0
                or project.name != "Legacy Support"
                or project.resource_name is not None
                or original.mode != request["mode"]
                or original.outcome != "repaired"
                or original.operator_label != request["operatorLabel"]
                or original.reason != request["reason"]
                or original.subject != request["expectedIdentityId"]
                or original.authority != "kratos:account-ui-test"
                or repaired.recipient_id != principal_id
                or repaired.project_id != project_id
                or repaired.expected_identity_id != UUID(str(request["expectedIdentityId"]))
                or repaired.before_revision != request["expectedAccessRevision"]
                or repaired.after_revision != receipt["accessRevision"]
                or grant.recipient_principal_id != principal_id
                or grant.recipient_kind != PrincipalKind.HUMAN
                or not grant.can_grant
                or audit.correlation_id != operation_id
                or audit.event_type != "project_metadata_authority_repaired"
                or audit.affected_principal_id != principal_id
                or audit.before_values != {"access_revision": 0}
                or audit.after_values != {"access_revision": 1, "can_grant": True}
            ):
                raise RuntimeError(
                    "The committed proof records disagree with the original operation."
                )
    finally:
        await database.shutdown()
    print('{"phase":"recipient-proof","status":"passed"}')


def prepare_navigation(configured: ApplicationSettings) -> None:
    """Read official registration for browser decision navigation without exchange."""
    from ory_hydra_client import ApiClient, Configuration, OAuth2Api

    hydra = configured.hydra
    if hydra is None:
        raise RuntimeError("The fixture requires its official OAuth registration.")
    sdk = ApiClient(Configuration(host=str(hydra.admin_url).rstrip("/"), retries=0, debug=False))
    try:
        registration = OAuth2Api(sdk).get_o_auth2_client("inframeld-cli", _request_timeout=5.0)
        redirects = registration.redirect_uris
        if registration.client_id != "inframeld-cli" or redirects is None or len(redirects) != 1:
            raise RuntimeError("The official registration is not available.")
        body = {
            "clientId": registration.client_id,
            "redirectUri": redirects[0],
            "authorizationEndpoint": f"{hydra.issuer.value.rstrip('/')}/oauth2/auth",
            "issuer": hydra.issuer.value,
            "audience": hydra.api_audience.value,
        }
        descriptor = os.open(
            "/run/account-fixture/oauth-navigation.json",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w") as destination:
            json.dump(body, destination)
    finally:
        sdk.rest_client.pool_manager.clear()


def read_account_results() -> tuple[list[dict[str, object]], UUID]:
    """Bound the fixed private observations before asynchronous verification."""
    with Path("/run/account-proof/account-results.jsonl").open("rb") as source:
        raw = source.read(65_537)
    if len(raw) > 65_536:
        raise ValueError("The fixed account observations exceeded their bound.")
    observations: list[dict[str, object]] = []
    for line in raw.splitlines():
        parsed: object = json.loads(line, object_pairs_hook=_unique)
        if not isinstance(parsed, dict):
            raise ValueError("Each account observation must be an object.")
        value = cast("dict[str, object]", parsed)
        if value.get("kind") == "invitation":
            fields = {
                "kind",
                "identityId",
                "invitationId",
                "organizationId",
                "principalId",
                "operationId",
                "requestKey",
                "organizationAccessRevision",
                "projectAccessRevisions",
                "idempotencyExpiresAt",
            }
            if "projectId" in value:
                fields.update({"projectId", "accessGroupId"})
        elif value.get("kind") == "unused-invitation":
            fields = {"kind", "invitationId"}
        elif value.get("kind") == "recovery":
            fields = {"kind", "identityId", "principalId", "interruptedSettingsFlowId"}
        else:
            raise ValueError("Unknown account observation.")
        observations.append(_object(value, fields))
    if len(observations) != 5 or sorted(str(value["kind"]) for value in observations) != [
        "invitation",
        "invitation",
        "recovery",
        "unused-invitation",
        "unused-invitation",
    ]:
        raise ValueError("The five account outcomes did not complete.")
    issuer = _object(
        json.loads(Path("/run/account-fixture/issuer.json").read_bytes()),
        {"installationId", "organizationId", "principalId"},
    )
    return observations, UUID(str(issuer["principalId"]))


async def verify_account_results(
    configured: ApplicationSettings,
    observations: list[dict[str, object]],
    issuer_id: UUID,
) -> None:
    """Check durable effects independently of the browser's UI and original replay."""
    from datetime import datetime, timedelta

    from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
        IdentityRecoveryEvidenceType,
    )
    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
        AccessAuditEventRow,
    )
    from inframeld_backend.access.infrastructure.rows.group_membership_row import (
        GroupMembershipRow,
    )
    from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
        HumanIdentityLinkRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
        IdentityRecoveryAdmissionRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
        IdentityRecoveryCleanupJobRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
        IdentityRecoveryCleanupProofRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
        IdentityRecoveryEvidenceReceiptRow,
    )
    from inframeld_backend.access.infrastructure.rows.invitation_activation_operation_row import (
        InvitationActivationOperationRow,
    )
    from inframeld_backend.access.infrastructure.rows.invitation_row import (
        InvitationRow,
    )
    from inframeld_backend.access.infrastructure.rows.project_membership_row import (
        ProjectMembershipRow,
    )
    from inframeld_backend.shared.application.enums.operation_reservation_state import (
        OperationReservationState,
    )
    from inframeld_backend.shared.infrastructure.resources.database import Database
    from sqlalchemy import func, select

    database = Database(configured.database)
    await database.startup()
    try:
        async with database.session() as session:
            for observation in observations:
                if observation["kind"] == "recovery":
                    subject = str(observation["identityId"])
                    admissions = (
                        await session.scalars(
                            select(IdentityRecoveryAdmissionRow).where(
                                IdentityRecoveryAdmissionRow.authority == "kratos:account-ui-test",
                                IdentityRecoveryAdmissionRow.subject == subject,
                            )
                        )
                    ).all()
                    assert len(admissions) == 1
                    admission = admissions[0]
                    assert admission.released_at is not None
                    assert admission.kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
                    assert admission.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
                    job = await session.get(IdentityRecoveryCleanupJobRow, admission.operation_id)
                    assert job is not None
                    assert job.cli_grants_state is IdentityRecoveryCleanupState.CONFIRMED
                    assert job.remembered_logins_state is IdentityRecoveryCleanupState.CONFIRMED
                    proofs = (
                        await session.scalars(
                            select(IdentityRecoveryCleanupProofRow).where(
                                IdentityRecoveryCleanupProofRow.source_operation_id
                                == admission.operation_id,
                            )
                        )
                    ).all()
                    assert len(proofs) == 1 and proofs[0].propagation_complete
                    evidence = (
                        await session.scalars(
                            select(IdentityRecoveryEvidenceReceiptRow).where(
                                IdentityRecoveryEvidenceReceiptRow.operation_id
                                == admission.operation_id,
                            )
                        )
                    ).all()
                    saved = [
                        row
                        for row in evidence
                        if row.event_type is IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
                    ]
                    assert len(saved) == 1
                    assert str(saved[0].native_flow_id) != observation["interruptedSettingsFlowId"]
                    link = await session.get(
                        HumanIdentityLinkRow, ("kratos:account-ui-test", subject)
                    )
                    assert link is not None and str(link.principal_id) == observation["principalId"]
                    continue

                invitation_id = UUID(str(observation["invitationId"]))
                invitation = await session.get(InvitationRow, invitation_id)
                assert invitation is not None
                originals = (
                    await session.scalars(
                        select(InvitationActivationOperationRow).where(
                            InvitationActivationOperationRow.invitation_id == invitation_id,
                        )
                    )
                ).all()
                if observation["kind"] == "unused-invitation":
                    assert invitation.consumed_at is None
                    assert invitation.consumed_by_principal_id is None
                    assert not originals
                    continue

                principal_id = UUID(str(observation["principalId"]))
                assert invitation.consumed_at is not None
                assert invitation.consumed_by_principal_id == principal_id
                assert str(invitation.organization_id) == observation["organizationId"]
                assert len(originals) == 1
                original = originals[0]
                assert original.state is OperationReservationState.REPLAYABLE
                assert original.operation_id == observation["operationId"]
                assert original.request_key == observation["requestKey"]
                assert original.subject == observation["identityId"]
                assert original.principal_id == principal_id
                assert (
                    original.organization_access_revision
                    == observation["organizationAccessRevision"]
                )
                assert original.project_access_revisions == observation["projectAccessRevisions"]
                assert original.expires_at is not None
                assert original.expires_at == datetime.fromisoformat(
                    str(observation["idempotencyExpiresAt"])
                )
                assert original.completed_at is not None
                assert original.expires_at - original.completed_at == timedelta(hours=24)
                audits = await session.scalar(
                    select(func.count())
                    .select_from(AccessAuditEventRow)
                    .where(
                        AccessAuditEventRow.target_id == invitation_id,
                        AccessAuditEventRow.event_type == "invitation_activated",
                        AccessAuditEventRow.actor_principal_id == principal_id,
                        AccessAuditEventRow.correlation_id == original.operation_id,
                    )
                )
                assert audits == 1
                link = await session.get(
                    HumanIdentityLinkRow, ("kratos:account-ui-test", original.subject)
                )
                assert link is not None and link.principal_id == principal_id
                if "projectId" in observation:
                    project_id = UUID(str(observation["projectId"]))
                    membership = await session.get(ProjectMembershipRow, (project_id, principal_id))
                    assert membership is not None
                    assert membership.assigned_by_principal_id == issuer_id
                    group = await session.get(
                        GroupMembershipRow,
                        (
                            project_id,
                            UUID(str(observation["accessGroupId"])),
                            principal_id,
                        ),
                    )
                    assert group is not None
                    assert group.assigned_by_principal_id == issuer_id
    finally:
        await database.shutdown()


def validate_bootstrap_identity_links(
    links: list[tuple[str, str, UUID]], expected: tuple[str, str, UUID] | None
) -> None:
    """Require the complete native identity-link set, including absence of aliases."""
    if links != ([] if expected is None else [expected]):
        raise ValueError("The complete bootstrap identity-link set disagrees.")


async def bootstrap_database(
    configured: ApplicationSettings,
    stage: str,
    receipt: dict[str, object] | None = None,
) -> UUID:
    """Independently inspect only this disposable installation and its exact claim."""
    from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
        AccessAuditEventRow,
    )
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
    from inframeld_backend.access.infrastructure.rows.organization_row import (
        OrganizationRow,
    )
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
    from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
    from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
        PostgresInstallationIdentityReader,
    )
    from inframeld_backend.shared.infrastructure.resources.database import Database
    from sqlalchemy import func, select

    database = Database(configured.database)
    await database.startup()
    try:
        installation = (await PostgresInstallationIdentityReader(database).read()).value
        async with database.session() as session:
            links = (await session.scalars(select(HumanIdentityLinkRow))).all()
            principals = (await session.scalars(select(PrincipalRow))).all()
            organizations = (await session.scalars(select(OrganizationRow))).all()
            grants = (await session.scalars(select(OrganizationActionGrantRow))).all()
            claims = (await session.scalars(select(FirstAdministratorBootstrapReceiptRow))).all()
            originals = (await session.scalars(select(HostMaintenanceReceiptRow))).all()
            audits = (await session.scalars(select(AccessAuditEventRow))).all()
            projects = await session.scalar(select(func.count()).select_from(ProjectRow))
            if projects != 0:
                raise RuntimeError("Bootstrap created a Project or starter scope.")
            if stage == "pristine":
                validate_bootstrap_identity_links(
                    [(link.authority, link.subject, link.principal_id) for link in links], None
                )
                if principals or organizations or grants or claims or originals or audits:
                    raise RuntimeError("The installation is not pristine.")
                return installation
            if (
                len(principals) != 1
                or len(organizations) != 1
                or len(claims) != 1
                or len(originals) != 1
                or len(audits) != 1
            ):
                raise RuntimeError("The exact atomic bootstrap effects are missing.")
            principal, organization, claim, original, audit = (
                principals[0],
                organizations[0],
                claims[0],
                originals[0],
                audits[0],
            )
            subject = UUID(
                json.loads(
                    await asyncio.to_thread(Path("/run/account-fixture/human.json").read_bytes)
                )["subject"]
            )
            validate_bootstrap_identity_links(
                [(link.authority, link.subject, link.principal_id) for link in links],
                ("kratos:account-ui-test", str(subject), principal.id),
            )
            link = links[0]
            if (
                principal.kind != PrincipalKind.HUMAN
                or principal.status != PrincipalStatus.ACTIVE
                or principal.organization_id != organization.id
                or organization.access_revision != 1
                or claim.installation_id != installation
                or claim.expected_identity_id != subject
                or claim.recipient_id != principal.id
                or claim.organization_id != organization.id
                or claim.before_revision != 0
                or claim.after_revision != 1
                or original.operator_request_id != "native-bootstrap-original"
                or original.subject != str(subject)
                or original.authority != "kratos:account-ui-test"
                or original.outcome != "bootstrapped"
                or audit.event_type != "first_administrator_bootstrapped"
                or audit.affected_principal_id != principal.id
                or link.organization_id != organization.id
                or link.principal_kind != PrincipalKind.HUMAN
            ):
                raise RuntimeError("Bootstrap identity/revision/audit binding disagrees.")
            if receipt is not None and (
                receipt["principalId"] != str(principal.id)
                or receipt["installationId"] != str(installation)
                or receipt["accessRevision"] != claim.after_revision
            ):
                raise RuntimeError("The original receipt disagrees with durable state.")
            expected = {
                "admit-users",
                "suspend-users",
                "restore-users",
                "create-projects",
            }
            if stage in {"first", "remove"}:
                if (
                    len(grants) != 4
                    or {grant.action for grant in grants} != expected
                    or any(
                        grant.organization_id != organization.id
                        or grant.recipient_principal_id != principal.id
                        or grant.recipient_kind != PrincipalKind.HUMAN
                        or not grant.can_grant
                        for grant in grants
                    )
                ):
                    raise RuntimeError("The four exact Organization assignments disagree.")
                if stage == "remove":
                    for grant in grants:
                        await session.delete(grant)
                    await session.commit()
            elif grants:
                raise RuntimeError("Original replay or rejection recreated removed grants.")
            return installation
    finally:
        await database.shutdown()


def prepare_bootstrap_fixture(configured: ApplicationSettings) -> None:
    """Use migrated singleton and provider fixtures without claiming business authority."""
    installation = asyncio.run(bootstrap_database(configured, "pristine"))
    names = (
        "PYTHONPATH",
        "INFRAMELD_ENVIRONMENT",
        "INFRAMELD_LOG_LEVEL",
        "INFRAMELD_DATABASE__HOST",
        "INFRAMELD_DATABASE__NAME",
        "INFRAMELD_DATABASE__USER",
        "INFRAMELD_DATABASE__PASSWORD",
        "INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE",
        "INFRAMELD_KRATOS__PUBLIC_URL",
        "INFRAMELD_KRATOS__ADMIN_URL",
        "INFRAMELD_KRATOS__AUTHORITY",
        "INFRAMELD_HYDRA__ADMIN_URL",
        "INFRAMELD_HYDRA__PUBLIC_URL",
        "INFRAMELD_HYDRA__ISSUER",
        "INFRAMELD_HYDRA__API_AUDIENCE",
    )
    environment = {name: os.environ[name] for name in names}
    for folder, identity_file, operation in [
        ("first", "human", "native-bootstrap-original"),
        ("competing", "switch", "native-bootstrap-competing"),
        ("reused", "switch", "native-bootstrap-original"),
    ]:
        identity = UUID(
            json.loads(Path(f"/run/account-fixture/{identity_file}.json").read_bytes())["subject"]
        )
        write_bootstrap_inputs(
            Path(f"/run/account-secrets/bootstrap-{folder}"),
            installation_id=installation,
            identity_id=identity,
            certificate_authority=Path("/run/account-trust/ca.pem").read_text(),
            environment=environment,
            operation_id=operation,
        )


def main() -> None:
    configured = settings()
    if sys.argv[1:] == ["migrate"]:
        from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
            run_migrations,
        )

        run_migrations(configured.database)
    elif sys.argv[1:] == ["seed"]:
        subject = UUID(json.loads(Path("/run/account-fixture/human.json").read_text())["subject"])
        if os.getenv("INFRAMELD_ACCOUNT_PROOF_MODE") == "bootstrap":
            prepare_bootstrap_fixture(configured)
        else:
            identifiers = asyncio.run(seed(configured, subject))
            if identifiers is not None:
                prepare_proof_inputs(identifiers, subject)
        prepare_navigation(configured)
    elif sys.argv[1:] == ["serve"]:
        import uvicorn

        uvicorn.run(
            "inframeld_backend.main:app",
            host="0.0.0.0",
            port=8000,
            proxy_headers=False,
            access_log=False,
            log_level="warning",
        )
    elif (
        len(sys.argv) == 2
        and sys.argv[1].startswith("bootstrap-")
        and os.getenv("INFRAMELD_ACCOUNT_PROOF_MODE") == "bootstrap"
    ):
        stage = sys.argv[1].removeprefix("bootstrap-")
        if stage not in {
            "pristine",
            "first",
            "remove",
            "replay",
            "competing",
            "reused",
        }:
            raise ValueError("Unknown bootstrap fixture stage.")
        receipt = None
        if stage not in {"pristine", "remove"}:
            folder = "first" if stage in {"first", "replay"} else stage
            request = cast(
                "dict[str, object]",
                json.loads(
                    Path(f"/run/account-secrets/bootstrap-{folder}/request.json").read_bytes()
                ),
            )
            code = {
                "competing": "already_bootstrapped",
                "reused": "idempotency_key_reused",
            }.get(stage)
            receipt = validate_bootstrap_result(sys.stdin.buffer.read(65_537), request, code)
        asyncio.run(bootstrap_database(configured, stage, receipt))
        print(f"Independent bootstrap {stage} effects verified.")
    elif (
        sys.argv[1:] == ["verify-account-result"]
        and os.getenv("INFRAMELD_ACCOUNT_PROOF_MODE") != "1"
    ):
        observations, issuer_id = read_account_results()
        asyncio.run(verify_account_results(configured, observations, issuer_id))
        print("Independent native account effects and original outcomes verified.")
    elif (
        sys.argv[1:] in (["verify-proof-result"], ["verify-denied-result"])
        and os.getenv("INFRAMELD_ACCOUNT_PROOF_MODE") == "1"
    ):
        denied = sys.argv[1] == "verify-denied-result"
        private = Path(
            "/run/account-secrets/recipient-proof-denied"
            if denied
            else "/run/account-secrets/recipient-proof"
        )
        request = cast(
            "dict[str, object]",
            json.loads((private / "request.json").read_bytes(), object_pairs_hook=_unique),
        )
        expected = json.loads((private / "expected.json").read_bytes(), object_pairs_hook=_unique)
        principal_id = UUID(expected["principalId"])
        raw = sys.stdin.buffer.read(65_537)
        if denied:
            validate_denied_result(raw)
            receipt = None
        else:
            receipt = validate_proof_result(raw, request, principal_id)
        asyncio.run(verify_proof_result(configured, request, principal_id, receipt))
    else:
        raise RuntimeError("Unknown account fixture command.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("The private account backend fixture failed.", file=sys.stderr)
        raise SystemExit(1) from None
