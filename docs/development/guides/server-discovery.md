# Publish and validate server discovery

An operator gives Alice one canonical API URL. Discovery returns public installation and identity-provider facts. It does not authenticate Alice, create membership or establish release compatibility. [ADR-0098](../../adr/ADR-0098-publish-bounded-first-party-discovery.md) records the accepted profile.

Issue #118 implements backend publication and the Rust library that validates those facts. The executable currently exposes help and version only. Saving a remote target remains #159 and browser login remains #160, so Alice cannot yet add an installation or sign in through the CLI.

## Configure publication

In `apps/backend/.env`, enable `INFRAMELD_DISCOVERY__PUBLIC_API_URL` together with the existing Kratos and Hydra settings. The public API identity must exactly equal `INFRAMELD_HYDRA__API_AUDIENCE`. The configured Hydra issuer must be its exact public issuer identifier. Never substitute the private admin address or infer either identifier from incoming Host or forwarded headers.

Public API and issuer settings use a maintained URL parser together with raw-input checks. Malformed hosts, credentials, queries, fragments, control characters, backslashes, malformed path escapes and dot segments fail validation. The limit is 8,192 bytes in the original UTF-8 input. Valid identities retain their exact spelling, including case, explicit ports and encoded paths. Parsed values never replace the configured identity.

The [configuration verifier](../../../apps/backend/src/inframeld_backend/access/infrastructure/verifiers/pydantic_discovery_url_verifier.py) also compares advertised identities with configured administration endpoints. It uses normalized scheme, host and effective port plus the path, treating trailing slashes as equivalent for this guard. Encoded-host, international-domain and IPv6 spelling aliases cannot hide the same endpoint. Different paths on the same origin remain distinct. These checks perform no DNS lookup and do not exclude private-network HTTPS.

The default discovery transport profile is `https`. The `managed-local` profile requires the original literal `http://127.0.0.1` authority. Normalized aliases, including `127.1` and percent-encoded loopback, cannot grant this exception. Its server configuration does not grant clients permission to trust HTTP. Only the managed-runtime owner can supply the independent trusted client context. Manual HTTP registration remains rejected.

Disabled discovery returns a safe 503 Problem Details response. Invalid enabled configuration fails startup. Startup reads the existing installation ID and caches an immutable descriptor. Missing identity stops startup rather than generating a replacement. Ordinary restart preserves that identity. No provider request occurs while serving metadata.

### Check URL syntax without starting services

With the backend dependencies installed, run this from the repository root:

```sh
uv run --project apps/backend python - <<'PY'
from pydantic import ValidationError
from inframeld_backend.access.infrastructure.settings.discovery_settings import DiscoverySettings

for label, value in (
    ("valid", "https://inframeld.company.example/api/v1"),
    ("invalid", "https://api%GG.test"),
):
    try:
        settings = DiscoverySettings(public_api_url=value)
    except ValidationError:
        print(f"{label}: rejected")
    else:
        print(f"{label}: accepted unchanged={settings.public_api_url == value}")
PY
```

Expect `valid: accepted unchanged=True` followed by `invalid: rejected`. This checks local syntax validation only. It reads no application configuration, makes no network request and saves nothing, so no cleanup is needed. It does not qualify issuer agreement, the configured admin-endpoint guard or a complete CLI registration. The executable still has no discovery command.

## Read metadata

Root resources use `/.well-known/oauth-protected-resource`. An API identity ending in `/api/v1` uses `/.well-known/oauth-protected-resource/api/v1`. The API serves only its configured resource path. Responses use JSON and `Cache-Control: no-store`.

| Field                       | Meaning                                   |
| --------------------------- | ----------------------------------------- |
| `resource`                  | Exact canonical API identity and audience |
| `authorization_servers`     | Exactly one configured Hydra issuer       |
| `scopes_supported`          | The fixed `inframeld:api` API scope       |
| `bearer_methods_supported`  | Header transport only                     |
| `inframeld.schema_version`  | Profile version 1                         |
| `inframeld.installation_id` | Persistent installation UUID              |
| `inframeld.client_id`       | Fixed `inframeld-cli` public client       |

The client preserves identifier spelling rather than trimming slashes or rewriting paths before comparison. It accepts unknown extension fields but rejects unsupported profile versions. Metadata cannot enlarge the client's scope or select another account. The [owning target workflow](../../../.agents/skills/inframeld-application-contracts/references/cli-targets-and-accounts.md#target-discovery) describes later persistence and reconfiguration.

## Verify the boundary

Use backend tests for public disclosure and startup, native PostgreSQL tests for identity persistence, real Hydra observations for issuer/client agreement, and Rust local TLS tests for the client policy. The private provider graph deliberately uses internal HTTP service addresses. Agreement tests there do not qualify an externally registered HTTP installation.

New operations also run through all selected SDK profiles using the normal endpoint/conformance workflow. Run complete `pnpm sdk:verify` and the integration suite before claiming full qualification. Record final-revision Docker and native-platform CI separately from local Podman evidence.

## Client path and capability checks

Generated SDK discovery path arguments use the [encoded relative path contract](../../../packages/sdk-tools/docs/generators.md#encoded-relative-path-parameters). Its 24,576-character ASCII budget accommodates the maximum threefold expansion of the original 8,192-byte UTF-8 input. The original URL limit remains unchanged. The Rust library preserves the URL path directly, so `/api/v1` and `/api%2Fv1` remain distinct on the wire. Malformed authority syntax and user information, including an empty username, fail URL validation before network I/O.

OIDC requests and parsed provider endpoints use a separate 24,609-byte URL budget. This allows threefold encoding expansion plus the 33-byte metadata suffix that the OIDC library can append. Original API and issuer input still passes the 8,192-byte check first. The provider budget applies to metadata and signing-key requests and to advertised authorization, token, user-info and revocation endpoints, retaining the same syntax, HTTPS, exact-origin and managed-local checks.

Local SDK request-serialization rejection is reported as invalid URL input, without retaining the underlying message. Actual connection failures remain connection failures. Deployment proxies and HTTP servers can impose their own request limits, so accepted client input does not establish every installation's capacity for long request paths.

Ordinary HTTPS targets support an explicit proxy and additional trusted CAs. Managed-local discovery rejects explicit proxies and never adopts inherited proxy settings. Provider metadata must support both authorization-code and refresh grants, a code response, public-client authentication and S256. Missing grant metadata has the standard authorization-code/implicit default and therefore fails this profile's refresh requirement. These checks establish discovery compatibility, while complete login remains separately qualified.

## Follow the Rust implementation

The public entry point and records remain reachable through [`discovery`](../../../apps/cli/src/discovery/mod.rs). The facade also holds the sealed managed-local context. [`discover.rs`](../../../apps/cli/src/discovery/discover.rs) owns the overall deadline and ordered sequence of API metadata, provider metadata and key-set reads. [`installation.rs`](../../../apps/cli/src/discovery/installation.rs) owns the returned records and provider-profile validation.

[`url_policy.rs`](../../../apps/cli/src/discovery/url_policy.rs) makes API and issuer trust decisions through named methods. [`oidc_transport.rs`](../../../apps/cli/src/discovery/oidc_transport.rs) constructs HTTP transport and adapts bounded requests to the OpenID Connect library. [`error.rs`](../../../apps/cli/src/discovery/error.rs) preserves the public safe failure categories. Transport scenarios remain together in `transport_tests.rs`, with pure URL tests beside the policy. These modules change navigation without adding an executable discovery command.

## Manually check the current delivery

The user goal is to recognize the installation behind the operator's URL before saving a target or starting login. The current delivery can be inspected at the public HTTP boundary. It has no discovery command in the executable yet.

From the repository root, with the pinned Rust toolchain installed, inspect the available CLI commands:

```sh
cargo run --locked -p inframeld-cli --bin inframeld -- --help
```

Expect help listing `version`, with no target-registration, discovery or login command. This checks the current command surface and does not contact an installation.

To inspect server publication, use an already-running installation with discovery configured as above, network or VPN access and a trusted HTTPS certificate. Replace the example hostname with the operator's actual hostname. This example assumes its exact configured API identity is `https://inframeld.company.example/api/v1`:

```sh
curl --proto '=https' --max-time 10 --fail --silent --show-error \
  --dump-header - \
  'https://inframeld.company.example/.well-known/oauth-protected-resource/api/v1'
```

Expect HTTP 200, `Cache-Control: no-store` and the public JSON fields listed above. Confirm that `resource` exactly matches the operator's API URL, the single authorization server matches the public Hydra issuer, and the client is `inframeld-cli`. Private admin endpoints and credentials must be absent. Repeat the request to confirm that the installation ID stays the same. For a root API identity, use `/.well-known/oauth-protected-resource` without the path suffix.

For a rejection case on that same configured installation, request a different resource path:

```sh
curl --proto '=https' --max-time 10 --fail --silent --show-error \
  --dump-header - \
  'https://inframeld.company.example/.well-known/oauth-protected-resource/another-api'
```

Expect HTTP 404 and curl exit status 22. If discovery is disabled, the configured discovery endpoint returns 503 instead of metadata. A private CA requires the operator's CA certificate through curl's `--cacert` option. Keep certificate verification enabled.

These anonymous reads change no application state and need no cleanup. They inspect server publication, not the Rust consumer's OIDC, key-set or transport-policy checks. Curl also has its own proxy behavior. Do not treat these reads as a complete CLI registration or login test.

For a separate automated check of the Rust library, run from the repository root:

```sh
cargo test --locked -p inframeld-cli --lib discovery::
```

These tests use controlled local servers, require no company installation and cover success and rejection behavior. Once #159 exposes target registration and #160 exposes login, their guides must add the actual executable commands and expected saved-target and authenticated behavior.
