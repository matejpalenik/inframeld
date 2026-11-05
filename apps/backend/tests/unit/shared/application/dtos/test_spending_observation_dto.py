from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId


def _observation() -> SpendingObservationDTO:
    return SpendingObservationDTO(
        UUID(int=1),
        ModelCallId(UUID(int=2)),
        SpendingObservationKind.CHARGE,
        datetime(2026, 11, 1, tzinfo=UTC),
        "fixture-charge",
        charge=Decimal("0.000000000000001"),
    )


def test_keeps_raw_charge_precision_until_accounting_conversion() -> None:
    assert _observation().charge == Decimal("0.000000000000001")


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_rejects_invalid_authoritative_charge_values(value: str) -> None:
    with pytest.raises(ValueError):
        replace(_observation(), charge=Decimal(value))


def test_usage_requires_quantities_and_cannot_also_claim_a_charge() -> None:
    with pytest.raises(ValueError):
        replace(_observation(), kind="usage", charge=None)

    with pytest.raises(ValueError):
        replace(
            _observation(), kind="usage", usage=(SpendingUsageDTO("input", "unit", Decimal("1")),)
        )


@pytest.mark.parametrize("kind", ["not_sent", "not_billed", "uncertain"])
def test_non_charge_outcomes_cannot_smuggle_a_charge(kind: str) -> None:
    with pytest.raises(ValueError):
        replace(_observation(), kind=kind)  # pyright: ignore[reportArgumentType]


def test_requires_bound_evidence_identity_and_time() -> None:
    with pytest.raises(TypeError):
        replace(_observation(), evidence_id="invented")

    with pytest.raises(ValueError):
        replace(_observation(), observed_at=datetime(2026, 11, 1))
