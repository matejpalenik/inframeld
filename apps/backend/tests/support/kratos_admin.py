"""Change or inspect test identities without publishing Kratos's admin API."""

import httpx2
from ory_kratos_client.models.identity import Identity as KratosIdentity

from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from tests.support.integration_services import KRATOS_ADMIN_URL


async def get_identity(subject: IdentitySubject) -> KratosIdentity:
    """Read credential identifiers, without requesting upstream credential secrets."""
    async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as client:
        response = await client.get(f"{KRATOS_ADMIN_URL}/admin/identities/{subject.value}")
    assert response.status_code == 200, "Kratos test identity lookup failed."
    return KratosIdentity.model_validate_json(response.text)


async def disable_identity(subject: IdentitySubject) -> None:
    """Disable the identity so a later request must reject its existing credentials."""
    async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as client:
        response = await client.patch(
            f"{KRATOS_ADMIN_URL}/admin/identities/{subject.value}",
            json=[{"op": "replace", "path": "/state", "value": "inactive"}],
        )
    assert response.status_code == 200, "Kratos test identity update failed."
