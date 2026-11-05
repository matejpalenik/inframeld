"""Seed real Project/job authority and assemble PostgreSQL spending scenarios.

Provider prices and observations here are controlled accounting inputs. They
establish no outbound model, provider mapping or invoice qualification.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import ARRAY, Integer, String, column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.project_budget_authorization_service import (
    ProjectBudgetAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_budget_facts_reader import (
    PostgresProjectBudgetFactsReader,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.bootstrap.spending_accounting_composition import (
    open_project_spending_policy,
    open_spending_accounting,
)
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.protocols.spending_ledger_writer import (
    SpendingLedgerWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.project_spending_policy_fingerprint_service import (
    ProjectSpendingPolicyFingerprintService,
)
from inframeld_backend.shared.application.services.project_spending_policy_service import (
    ProjectSpendingPolicyService,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_spending_ledger_writer import (
    PostgresSpendingLedgerWriter,
)
from tests.support.project_creation_scenarios import create_project, seed_project_creator

_DEFAULT_TEST_LIMIT = UsdAmount(Decimal("1"))


@dataclass(frozen=True, slots=True)
class SpendingScenarioDTO:
    access: AccessContextDTO
    organization_id: OrganizationId
    project_id: ProjectId
    attempt: JobAttemptContextDTO


def money(value: str) -> UsdAmount:
    return UsdAmount(Decimal(value))


def fingerprints() -> ProjectSpendingPolicyFingerprintService:
    return ProjectSpendingPolicyFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )


async def seed_spending_scenario(
    database: Database,
    *,
    monthly_limit: UsdAmount | None = _DEFAULT_TEST_LIMIT,
    create_account: bool = True,
) -> SpendingScenarioDTO:
    creator = await seed_project_creator(database)
    project = await create_project(database, creator)
    access = AccessContextDTO(creator.access.actor_principal_id, creator.binding)
    authority = AdmittedWorkAuthorityDTO(
        access.actor_principal_id,
        PrincipalKind.HUMAN,
        creator.binding.installation_id,
        creator.organization_id,
        project.project.project_id,
        ActionId("create-sources"),
        creator.binding,
    )
    if create_account:
        async with database.session() as session, session.begin():
            session.add(
                ProjectSpendingPolicyRow(
                    project_id=authority.project_id.value,
                    organization_id=authority.organization_id.value,
                    revision=0,
                    monthly_limit=None if monthly_limit is None else monthly_limit.value,
                )
            )
    attempt = await _admit_attempt(database, access, authority, "spending-job")
    return SpendingScenarioDTO(access, creator.organization_id, project.project.project_id, attempt)


async def _admit_attempt(
    database: Database, access: AccessContextDTO, authority: AdmittedWorkAuthorityDTO, key: str
) -> JobAttemptContextDTO:
    async with database.session() as session, session.begin():
        admitted = await JobAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            PostgresJobStore(session),
            PostgresJobAdmissionAuditWriter(session),
            supported_payloads=(("test.spending", 1),),
        ).admit(
            access=access,
            authority=authority,
            context=IdempotencyContextDTO(
                "POST", "/v1/projects/{project_id}/sources", IdempotencyKey(key)
            ),
            fingerprint=RequestFingerprint(b"S" * 32),
            request_id=RequestId(uuid4()),
            payload=JobPayload("test.spending", 1, b""),
        )
    async with database.session() as session:
        attempt = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("test.spending", 1),),
            worker_id=uuid4(),
        ).claim_next()
    assert attempt is not None and isinstance(attempt.binding, ProductJobBindingDTO)
    assert attempt.job_id == admitted.job_id
    return attempt


async def finish_fixture_job(
    database: Database, scenario: SpendingScenarioDTO, *, pending_effect: str | None = None
) -> None:
    """End the actual current attempt before claiming the next globally serial job."""
    async with database.session() as session, session.begin():
        if pending_effect is not None:
            await PostgresJobStore(session).begin_effect(scenario.attempt, pending_effect)
        await PostgresJobStore(session).finish(
            scenario.attempt, status=JobStatus.FAILED, reason="controlled_fixture_transition"
        )
    if pending_effect is not None:
        original = scenario.attempt.binding
        assert isinstance(original, ProductJobBindingDTO)
        async with database.session() as session:
            stopped = await PostgresJobStore(session).find(original.operation_id)
            assert stopped is not None and stopped.status is JobStatus.RECOVERY_REQUIRED
            assert stopped.fence is None and stopped.pending_effect == pending_effect
            replay = await session.get(IdempotencyReservationRow, original.operation_id.value)
            assert replay is not None and replay.expires_at is None


async def seed_human_work(
    database: Database, original: SpendingScenarioDTO, key: str
) -> SpendingScenarioDTO:
    """Admit a distinct human job with current OAuth facts and explicit create-sources authority.

    The preceding job must already have stopped. Identity verification is
    controlled fixture input, while admission, current facts and ownership use
    the actual application and PostgreSQL implementations.
    """
    access = await _seed_project_human(
        database, original, ActionId("create-sources"), "Accounting fixture"
    )
    binding = access.authentication_evidence
    assert isinstance(binding, HumanOAuthCredentialBindingDTO)
    authority = AdmittedWorkAuthorityDTO(
        access.actor_principal_id,
        PrincipalKind.HUMAN,
        binding.installation_id,
        original.organization_id,
        original.project_id,
        ActionId("create-sources"),
        binding,
    )
    attempt = await _admit_attempt(database, access, authority, key)
    return SpendingScenarioDTO(access, original.organization_id, original.project_id, attempt)


async def seed_other_budget_human(
    database: Database, scenario: SpendingScenarioDTO
) -> AccessContextDTO:
    """Give a second human explicit budget authority with a distinct identity lock."""
    return await _seed_project_human(
        database, scenario, ActionId("manage-budget"), "Budget fixture"
    )


async def _seed_project_human(
    database: Database, scenario: SpendingScenarioDTO, action: ActionId, display_name: str
) -> AccessContextDTO:
    principal = PrincipalId(uuid4())
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    original = scenario.attempt.binding
    assert isinstance(original, ProductJobBindingDTO)
    installation = original.authority.installation_id
    async with database.session() as session, session.begin():
        session.add(
            PrincipalRow(
                id=principal.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name=display_name,
            )
        )
        await session.flush()
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=scenario.organization_id.value,
                principal_id=principal.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        session.add(
            HumanCredentialVersionRow(
                installation_id=installation.value,
                authority=identity.authority.value,
                subject=identity.subject.value,
                version=1,
            )
        )
        session.add(
            ProjectMembershipRow(
                project_id=scenario.project_id.value,
                principal_id=principal.value,
                organization_id=scenario.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
                application_principal_id=None,
            )
        )
        await session.flush()
        session.add(
            ProjectActionGrantRow(
                project_id=scenario.project_id.value,
                recipient_principal_id=principal.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=action.value,
                can_grant=False,
            )
        )
    return AccessContextDTO(
        principal, HumanOAuthCredentialBindingDTO(identity, installation, HumanCredentialVersion(1))
    )


def call_context(scenario: SpendingScenarioDTO, number: int = 1) -> SpendingCallContextDTO:
    binding = scenario.attempt.binding
    assert isinstance(binding, ProductJobBindingDTO)
    return SpendingCallContextDTO(
        ModelCallId(uuid5(scenario.attempt.job_id.value, str(number))),
        binding.operation_id,
        binding.authority,
        scenario.attempt,
        RequestFingerprint(sha256(f"fixture-call-{number}".encode()).digest()),
    )


def price_basis(amount: str = "0.1", maximum: str = "1") -> CapturedSpendingBasisDTO:
    return CapturedSpendingBasisDTO(
        "controlled-basis",
        "accounting-fixture",
        "v1",
        datetime.now(UTC),
        (SpendingRateDTO("input", "unit", Decimal(amount)),),
        (SpendingUsageDTO("input", "unit", Decimal(maximum)),),
    )


def observation(
    call: SpendingCallContextDTO,
    *,
    number: int = 1,
    kind: Literal["usage", "charge", "not_sent", "not_billed", "uncertain"] = "charge",
    charge: str | None = "0.08",
) -> SpendingObservationDTO:
    return SpendingObservationDTO(
        uuid5(call.call_id.value, f"evidence-{number}"),
        call.call_id,
        kind,
        datetime.now(UTC),
        "controlled-call-bound-accounting-evidence",
        charge=None if charge is None else Decimal(charge),
    )


def accounting_service(
    session: AsyncSession, writer: SpendingLedgerWriter | None = None
) -> SpendingAccountingService:
    return SpendingAccountingService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        admitted_work_authorizer=AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        ),
        job_ownership=PostgresJobStore(session),
        spending_ledger_reader=PostgresSpendingLedgerReader(session),
        spending_ledger_writer=PostgresSpendingLedgerWriter(session) if writer is None else writer,
        budget_authorizer=ProjectBudgetAuthorizationService(
            PostgresProjectBudgetFactsReader(session)
        ),
    )


def policy_service(
    session: AsyncSession, writer: SpendingLedgerWriter | None = None
) -> ProjectSpendingPolicyService:
    return ProjectSpendingPolicyService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        project_budget_authorizer=ProjectBudgetAuthorizationService(
            PostgresProjectBudgetFactsReader(session)
        ),
        spending_ledger_reader=PostgresSpendingLedgerReader(session),
        spending_ledger_writer=PostgresSpendingLedgerWriter(session) if writer is None else writer,
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        spending_policy_fingerprint_service=fingerprints(),
    )


async def reserve(
    database: Database,
    call: SpendingCallContextDTO,
    *,
    basis: CapturedSpendingBasisDTO | None,
    operation_limit: UsdAmount | None = None,
) -> SpendingAccountingResultDTO:
    async with open_spending_accounting(database) as accountant:
        return await accountant.reserve(call=call, basis=basis, operation_limit=operation_limit)


async def change_limit(
    database: Database,
    scenario: SpendingScenarioDTO,
    limit: UsdAmount | None,
    *,
    revision: int = 0,
    key: str = "change-limit",
) -> ProjectSpendingPolicyResultDTO:
    async with open_project_spending_policy(database, fingerprints()) as policy:
        return await policy.change_limit(
            access=scenario.access,
            command=ChangeProjectSpendingPolicyCommand(scenario.project_id, revision, limit),
            context=IdempotencyContextDTO(
                "PATCH", "/internal/projects/{project_id}/spending-policy", IdempotencyKey(key)
            ),
        )


async def wait_for_database_lock[Result](
    database: Database, task: asyncio.Task[Result], *, minimum: int = 1
) -> None:
    """Observe actual lock contention in this temporary database before committing a holder."""
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(func.count())
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.cardinality(
                            func.pg_blocking_pids(pid, type_=ARRAY(Integer)), type_=Integer
                        )
                        > 0,
                    )
                )
            if blocked is not None and blocked >= minimum:
                return
            await asyncio.sleep(0.01)
    task.result()
    pytest.fail("Budget operation bypassed the required current-authority coordination.")
