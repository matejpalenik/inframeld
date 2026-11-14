import pytest

from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication as Auth,
)
from inframeld_backend.access.domain.enums.model_connection_provider import (
    ModelConnectionProvider as Provider,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)


@pytest.mark.parametrize(
    ("provider", "url", "authentication"),
    [
        (Provider.OPENAI, "https://api.openai.com/v1", Auth.API_KEY),
        (Provider.OPENAI_COMPATIBLE, "https://models.example.test:8443/v1", Auth.API_KEY),
        (Provider.OPENAI_COMPATIBLE, "https://10.1.2.3/v1", Auth.API_KEY),
        (Provider.OLLAMA, "http://127.0.0.1:11434", Auth.NONE),
        (Provider.OLLAMA, "http://[::1]:11434", Auth.NONE),
    ],
)
def test_explicit_deployment_policy_allows_the_exact_supported_configuration(
    provider: Provider, url: str, authentication: Auth
) -> None:
    policy = (
        ModelConnectionDestinationPolicy(https_base_urls=frozenset({url}))
        if url.startswith("https:")
        else ModelConnectionDestinationPolicy(local_ollama_base_urls=frozenset({url}))
    )
    assert policy.permits(
        provider=provider, base_url=url, api_version=None, authentication=authentication
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/v1",
        "https://[::ffff:a9fe:a9fe]/v1",
        "https://[fe80::1]/v1",
        "https://100.100.100.200/v1",
        "https://metadata.google.internal/v1",
        "https://0.0.0.0/v1",
        "https://0x7f000001/v1",
        "https://0177.0.0.1/v1",
        "https://example.test./v1",
        "https://example.test:0/v1",
        "https://example.test:/v1",
        "https://example.test:65536/v1",
        "https://user:pass@example.test/v1",
        "https://example.test/v1?key=hidden",
        "https://example.test/v1#fragment",
        "https://example.test/v1/../api",
        "https://example.test/v1/%2e%2e/api",
        "https://example.test/v1//api",
        "https://example.test/v1\\api",
        "https://example.test/v1\n",
    ],
)
def test_unsafe_destination_is_rejected_even_if_configured(url: str) -> None:
    policy = ModelConnectionDestinationPolicy(https_base_urls=frozenset({url}))
    assert not policy.permits(
        provider=Provider.OPENAI_COMPATIBLE,
        base_url=url,
        api_version=None,
        authentication=Auth.API_KEY,
    )


@pytest.mark.parametrize(
    ("provider", "url", "api_version", "authentication"),
    [
        (Provider.OPENAI_COMPATIBLE, "https://models.example.test/v2", None, Auth.API_KEY),
        (Provider.OPENAI_COMPATIBLE, "https://models.example.test/v1", "future", Auth.API_KEY),
        (Provider.OPENAI_COMPATIBLE, "https://models.example.test/v1", None, Auth.NONE),
        (Provider.OLLAMA, "http://127.0.0.1:11434", None, Auth.API_KEY),
        (Provider.OPENAI_COMPATIBLE, "http://127.0.0.1:11434", None, Auth.API_KEY),
        (Provider.OLLAMA, "http://10.1.2.3:11434", None, Auth.NONE),
    ],
)
def test_project_cannot_expand_origin_path_version_or_authentication(
    provider: Provider, url: str, api_version: str | None, authentication: Auth
) -> None:
    policy = ModelConnectionDestinationPolicy(
        https_base_urls=frozenset({"https://models.example.test/v1"}),
        local_ollama_base_urls=frozenset({"http://127.0.0.1:11434"}),
    )
    assert not policy.permits(
        provider=provider, base_url=url, api_version=api_version, authentication=authentication
    )


def test_https_allowlist_does_not_enable_unauthenticated_remote_ollama() -> None:
    url = "https://ollama.example.test"
    policy = ModelConnectionDestinationPolicy(https_base_urls=frozenset({url}))
    assert not policy.permits(
        provider=Provider.OLLAMA, base_url=url, api_version=None, authentication=Auth.NONE
    )
