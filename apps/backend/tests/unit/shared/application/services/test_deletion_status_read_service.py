"""Qualify retained-read decisions using controlled owner observations, not deletion effects."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast, override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_request_dto import (
    DeletionStatusAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.deletion_status_authorizer import (
    DeletionStatusAuthorizer,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_obligation_provenance_dto import (
    DeletionStatusObligationProvenanceDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
)
from inframeld_backend.shared.application.protocols.deletion_status_projection_reader import (
    DeletionStatusProjectionReader,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.services.deletion_status_read_service import (
    DeletionStatusReadService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

NOW = datetime(2030, 5, 10, tzinfo=UTC)
STARTED = NOW - timedelta(days=5)
ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
QUERY = GetDeletionStatusQuery(OperationId("original-deletion"))
AUTHORIZATION = DeletionStatusAuthorizationDTO(
    QUERY.operation_id,
    InstallationId(UUID(int=2)),
    OrganizationId(UUID(int=3)),
    ACCESS.actor_principal_id,
)
BINDING = DeletionStatusBindingDTO(
    operation_id=QUERY.operation_id,
    request_id=RequestId(UUID(int=4)),
    installation_id=AUTHORIZATION.installation_id,
    organization_id=AUTHORIZATION.organization_id,
    project_id=ProjectId(UUID(int=5)),
    initiator_principal_id=ACCESS.actor_principal_id,
    method=HttpMethod.DELETE,
    requested_route="/v1/original-project-deletion",
    key=IdempotencyKey("original-key"),
    fingerprint=RequestFingerprint(b"F" * 32),
    authority_family=OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
    action_id=ActionId("delete-project"),
    recorded_at=NOW - timedelta(days=10),
    retention_days=30,
    retention_policy_version="ADR-0117/PD-KNOWLEDGE-02:v1",
)
PROVENANCE = DeletionStatusObligationProvenanceDTO(
    obligation_id=UUID(int=6),
    operation_id=BINDING.operation_id,
    installation_id=BINDING.installation_id,
    organization_id=BINDING.organization_id,
    project_id=BINDING.project_id,
    initiator_principal_id=BINDING.initiator_principal_id,
    observed_at=NOW - timedelta(minutes=1),
    source_revision=1,
)
ACTIVE = DeletionStatusObservationDTO(
    binding=BINDING,
    observed_at=NOW,
    owner_revision=1,
    owner_observed_at=NOW - timedelta(minutes=1),
    job_status=JobStatus.RUNNING,
    admission_confirmed=True,
    access_blocked=True,
    unfinished_obligation=PROVENANCE,
)


def _settled() -> DeletionStatusObservationDTO:
    return replace(
        ACTIVE,
        owner_revision=2,
        owner_observed_at=STARTED,
        job_status=JobStatus.SUCCEEDED,
        application_shutdown_complete=True,
        physical_cleanup_complete=True,
        unfinished_obligation=None,
        retention_started_at=STARTED,
        expires_at=STARTED + timedelta(days=30),
    )


class MockDeletionAuthorizer(DeletionStatusAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = AUTHORIZATION
        self.failure: Exception | None = None

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: DeletionStatusAuthorizationRequestDTO
    ) -> DeletionStatusAuthorizationDTO:
        self.events.append("authorize")
        assert access == ACCESS
        assert request.operation_id == QUERY.operation_id
        if self.failure is not None:
            raise self.failure
        return self.result


class MockDeletionProjection(DeletionStatusProjectionReader):
    def __init__(self, events: list[str], observation: DeletionStatusObservationDTO | None) -> None:
        self.events = events
        self.observation = observation
        self.failure: Exception | None = None

    @override
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None:
        self.events.append("read")
        assert authorization == AUTHORIZATION
        if self.failure is not None:
            raise self.failure
        return self.observation


async def _lookup(
    observation: DeletionStatusObservationDTO | None,
) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
    events: list[str] = []
    return await DeletionStatusReadService(
        MockDeletionAuthorizer(events), MockDeletionProjection(events, observation)
    ).lookup(access=ACCESS, query=QUERY)


@pytest.mark.asyncio
@pytest.mark.parametrize("observation", [None, ACTIVE, _settled()])
async def test_denied_human_never_searches_retained_history(
    observation: DeletionStatusObservationDTO | None,
) -> None:
    events: list[str] = []
    authorizer = MockDeletionAuthorizer(events)
    authorizer.failure = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await DeletionStatusReadService(
            authorizer, MockDeletionProjection(events, observation)
        ).lookup(access=ACCESS, query=QUERY)
    assert events == ["authorize"]


@pytest.mark.asyncio
async def test_active_outcome_preserves_unknown_completion_without_private_binding_fields() -> None:
    result = await _lookup(ACTIVE)
    assert result == RetainedDeletionStatusDTO(
        operation_id=QUERY.operation_id,
        job_status=JobStatus.RUNNING,
        admission_confirmed=True,
        access_blocked=True,
        application_shutdown_complete=None,
        physical_cleanup_complete=None,
        expires_at=None,
    )


@pytest.mark.asyncio
async def test_successful_job_alone_does_not_prove_physical_completion() -> None:
    result = await _lookup(replace(ACTIVE, job_status=JobStatus.SUCCEEDED))
    assert isinstance(result, RetainedDeletionStatusDTO)
    assert result.physical_cleanup_complete is None
    assert result.expires_at is None


@pytest.mark.asyncio
async def test_settled_read_preserves_original_clock_and_does_not_extend_it_on_replay() -> None:
    observation = _settled()
    first = await _lookup(observation)
    second = await _lookup(replace(observation, observed_at=NOW + timedelta(days=1)))
    assert (
        first
        == second
        == RetainedDeletionStatusDTO(
            operation_id=QUERY.operation_id,
            job_status=JobStatus.SUCCEEDED,
            admission_confirmed=True,
            access_blocked=True,
            application_shutdown_complete=True,
            physical_cleanup_complete=True,
            expires_at=STARTED + timedelta(days=30),
        )
    )
    assert observation.retention_started_at == STARTED


@pytest.mark.asyncio
async def test_captured_maximum_is_used_even_when_a_later_installation_default_differs() -> None:
    observation = replace(
        _settled(),
        binding=replace(BINDING, retention_days=90),
        expires_at=STARTED + timedelta(days=90),
        observed_at=STARTED + timedelta(days=60),
    )
    result = await _lookup(observation)
    assert isinstance(result, RetainedDeletionStatusDTO)
    assert result.expires_at == STARTED + timedelta(days=90)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observation",
    [
        None,
        DeletionStatusObservationDTO(BINDING, NOW),
        replace(ACTIVE, binding=replace(BINDING, operation_id=OperationId("other"))),
        replace(ACTIVE, binding=replace(BINDING, initiator_principal_id=PrincipalId(UUID(int=99)))),
        replace(ACTIVE, binding=replace(BINDING, installation_id=InstallationId(UUID(int=99)))),
        replace(ACTIVE, binding=replace(BINDING, organization_id=OrganizationId(UUID(int=99)))),
        replace(ACTIVE, binding=replace(BINDING, authority_family=None)),
        replace(ACTIVE, binding=replace(BINDING, action_id=ActionId("create-sources"))),
    ],
)
async def test_absent_binding_only_and_nonmatching_history_are_uniformly_unresolved(
    observation: DeletionStatusObservationDTO | None,
) -> None:
    assert await _lookup(observation) == UnresolvedOperationDTO()


@pytest.mark.asyncio
@pytest.mark.parametrize("after_expiry", [timedelta(0), timedelta(microseconds=1)])
async def test_exact_retained_expiry_is_not_extended(after_expiry: timedelta) -> None:
    observation = _settled()
    assert observation.expires_at is not None
    result = await _lookup(replace(observation, observed_at=observation.expires_at + after_expiry))
    assert result == UnresolvedOperationDTO()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observation",
    [
        replace(ACTIVE, binding=replace(BINDING, retention_days=None)),
        replace(ACTIVE, binding=replace(BINDING, retention_days=0)),
        replace(ACTIVE, binding=replace(BINDING, retention_days=91)),
        replace(ACTIVE, binding=replace(BINDING, retention_days=True)),
        replace(ACTIVE, binding=replace(BINDING, retention_policy_version=None)),
        replace(ACTIVE, binding=replace(BINDING, retention_policy_version="unreviewed")),
        replace(ACTIVE, unfinished_obligation=None),
        replace(
            ACTIVE, unfinished_obligation=replace(PROVENANCE, operation_id=OperationId("other"))
        ),
        replace(
            ACTIVE,
            unfinished_obligation=replace(PROVENANCE, installation_id=InstallationId(UUID(int=99))),
        ),
        replace(
            ACTIVE,
            unfinished_obligation=replace(PROVENANCE, organization_id=OrganizationId(UUID(int=99))),
        ),
        replace(
            ACTIVE, unfinished_obligation=replace(PROVENANCE, project_id=ProjectId(UUID(int=99)))
        ),
        replace(
            ACTIVE,
            unfinished_obligation=replace(
                PROVENANCE, initiator_principal_id=PrincipalId(UUID(int=99))
            ),
        ),
        replace(ACTIVE, unfinished_obligation=replace(PROVENANCE, source_revision=0)),
        replace(ACTIVE, owner_revision=0),
        replace(ACTIVE, owner_revision=2**53),
        replace(ACTIVE, unfinished_obligation=replace(PROVENANCE, source_revision=2**53)),
        replace(ACTIVE, owner_observed_at=None),
        replace(ACTIVE, owner_observed_at=NOW + timedelta(seconds=1)),
        replace(ACTIVE, observed_at=NOW.replace(tzinfo=None)),
        replace(ACTIVE, physical_cleanup_complete=True),
        replace(ACTIVE, admission_confirmed=cast(bool, "true")),
        replace(ACTIVE, job_status=cast(JobStatus, "invented-state")),
        replace(_settled(), expires_at=None),
        replace(_settled(), retention_started_at=None),
        replace(_settled(), expires_at=STARTED + timedelta(days=31)),
        replace(_settled(), application_shutdown_complete=None),
        replace(_settled(), unfinished_obligation=PROVENANCE),
        replace(DeletionStatusObservationDTO(BINDING, NOW), physical_cleanup_complete=True),
        replace(
            _settled(),
            observed_at=datetime.max.replace(tzinfo=UTC),
            owner_observed_at=datetime.max.replace(tzinfo=UTC),
            retention_started_at=datetime.max.replace(tzinfo=UTC),
            expires_at=datetime.max.replace(tzinfo=UTC),
        ),
    ],
)
async def test_malformed_authoritative_observation_is_unavailable_not_repaired(
    observation: DeletionStatusObservationDTO,
) -> None:
    with pytest.raises(DependencyUnavailableError):
        await _lookup(observation)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        replace(AUTHORIZATION, operation_id=OperationId("other")),
        replace(AUTHORIZATION, principal_id=PrincipalId(UUID(int=99))),
    ],
)
async def test_wrong_authorized_scope_stops_before_history(
    authorization: DeletionStatusAuthorizationDTO,
) -> None:
    events: list[str] = []
    authorizer = MockDeletionAuthorizer(events)
    authorizer.result = authorization
    with pytest.raises(RuntimeError, match="scope"):
        await DeletionStatusReadService(authorizer, MockDeletionProjection(events, ACTIVE)).lookup(
            access=ACCESS, query=QUERY
        )
    assert events == ["authorize"]


@pytest.mark.asyncio
async def test_projection_failure_remains_a_failed_observation() -> None:
    events: list[str] = []
    reader = MockDeletionProjection(events, None)
    reader.failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await DeletionStatusReadService(MockDeletionAuthorizer(events), reader).lookup(
            access=ACCESS, query=QUERY
        )
    assert events == ["authorize", "read"]


def test_operation_reference_has_the_shared_wire_bound() -> None:
    assert GetDeletionStatusQuery(OperationId("a" * 128)).operation_id.value == "a" * 128
    with pytest.raises(InvalidInputError):
        GetDeletionStatusQuery(OperationId("a" * 129))


def _settled_group() -> DeletionStatusObservationDTO:
    binding = replace(
        BINDING,
        authority_family=OperationLookupAuthorityFamily.ACCESS_GROUP_DELETION,
        action_id=ActionId("delete-access-group"),
        requested_route=f"/v1/projects/{BINDING.project_id.value}/access-groups/{UUID(int=9)}",
    )
    return replace(_settled(), binding=binding, job_status=None, application_shutdown_complete=None)


@pytest.mark.asyncio
async def test_synchronous_group_completion_preserves_inapplicable_nulls_and_captured_expiry() -> (
    None
):
    original = _settled_group()
    result = await _lookup(original)
    assert isinstance(result, RetainedDeletionStatusDTO)
    assert result.job_status is None and result.application_shutdown_complete is None
    assert result.admission_confirmed is True and result.access_blocked is True
    assert result.physical_cleanup_complete is True
    assert result.expires_at == original.expires_at
    later = await _lookup(replace(original, observed_at=NOW + timedelta(days=1)))
    assert later == result
    assert isinstance(
        await _lookup(replace(original, observed_at=original.expires_at)), UnresolvedOperationDTO
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("job_status", JobStatus.SUCCEEDED),
        ("application_shutdown_complete", True),
        ("admission_confirmed", None),
        ("access_blocked", False),
        ("physical_cleanup_complete", None),
        ("unfinished_obligation", PROVENANCE),
        ("retention_started_at", None),
        ("expires_at", STARTED + timedelta(days=31)),
        ("owner_observed_at", NOW + timedelta(seconds=1)),
    ],
)
async def test_group_completion_rejects_inconsistent_owner_observations(
    field: str, value: object
) -> None:
    with pytest.raises(DependencyUnavailableError):
        await _lookup(replace(_settled_group(), **{field: value}))
