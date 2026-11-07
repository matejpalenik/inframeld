import pytest
from starlette.exceptions import HTTPException

from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.http.mappers.incoming_credential_mapper import (
    IncomingCredentialMapper,
)
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)

KEY = "ifm_app_00000000-0000-4000-8000-000000000001_" + "A" * 43


@pytest.mark.parametrize(
    "header, kind",
    [
        ("bEaReR " + KEY, ApplicationKeyCredential),
        ("Bearer human-opaque", HumanAccessTokenCredential),
    ],
)
def test_one_bearer_stays_in_its_selected_credential_family(
    header: str, kind: type[ApplicationKeyCredential | HumanAccessTokenCredential]
) -> None:
    result = IncomingCredentialMapper.select(authorization_headers=[header], cookies={})
    assert isinstance(result, kind)


def test_cookie_is_selected_without_unrelated_cookie_competition() -> None:
    result = IncomingCredentialMapper.select(
        authorization_headers=[], cookies={"ory_kratos_session": "cookie", "unrelated": "other"}
    )
    assert result == BrowserSessionCredential("cookie")


@pytest.mark.parametrize(
    "headers, cookies",
    [
        (["Bearer one", "Bearer two"], {}),
        (["Bearer one"], {"ory_kratos_session": ""}),
        (["Bearer"], {}),
        (["Bearer token extra"], {}),
    ],
)
def test_ambiguous_or_malformed_request_is_rejected_before_verification(
    headers: list[str], cookies: dict[str, str]
) -> None:
    with pytest.raises(InvalidAuthenticationRequestError):
        IncomingCredentialMapper.select(authorization_headers=headers, cookies=cookies)


@pytest.mark.parametrize(
    "header", ["Bearer ifm_app_", "Bearer " + KEY + "=", "Basic user:password"]
)
def test_unsupported_or_invalid_credential_has_safe_401(header: str) -> None:
    with pytest.raises(HTTPException) as error:
        IncomingCredentialMapper.select(authorization_headers=[header], cookies={})
    assert error.value.status_code == 401
    assert header not in str(error.value)
