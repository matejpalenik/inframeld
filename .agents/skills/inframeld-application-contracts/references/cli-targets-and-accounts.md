# Select a CLI target, account and project

<a id="select-a-cli-target-account-and-project"></a>

Alice has separate local and remote logins. A one-shot target override must select the remote target’s own account and project without forwarding local credentials or changing tomorrow’s saved selection.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="cli-context"></a>

<a id="resolve-target-account-and-project-without-changing-identity"></a>

### Resolve target, account and project without changing identity

Alice has local selected, with `admin` selected on local and `alice` selected on dev. Running `pipeline list --target dev` uses dev/Alice and that pair's saved project. It does not send local/Admin credentials to dev, select dev for tomorrow or copy any data. A target is an installation connection, not a Pipeline Deployment.

The CLI stores one global target preference, one account preference per target and one project UUID per target/account pair. Account aliases identify locally saved human bindings, not server directory entries, application accounts, email-based identities or impersonation rights. Credentials live separately in the OS store. Account aliases for the same principal in one target must not create independent rotating-token copies.

| Scope | Explicit input | Environment | Saved fallback |
| --- | --- | --- | --- |
| Target | `--target` | `INFRAMELD_TARGET` | Globally selected registered target |
| Human account | `--account` | `INFRAMELD_ACCOUNT` | Selected account within the effective target |
| Project | Exactly one of `--project` or `--project-id` | Exactly one of `INFRAMELD_PROJECT` or `INFRAMELD_PROJECT_ID` | Project UUID within the effective target/account pair |

These are accepted selector names. Precise validation/output schemas remain deliverables. Resolve target, then account, validate its credential binding, then resolve any required project under normal current access. Freeze the resulting installation/principal/project identity for admission, polling and retries. Refresh may replace credentials for that same identity, never substitute another account.

For projects, select a whole precedence level rather than merging name and ID independently. Both explicit forms are a usage error even if they resolve to the same project. With no explicit form, both environment forms are a usage error. Either explicit form ignores **both** environment forms, including an invalid value or conflict between them. Validate an effective blank/invalid selector as an error. Do not fall back. Ignored lower-priority invalid values cannot block a valid explicit choice. Only read context variables relevant to the operation.

`INFRAMELD_TARGET` names an already registered target, not a URL or transport exception. `INFRAMELD_ACCOUNT` resolves only within that target. `INFRAMELD_PROJECT` is an exact Name, never a Display name/fuzzy search. IDs retain installation, existence and access checks. Unknown, inaccessible, logged-out or revoked context never selects another resource automatically, even when only one alternative exists. Ordinary commands give actionable errors. Interactive setup may ask for explicit selections.

| Proposed command | Persisted effect |
| --- | --- |
| `inframeld target use dev` | Only the global target preference |
| `inframeld account use alice --target dev` | Only dev's selected-account preference |
| `inframeld project use legal-research --target dev --account alice` | Only dev/Alice's selected project UUID, after authorized resolution |
| `inframeld pipeline list --target dev --account alice --project legal-research` | None |
| `inframeld login --target dev --account alice` | Establish/renew that bound login, not context preferences |
| `inframeld logout --target dev --account alice` | Revoke/remove that login's credentials. Retain preferences and other logins |

Target/account selection is local preference management: it does not need a reachable backend or credential refresh merely to save a known selection. Selecting a logged-out account is valid but must report login required. Unknown selectors fail without changing preferences. Project selection resolves current access before saving. A failure preserves the old preference. Selection never creates membership, grants or a second local runtime.

An explicit positional value in `use` is the selection being saved. Reject competing explicit selectors. Upper scopes still use normal precedence. Saving a preference never edits shell variables/profiles. When an environment variable continues to override a saved choice, say so:

```text
$ inframeld target use local
Saved target: local
This shell still uses dev through INFRAMELD_TARGET.
Unset INFRAMELD_TARGET or pass --target local.
```

This is a proposed, unimplemented screen with mock names. `status` and relevant `diagnose` output expose safe effective context and its source: explicit input, the named supported variable or the scoped saved preference. Sanitize terminal control characters. Do not dump environment/store contents or present cached labels as freshly verified permissions.

Do not read `.env`, search parent directories for context files, install shell hooks or implicitly create a repository configuration file. Changing working directory alone never changes target. These four variables contain no passwords, incoming keys, human tokens or provider secrets. Deployment-container environment settings are a different surface. `local start/stop/status/diagnose` always concerns the one managed runtime, regardless of product context. Factory reset has its explicit whole-CLI scope, not an environment-selected remote deletion scope.

When login has no effective account, interactive login may ask for an alias before authentication. New aliases require verified identity/admission and visible confirmation. An existing alias cannot silently be rebound. Ordinary commands do not create aliases. Setup may compose login and remembering context only with visible agreement about each changed preference. A saved login is not proof of current server permission.

Required acceptance cases include every precedence combination, both project-form conflicts, explicit overrides of invalid lower-priority values, blank effective selectors, per-target/per-account defaults, wrong-target aliases rejected before credential disclosure, logged-out selection, failed project resolution preserving the previous ID, environment-overridden saves, no directory discovery, and context changes during admitted work. Use both human and JSON/noninteractive output. These are future tests, not evidence that the client exists.

<a id="target-discovery"></a>

<a id="register-a-target-from-one-public-server-url"></a>

### Register a target from one public server URL

Alice receives `https://api.dev.example.com` from her operator. The proposed command `inframeld target add dev --url https://api.dev.example.com` saves a validated connection, not authentication, a project selection or a working RAG pipeline. `dev` is only a local label. The operator configures API identity, Hydra issuer, official client and API audience. Alice should not reconstruct those settings manually.

1. Validate the explicit canonical public API URL and require verified HTTPS. A Studio page, arbitrary API route, model endpoint or private administrator URL is not the input. The managed local target instead obtains its settings from verified runtime state.
2. Read RFC 9728 resource metadata using the standard path derivation without any saved credentials, cookies, project selections or model/document data. Require the returned `resource` to match the supplied identity under the standard's comparison rules. Preserve URL path meaning.
3. Obtain the configured Hydra issuer from validated `authorization_servers`. Reject ambiguous or unsupported metadata rather than selecting an unrelated issuer. The canonical API URL is this profile's token audience. Public metadata is not authorization.
4. Validate the issuer's standard metadata with a maintained OAuth/OIDC library and exact issuer matching. Qualify the supported discovery path algorithm instead of mixing OAuth/OIDC variants through ad hoc URL concatenation. Keep the fixed `inframeld-cli`, scope, PKCE and audience contract. Discovery cannot enlarge it.
5. Save the non-secret target identity and API/issuer/client/audience binding only after all validation succeeds. Preserve prior targets, credentials and selections. A repeated label cannot overwrite an established identity or borrow old credentials merely because a URL matches.
6. Report registration separately. Interactive continuation may offer browser sign-in and project selection, each with its own completed/partial outcome. Noninteractive `--no-input --json` registers only the target and returns without prompts or browser launch.

Bound time, response size and parsing. Metadata/redirect destinations remain untrusted inputs requiring the specified destination policy. Reject HTTPS downgrade, mismatches and private administration exposure. Qualify redirects, DNS/proxy behavior and legitimate private/VPN deployments together. A public-cloud-only shortcut must not exclude supported private installations. Exact URL rules, metadata cache policy and bounds remain contracts, not permission to accept arbitrary network destinations.

Later metadata changes and authentication errors cannot silently replace a saved binding. Explicit reviewed reconfiguration invalidates affected logins and coordinates with pending login/refresh. Ordinary standard signing-key rotation is not a new issuer/audience and does not justify inventing permanent key pinning. No existing credential is sent to discover a proposed replacement.

Missing metadata, unavailable service, invalid certificate, resource/issuer mismatch and unsupported protocol configuration need distinct safe explanations. They are not password errors. Cancellation before saving leaves no target. Cancellation after a committed save reports that fact rather than rollback. A later login failure leaves the target. A later project-list failure leaves the saved login. No failure implicitly runs setup, copies data, publishes or calls a model. Project remembering still rechecks current access. Preference-persistence failures report confirmed versus incomplete effects without undoing unrelated concurrent choices.

Qualification covers malformed/oversized metadata, path comparisons, missing metadata on older installations, hostile redirects, public metadata without secrets, private-network operation, concurrent target/login changes, cancellation around persistence and noninteractive refusal to prompt. The discovery profile is first-party CLI only. It does not expand MCP OAuth or third-party client onboarding. Registration's successful validation is not proof that the subsequent OAuth login will succeed.

### Implemented discovery profile

[ADR-0098](../../../../docs/adr/ADR-0098-publish-bounded-first-party-discovery.md) accepts the first-party profile. The backend publishes anonymous RFC 9728 metadata with exact resource and issuer identifiers, the fixed API scope and header bearer transport. The inframeld extension requires schema_version 1, the persistent installation_id UUID and client_id inframeld-cli. Private administration addresses, credentials, permission records and release-compatibility claims are excluded. Explicit enabled configuration must match the Hydra audience. Unconfigured discovery returns safe unavailable metadata. Startup reads the original installation identity without creating a replacement.

Server-side public API and issuer configuration uses the infrastructure [Pydantic URL verifier](../../../../apps/backend/src/inframeld_backend/access/infrastructure/verifiers/pydantic_discovery_url_verifier.py), combining maintained authority validation with raw syntax checks and an 8,192-byte UTF-8 limit. Original identity strings remain unchanged. The configured-admin guard compares normalized scheme, hostname and effective port together with the path, preserving its trailing-slash equivalence without banning other paths on the same origin. Host aliases recognized by the parser cannot bypass this guard. Validation performs no DNS lookup. Managed-local admission still requires the original literal `http://127.0.0.1` authority rather than a normalized loopback alias.

The stateless [Rust discovery library](../../../../apps/cli/src/discovery/mod.rs) consumes generated API operations and maintained `openidconnect` metadata validation. It uses fresh credential-free transports, ten seconds overall, five per request and 64 KiB per response. Redirects and automatic retries are disabled. Returned metadata must preserve exact resource, issuer and fixed-client identity. Provider and key-set requests remain on the issuer origin. HTTPS supports private/VPN installations and explicit proxies. Proxy environment variables are not adopted implicitly. Managed-local discovery rejects explicit proxies before I/O. Provider compatibility requires authorization-code and refresh grants, the code response, public-client token authentication and S256. Omitted grant metadata uses the standard authorization-code/implicit default and therefore fails the refresh requirement.

The internal managed-local context is separate from returned metadata and has no public constructor or deserialization path. Its literal-loopback, exact-origin and installation checks have controlled tests. Actual managed-runtime creation remains #162. The generated path operation uses the [encoded relative path capability](../../../../packages/sdk-tools/docs/generators.md#encoded-relative-path-parameters), accepted through [ADR-0099](../../../../docs/adr/ADR-0099-preserve-encoded-relative-paths-in-generated-clients.md). It preserves literal separators and existing escapes instead of decoding the resource path before serialization. Discovery saves nothing and starts no login. Target persistence remains #159 and browser login remains #160. The [operator guide](../../../../docs/development/guides/server-discovery.md) and [verification report](../../../../docs/development/reports/server-discovery-verification.md) distinguish configuration, local evidence and pending release qualification.
