# Manage the local runtime and its HTTP boundary

<a id="manage-the-local-runtime-and-its-http-boundary"></a>

Alice starts one persistent personal installation on her machine. The narrow managed-loopback HTTP exception comes from verified runtime state. A target named local or a private address does not establish that boundary.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="managed-local-http"></a>

<a id="use-http-only-for-the-cli-managed-loopback-trial"></a>

### Use HTTP only for the CLI-managed loopback trial

The developer accepted local HTTP instead of installing a local certificate authority. This exception covers only the same-machine runtime provisioned and controlled by the CLI for the current OS user, with installation identity and endpoint configuration from protected managed state. It is not selected by a target's name, an arbitrary URL, a server claim or a general insecure flag.

- Publish necessary public UI/protocol/API listeners only on literal loopback. Do not expose identity administration, introspection, databases or storage ports, even on loopback. Preserve the private container network and the narrow operator maintenance channel.
- Require the CLI, browser and managed runtime on the same supported machine. Remote Docker contexts, LAN/shared servers, tunnels and port forwarding do not qualify. Use HTTPS for ordinary added/imported targets, including private addresses.
- Keep exact configured origins, host/Origin checks, CSRF, normal authentication, authorization, budgets and rate limits. Use Ory's documented development mode only in this bounded profile. Do not disable TLS certificate verification or use `--insecure` for remote connections or model destinations.
- Persist issuer/installation identity and server state across stop/start. Fail on an occupied configured service port instead of adopting another listener. A deliberate origin change invalidates the affected stored authentication. A destructive reset creates a new installation identity even if its URLs match the old one.
- The temporary CLI callback has its own standard loopback exception for local or remote login. It must not be confused with permission to send production token/API requests over HTTP.

The following requirements apply to the accepted managed-local profile. They are not certification of existing Compose files.

<a id="what-qualifies-as-managed-local"></a>

#### What qualifies as managed local

All of these conditions are required together:

1. The runtime was provisioned and is managed by this CLI for the current OS user under the single persistent-instance contract. Its identity and effective endpoint configuration come from the protected local runtime state, not a server response or arbitrary target file.
2. The CLI, browser and runtime are on the same supported development machine. A qualified Docker Desktop VM may be part of that machine. A remote Docker daemon/context, remote workstation, shared server, tunnel or forwarded port is not the managed local exception.
3. Host-published public service listeners bind explicitly to loopback and are not exposed to the LAN, internet or other interfaces. Private services are not published. Runtime configuration must preserve the private container network, not enable direct external routing or host-network exposure.
4. The CLI verifies the intended runtime/configuration and supported isolation prerequisites before starting login or sending saved credentials. Unknown, stale, redirected or conflicting state fails closed with a repair instruction.

A target named `local`, a private RFC1918 address, a hostname resolving to loopback or a successful HTTP health response does not independently establish these conditions. Imported/manually added targets do not acquire the exception. There is no user-settable `allow_http` or `--insecure` escape hatch for arbitrary targets. This verification checks managed state and exposure. It is not TLS-like proof against an attacker who controls the development machine.

<a id="allowed-connections-and-published-endpoints"></a>

#### Allowed connections and published endpoints

| Connection | Transport/exposure rule |
| --- | --- |
| Host CLI/browser to the managed local API, account UI and Ory public endpoints | HTTP permitted only at the runtime's exact configured loopback origins |
| The managed stack's internal service calls | Private same-machine container-network HTTP is permitted where supported. No host publication of admin/storage services |
| Desktop browser to the temporary CLI OAuth callback | HTTP on literal loopback and the registered `/oauth/callback` path. RFC 8252 exception, independently of local/remote target |
| CLI/browser to remote, LAN-accessible or production public endpoints | Certificate-verified HTTPS. Private IPs and environment labels do not waive it |
| External model/identity-provider traffic | Preserve verified HTTPS and existing provider policy. Local HTTP does not authorize secret-bearing HTTP to a provider |

For the first managed implementation, use literal `127.0.0.1` consistently for browser/host-facing HTTP URLs, with only the runtime's explicitly recorded ports and routes. Do not mix `localhost`, another IP spelling or an arbitrary local domain into the same cookie/issuer configuration. Do not publish a wildcard IPv6 listener alongside an IPv4 loopback listener. Additional address families need their own explicit configuration and qualification, not implicit fallback.

The actual service port numbers/routes are release configuration, not guessed defaults in multiple clients. Record them once in managed runtime state and generate the matching Ory/UI/CLI settings. Preserve origins across restart. If a port is occupied, fail rather than silently changing the issuer or sending credentials to the process using it. A deliberate origin change follows the Access guide's authentication-binding invalidation rule. The temporary OAuth callback port remains ephemeral and is not the issuer's persistent port.

Publish only the needed public entry point(s). Never publish Hydra/Kratos admin, PostgreSQL or storage ports, even on loopback, merely because it is development. The host operator's narrow maintenance channel for initial host-authorized bootstrap remains separate. UI server code may use explicit private service addresses. The browser still uses the configured public loopback origins. Internal routing cannot redefine the issuer, audience or browser redirect destination.

This is the CLI-managed runtime contract. Today's [developer Compose profile](../../../../compose.dev.yaml) also serves host-side backend development and publishes the application database on loopback. It does not yet implement that managed isolation contract. Its Hydra public endpoint is `127.0.0.1:14444`, with administration private, and its containerized API uses audience `http://127.0.0.1:8001`. [Explicit setup](../../../../docs/development/getting-started/local-setup.md#configure-the-cli-client) reconciles the official client before containerized API startup. The future runtime must reuse that provisioning capability with its own verified origins rather than exposing administration to the host CLI.

[Docker's port-publishing documentation](https://docs.docker.com/engine/network/port-publishing/) warns that unqualified port mappings publish beyond localhost, and that versions older than 28.0.0 have a localhost/L2 exposure caveat. Do not qualify an affected runtime on the strength of the Compose binding alone. Require a supported fixed runtime and verify actual exposure, including VM/WSL networking where offered.

<a id="http-exception-enforcement"></a>

#### HTTP exception enforcement

Use a target-scoped HTTP client policy derived from verified managed state, not a global TLS disable switch. HTTP API/discovery/token/revocation endpoints must be the expected local endpoints. Validate discovery issuer and endpoint destinations before any credential exchange. Do not follow a discovered URL or redirect that expands the HTTP allowlist. Do not forward Authorization/cookies to another origin. The normal remote client always verifies TLS, including while another concurrent command is working against local.

Disable proxy forwarding for managed loopback CLI requests explicitly. Inherited `HTTP_PROXY`/`HTTPS_PROXY` settings must not send local credentials off-machine. The supported browser/runtime configuration must also bypass network proxies for its loopback origins. If this cannot be established in a managed corporate or remote-browser environment, do not claim this local mode is qualified. Direct the user to an HTTPS deployment. This is not permission to change their system proxy.

Allow only configured Host/origin values at the public entry points. Keep browser Origin/CSRF checks and restrictive CORS where applicable. No wildcard credentialed origins and no assumption that a request is authorized because it came from loopback. Exact host validation and rejected cross-origin requests are release checks, including requests from hostile websites and DNS-rebinding attempts. Origin checks do not replace authentication or constrain a malicious native process that can fabricate headers.

External company sign-in can redirect through its separately configured HTTPS identity provider using the ordinary Ory integration. That is not permission for an off-machine HTTP hop. Providers or browser authentication methods that require an HTTPS callback/origin must be tested in the HTTPS deployment. Do not weaken their policy or promise that every production method works in local HTTP.

<a id="preserve-authentication-qualify-development-settings"></a>

#### Preserve authentication. Qualify development settings

Use Ory's documented development configuration for HTTP, and inventory the exact security differences in the pinned Kratos/Hydra/UI versions. Kratos documents [HTTP localhost development mode](https://www.ory.com/docs/oss/kratos/debug/csrf). The pinned [Hydra quickstart](https://github.com/ory/hydra/blob/v26.2.0/quickstart.yml) uses `--dev`. These establish development support, not approval to copy the full demo stack: its example admin port exposure and other demo conveniences are not Inframeld's contract.

The local override may enable the supported HTTP/cookie behavior needed by those components. It must not become a generic backend "skip security" mode. Retain real Kratos identities and login, the Access login transaction's PKCE/state/nonce and issuer checks, audience/client/scope validation, private introspection, active-account checks, normal grants, revocation/rotation, CSRF and secure credential storage. Use real per-installation persistent server secrets, not Ory sample secrets or passwords. Do not disable a failing check to make the quickstart work.

Explicitly test cookie attributes, cookie-name separation from unrelated local apps, CSRF, redirect handling, browser login/recovery and CLI refresh/logout. Keep cookies HttpOnly where required by the account integration. Record any HTTP-specific Secure/SameSite behavior rather than claiming production cookie parity. Scope cookies as narrowly as the supported Ory integration permits. Ports alone are not a cookie-isolation boundary.

Remote/production deployment configuration must not inherit these development flags or relaxed public-cookie settings. Local and production profiles/configs must be independently reviewable and tested. If a selected library/release cannot support the bounded development mode through documented options, block that release/integration. Do not fork the protocol or introduce a custom token bridge.

<a id="threat-model-and-non-goals"></a>

#### Threat model and non-goals

This mode is for a trusted, personal development machine, not a shared service or a security boundary against hostile local users/processes. Local API calls and identity flows may carry credentials over plaintext HTTP within that host, including credentials submitted to normal provider-connection setup. OS secure storage protects persisted CLI credentials. It does not encrypt the HTTP path. PKCE protects authorization-code redemption, not captured bearer tokens or every message in the browser flow. Docker itself does not provide TLS.

No claim is made that HTTP authenticates the local server cryptographically or resists a compromised host, malicious local process, privileged packet capture or replacement of trusted runtime state. Explicit binding, private services and browser defenses reduce exposure but do not eliminate these residual risks. Use development identities/data and appropriately limited provider credentials. External provider calls still follow the existing ModelGateway HTTPS policy. The accepted credential-free local Ollama exception is unchanged.

Production and network use retain the normal OAuth/TLS security requirements. RFC 8252's loopback callback exception is not an exemption for OAuth token/API endpoints in production. Our additional development-only HTTP allowance is an explicit Inframeld deployment choice using Ory's supported development mode. Keep an HTTPS deployment in the release tests for production cookies, TLS and identity-provider integration. Local HTTP success is not production qualification.

<a id="startup-setup-and-fail-closed-behavior"></a>

#### Startup, setup and fail-closed behavior

`local start` checks the supported local runtime and effective isolation settings, starts/reuses the stack and reports runtime health plus the next setup command. It does not install a CA, change trust stores, authenticate, create a human, claim administration or change the saved target/account/project selections. `setup --target local` rechecks the boundary, explicitly reports local HTTP development mode, then follows normal browser authentication, host-authorized bootstrap and explicit context-selection steps. Existing valid login/setup state is reused safely.

| Condition | Required outcome |
| --- | --- |
| Qualified managed loopback runtime | Continue using its exact HTTP origins. No certificate ceremony |
| Remote Docker context, unverified origin or unsupported isolation | Refuse managed-local startup/login as appropriate. No credential disclosure |
| Wildcard/LAN publishing or exposed private services | Fail preflight. Do not declare the stack ready or start authentication |
| Expected port occupied or runtime identity changed | Stop with a conflict/reset explanation. Do not reuse credentials against the responder |
| Local runtime stopped/unavailable | Give the explicit `local start` instruction. Never fall back to dev/prod |
| Ordinary target configured with HTTP | Reject it before authentication, even if named `local` or pointing at loopback/private IP |
| Remote certificate failure or HTTPS-to-HTTP redirect | Fail TLS/authentication. Never apply the local exception |
| Local browser/provider flow incompatible with HTTP | Report the unsupported configuration and HTTPS deployment path. Do not bypass the failing control |
| User requests LAN/tunnel/public access | Use the normal HTTPS deployment procedure, not a broadened local bind or inherited dev profile |

Neither `--no-input` nor a general confirmation flag can authorize relaxing these boundaries. An optional production-like HTTPS installation on the same machine is an ordinary HTTPS target, not a required extra v1 local TLS/CA wizard. No existing CA is removed automatically. Removing previously installed trust is a separate explicit operator action, not part of this design-document update.

<a id="persistent-lifecycle-status-and-deliberate-reset"></a>

## Persistent lifecycle, status and deliberate reset

The CLI initially supports macOS and Linux. Platform and architecture claims still require the release’s qualification matrix. It manages one persistent local development installation without requiring a project initialization file. A repository directory or target alias is not proof of ownership.

`local start` and an explicit setup are separate. Returning later through concise status reports saved context, runtime and permitted progress without starting services, authenticating, repairing or replaying work. If the runtime is stopped, show the explicit start command. Stopping the local runtime does not cancel durable jobs. They remain saved for safe continuation after restart under the ordinary current-authority and uncertainty checks.

Upgrades are explicit and preserve installation data and identity through the controlled migration procedure. A reset is a different, destructive operation. Review the verified owned managed installation and the current OS user’s complete CLI state before factory reset. It removes local copies of remote target definitions and logins as well as local data. It does not reset remote installations, source files, another user’s state or an unrelated container runtime. A new managed installation receives a new identity, so old bindings cannot silently apply. Diagnosis only observes and reports. It never uses a failed health check as permission to repair or repeat an operation.
