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


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate fixture response field.")
        result[key] = value
    return result


def _object(value: object, keys: set[str]) -> dict[str, object]:
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
    from tests.support.access_scenarios import MockAccessScenarios

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
        async with database.session() as session, session.begin():
            await MockAccessScenarios.seed_linked_human(
                session,
                VerifiedHumanIdentityDTO(
                    IdentityAuthority("kratos:account-ui-test"),
                    IdentitySubject(str(subject)),
                ),
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


def main() -> None:
    configured = settings()
    if sys.argv[1:] == ["migrate"]:
        from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
            run_migrations,
        )

        run_migrations(configured.database)
    elif sys.argv[1:] == ["seed"]:
        subject = UUID(json.loads(Path("/run/account-fixture/human.json").read_text())["subject"])
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
            access_log=False,
            log_level="warning",
        )
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
