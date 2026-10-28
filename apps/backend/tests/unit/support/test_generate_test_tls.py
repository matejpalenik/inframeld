"""Verify disposable certificate trust through real TLS connections."""

import asyncio
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from stat import S_IMODE

import pytest
from cryptography import x509
from tests.support.generate_test_tls import generate_certificates


@asynccontextmanager
async def _tls_server(identity: Path) -> AsyncGenerator[int]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(identity / "server.pem", identity / "server.key")

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readexactly(1)
        writer.write(b"ready")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0, ssl=context)
    async with server:
        yield int(server.sockets[0].getsockname()[1])


async def _connect(port: int, ca: Path, hostname: str = "password-breaches") -> bytes:
    context = ssl.create_default_context(cafile=str(ca / "ca.pem"))
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname=hostname),
        timeout=2,
    )
    try:
        writer.write(b"?")
        await writer.drain()
        return await asyncio.wait_for(reader.readexactly(5), timeout=2)
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_generated_identity_allows_verified_tls(tmp_path: Path) -> None:
    trust, identity = tmp_path / "trust", tmp_path / "identity"
    generate_certificates(trust, identity)

    async with _tls_server(identity) as port:
        assert await _connect(port, trust) == b"ready"


@pytest.mark.asyncio
async def test_certificate_rejects_an_incorrect_hostname(tmp_path: Path) -> None:
    trust, identity = tmp_path / "trust", tmp_path / "identity"
    generate_certificates(trust, identity)

    async with _tls_server(identity) as port:
        with pytest.raises(ssl.SSLCertVerificationError, match="[Hh]ostname mismatch"):
            await _connect(port, trust, "other-service")


@pytest.mark.asyncio
async def test_new_stack_trust_rejects_previous_stack_identity(tmp_path: Path) -> None:
    first_trust, first_identity = tmp_path / "first-trust", tmp_path / "first-identity"
    next_trust, next_identity = tmp_path / "next-trust", tmp_path / "next-identity"
    generate_certificates(first_trust, first_identity)
    generate_certificates(next_trust, next_identity)
    assert (first_trust / "ca.pem").read_bytes() != (next_trust / "ca.pem").read_bytes()

    async with _tls_server(first_identity) as port:
        with pytest.raises(ssl.SSLCertVerificationError):
            await _connect(port, next_trust)


@pytest.mark.asyncio
async def test_expired_server_identity_is_rejected(tmp_path: Path) -> None:
    trust, identity = tmp_path / "trust", tmp_path / "identity"
    generate_certificates(trust, identity, now=datetime.now(UTC) - timedelta(days=2))

    async with _tls_server(identity) as port:
        with pytest.raises(ssl.SSLCertVerificationError, match="expired"):
            await _connect(port, trust)


def test_exports_only_required_material_with_restricted_key_access(tmp_path: Path) -> None:
    trust, identity = tmp_path / "trust", tmp_path / "identity"
    now = datetime.now(UTC)
    generate_certificates(trust, identity, now=now)

    assert {path.name for path in trust.iterdir()} == {"ca.pem", "server-not-after.txt"}
    assert datetime.fromisoformat((trust / "server-not-after.txt").read_text()) == (
        now + timedelta(hours=24)
    ).replace(microsecond=0)
    assert {path.name for path in identity.iterdir()} == {"server.pem", "server.key"}
    for path, mode in (
        (trust, 0o755),
        (identity, 0o700),
        (trust / "ca.pem", 0o644),
        (identity / "server.pem", 0o644),
        (identity / "server.key", 0o600),
    ):
        assert S_IMODE(path.stat().st_mode) == mode

    certificate = x509.load_pem_x509_certificate((identity / "server.pem").read_bytes())
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ["password-breaches"]
    assert (
        abs((certificate.not_valid_before_utc - (now - timedelta(minutes=5))).total_seconds()) < 1
    )
    assert abs((certificate.not_valid_after_utc - (now + timedelta(hours=24))).total_seconds()) < 1


def test_existing_material_is_not_replaced_or_partially_reused(tmp_path: Path) -> None:
    trust, identity = tmp_path / "trust", tmp_path / "identity"
    trust.mkdir()
    previous = trust / "ca.pem"
    previous.write_bytes(b"incomplete previous generation")

    with pytest.raises(ValueError, match="empty"):
        generate_certificates(trust, identity)

    assert previous.read_bytes() == b"incomplete previous generation"
    assert not (identity / "server.key").exists()
