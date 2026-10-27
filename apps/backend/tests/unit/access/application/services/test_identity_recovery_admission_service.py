from dataclasses import replace
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.identity_recovery_admission_writer import (
    IdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

EVENT = IdentityRecoveryEventDTO(
    flow_id=IdentityRecoveryFlowId(UUID("10000000-0000-0000-0000-000000000001")),
    identity=VerifiedHumanIdentityDTO(
        authority=IdentityAuthority("https://identity.example.test"),
        subject=IdentitySubject("20000000-0000-0000-0000-000000000001"),
    ),
    event_kind=IdentityRecoveryEventKind.RECOVERY,
)
ORIGINAL_OPERATION = OperationId("original-recovery-operation")
ADMISSION = IdentityRecoveryAdmissionDTO(event=EVENT, operation_id=ORIGINAL_OPERATION)


class MockIdentityRecoveryAdmissionWriter(IdentityRecoveryAdmissionWriter):
    """Return a fixed stored binding. These tests do not simulate database durability."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls: list[IdentityRecoveryEventDTO] = []
        self.unavailable = unavailable

    @override
    async def reserve(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryAdmissionDTO:
        self.calls.append(event)
        if self.unavailable:
            raise DependencyUnavailableError()
        return ADMISSION


@pytest.mark.asyncio
async def test_matching_callbacks_return_the_original_operation() -> None:
    writer = MockIdentityRecoveryAdmissionWriter()
    service = IdentityRecoveryAdmissionService(writer)

    first = await service.admit(EVENT)
    repeated = await service.admit(replace(EVENT))

    assert first == repeated == ORIGINAL_OPERATION
    assert writer.calls == [EVENT, EVENT]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conflicting_event",
    [
        pytest.param(
            replace(
                EVENT,
                flow_id=IdentityRecoveryFlowId(UUID("10000000-0000-0000-0000-000000000002")),
            ),
            id="different-flow",
        ),
        pytest.param(
            replace(
                EVENT,
                identity=replace(
                    EVENT.identity,
                    authority=IdentityAuthority("https://other-identity.example.test"),
                ),
            ),
            id="different-authority",
        ),
        pytest.param(
            replace(
                EVENT,
                identity=replace(
                    EVENT.identity,
                    subject=IdentitySubject("20000000-0000-0000-0000-000000000002"),
                ),
            ),
            id="different-subject",
        ),
        pytest.param(
            replace(EVENT, event_kind=IdentityRecoveryEventKind.PASSWORD_RESET),
            id="different-event-kind",
        ),
    ],
)
async def test_conflicting_stored_binding_is_rejected(
    conflicting_event: IdentityRecoveryEventDTO,
) -> None:
    writer = MockIdentityRecoveryAdmissionWriter()
    service = IdentityRecoveryAdmissionService(writer)

    with pytest.raises(
        ConflictError,
        match="The recovery flow is already bound to another event.",
    ):
        await service.admit(conflicting_event)

    assert writer.calls == [conflicting_event]


@pytest.mark.asyncio
async def test_unconfirmed_reservation_does_not_return_an_operation() -> None:
    writer = MockIdentityRecoveryAdmissionWriter(unavailable=True)
    service = IdentityRecoveryAdmissionService(writer)

    with pytest.raises(DependencyUnavailableError):
        await service.admit(EVENT)

    assert writer.calls == [EVENT]
