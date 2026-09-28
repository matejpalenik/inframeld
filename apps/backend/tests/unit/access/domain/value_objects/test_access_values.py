"""Verify Access values reject unusable identifiers before they reach persistence."""

from typing import cast

import pytest

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject


@pytest.mark.parametrize("raw", ["", " ", "\t"])
def test_identity_authority_rejects_blank_values(raw: str) -> None:
    with pytest.raises(ValueError):
        IdentityAuthority(raw)


@pytest.mark.parametrize("raw", ["", " ", "\t"])
def test_identity_subject_rejects_blank_values(raw: str) -> None:
    with pytest.raises(ValueError):
        IdentitySubject(raw)


@pytest.mark.parametrize("raw", ["", " ", "\t", "x" * 101])
def test_action_id_rejects_values_outside_the_grant_column(raw: str) -> None:
    with pytest.raises(ValueError):
        ActionId(raw)


def test_identity_values_preserve_exact_verified_text() -> None:
    """Identity lookup uses the exact verified pair without normalizing it."""
    assert IdentityAuthority("kratos:Local ").value == "kratos:Local "
    assert IdentitySubject(" Alice ").value == " Alice "


@pytest.mark.parametrize("value_type", [IdentityAuthority, IdentitySubject, ActionId])
def test_string_values_reject_nontext_input(
    value_type: type[IdentityAuthority] | type[IdentitySubject] | type[ActionId],
) -> None:
    """Reject nontext input that bypasses static checks without accidentally coercing identity."""
    with pytest.raises(TypeError):
        value_type(cast(str, 42))
