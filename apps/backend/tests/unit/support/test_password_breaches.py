"""Exercise the local HIBP contract without contacting an external service."""

import httpx2
import pytest
from tests.support.password_breaches import BREACHED_PASSWORD_SHA1, create_app


@pytest.mark.asyncio
async def test_breached_password_returns_matching_suffix_and_records_lookup() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=create_app()), base_url="https://password-breaches:8443"
    ) as client:
        prefix = BREACHED_PASSWORD_SHA1[:5]
        response = await client.get(f"/range/{prefix}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == f"{BREACHED_PASSWORD_SHA1[5:]}:1\n"
        assert (await client.get(f"/observations/{prefix}")).json() == {"requests": 1}


@pytest.mark.asyncio
async def test_unlisted_password_range_is_empty_and_does_not_reuse_another_apps_counts() -> None:
    prefix = "00000"
    for _ in range(2):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=create_app()),
            base_url="https://password-breaches:8443",
        ) as client:
            assert (await client.get(f"/observations/{prefix}")).json() == {"requests": 0}
            response = await client.get(f"/range/{prefix.lower()}")
            assert response.status_code == 200
            assert response.text == ""
            assert (await client.get(f"/observations/{prefix}")).json() == {"requests": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["abc", "GGGGG", "123456"])
async def test_malformed_range_is_rejected(prefix: str) -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=create_app()), base_url="https://password-breaches:8443"
    ) as client:
        assert (await client.get(f"/range/{prefix}")).status_code == 422


@pytest.mark.asyncio
async def test_readiness_does_not_count_as_a_password_lookup() -> None:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=create_app()), base_url="https://password-breaches:8443"
    ) as client:
        assert (await client.get("/health/ready")).status_code == 200
        assert (await client.get(f"/observations/{BREACHED_PASSWORD_SHA1[:5]}")).json() == {
            "requests": 0
        }
