# Inframeld account UI

In the intended combined journey, an existing human starts sign-in from the Inframeld CLI, completes native Kratos password or email-code login, checks the account subject and installation on the consent page, then returns to the CLI for its result. This increment supplies the account pages. The public CLI sign-in command and qualification of the client handoff remain separate work. The backend owns consent, identity currentness and permissions. The browser never receives the CLI tokens or maintenance proof payload.

This is a bounded supporting increment for #82. It does not complete #82 or its #119 prerequisite. Account creation, verification, admission, invitations, recovery, account settings, configured MFA/OIDC and Studio remain outside this increment. Unsupported provider interactions stop instead of dropping a required factor.

## Routes and requests

- `/login` starts a native Kratos browser flow or renders its checked flow ID. Native forms preserve CSRF, method, constraints and provider messages, with separate password and code forms.
- `/consent` inspects the current request through the generated `@inframeld/sdk`. Allow and cancel are explicit actions. Remember approval starts unchecked. Browser writes send real cookies, the real browser Origin and `X-Inframeld-CSRF: 1`.
- `/logout` prepares a native logout link. The user must activate it. Browser logout does not promise revocation of CLI credentials.
- `/error` gives a safe stopping point without reflecting provider errors or untrusted return URLs.
- `/` is a neutral account landing page and never claims that CLI sign-in succeeded.

Consent rechecks identity after focus or restored-page navigation and removes stale account details. A lost decision response stays unknown and cannot be automatically submitted again. Restart from the requesting client if the page cannot confirm its result.

All eleven maintained native navigation cases passed in the pinned private-container/Chromium profile, with no failures, skips or cancellations. They cover existing-human password and email-code login, explicit browser logout, real UI Allow/Cancel navigation through Hydra and strict revoked-cookie `401` refusal. A test-only in-process Node receiver on literal `127.0.0.1` with an ephemeral port receives the actual registered callback. It observes navigation without retaining a PKCE verifier or exchanging an authorization code for tokens. It is not a proof consumer. This result does not qualify an OS browser or packaged ingress. The transient official-client acquisition capability and full #160 remain unfinished, and the complete human sign-in and protected-repair acceptance remains [#298](https://github.com/matejpalenik/inframeld/issues/298).

The official `@ory/client-fetch` frontend client owns native provider reads. Server calls use fixed private upstreams and forward only the current request's cookie. The generated Inframeld client owns application API calls. No handwritten application API client or Hydra administration is part of the browser app.

## HTTPS reference profile

The HTTPS reference profile has two fixed origins:

| Origin                                | Public routes                                           |
| ------------------------------------- | ------------------------------------------------------- |
| `https://inframeld.account.test:8443` | Account UI, Kratos public browser routes, Inframeld API |
| `https://hydra.account.test:8443/`    | Hydra public OAuth/OIDC endpoints                       |

A single TLS gateway forwards native cookies, Origin, CSRF and redirects without translating their paths or manufacturing identity claims. Kratos and Hydra administration stay private. The API audience and public API identity equal the account origin without a trailing slash. The issuer includes its trailing slash.

[`.env.example`](.env.example) lists the four server-only UI settings. Internal provider/API addresses are not public component props. This profile uses gateway forwarding, without a duplicate Next.js API proxy.

The current default HTTP development ports are **not supported for the final recipient-proof producer**. They do not qualify Rust HTTPS discovery. They remain unchanged. Running `pnpm --filter @inframeld/web dev` at `http://localhost:3000` can develop the app, but does not establish a supported CLI sign-in journey.

The separate [qualification fixture](tests/fixtures/README.md) requires host Bash, the repository's pinned Python 3.13 environment and an available container engine with Compose. The host must provide POSIX `waitid` with `WNOWAIT`, process-group signalling and `ps`. The repository pins Python 3.13.12. Its standard-library [account lifecycle owner](../../scripts/run_account_ui.py) retains each phase leader until group signalling ends, then releases that process identity. A recorded PID is diagnostic information, not later cleanup authority. It stages a disposable web/SDK source context and supplies private DNS routing and a fresh private CA without host DNS/trust changes, published ports, insecure TLS flags or a fabricated managed-local context. The wrapper requires a successful runtime volume-name baseline before build/startup and an exact final name-set match before confirming cleanup. The covered native browser/provider navigation cases and cleanup passed in this pinned private profile. Combined Rust recipient-proof qualification, packaged ingress #95 and human acceptance remain separate.

Fixture startup and retries go through `scripts/test-account-ui.sh --login-only` from the repository root. The wrapper owns the explicit dependency order, runs fresh TLS initializers once, and requires TCP database readiness before migrations under one 180-second startup budget. Runtime web, identity and browser commands use installed Node/package entry points without invoking pnpm. After a failed run, complete cleanup and reconciliation before a fresh wrapper invocation. The [fixture instructions](tests/fixtures/README.md) describe those gates and recovery.

## Browser privacy

Native session and CSRF cookies are necessary browser state. Login, consent and callback URLs necessarily contain flow IDs, challenges, state or authorization codes. Browsers may retain those URLs in history or session restoration. Do not copy them into logs, tickets, traces or screenshots.

The account application does not persist OAuth access/refresh/ID tokens, PKCE verifiers or maintenance proof payloads in web storage, IndexedDB, caches or service workers. Account responses use `no-store` and `no-referrer`. These controls reduce exposure and do not erase browser history. Static compiled assets can retain Next.js immutable caching and contain no per-request flow data.

## Private checks

From the repository root, using the pinned toolchain:

```bash
mise exec -- pnpm install --frozen-lockfile
mise exec -- pnpm --filter @inframeld/sdk build
mise exec -- pnpm --filter @inframeld/web test
mise exec -- pnpm --filter @inframeld/web lint
mise exec -- pnpm --filter @inframeld/web format:check
mise exec -- pnpm --filter @inframeld/web typecheck
mise exec -- pnpm --filter @inframeld/web build
```

Unit tests exercise native form rendering, official/generated HTTP contracts, consent races and safe uncertain outcomes. Harness lifecycle tests use private process substitutes for startup ordering, readiness, failure propagation and retained process ownership. The existing web test command also invokes the standard-library Python ownership regressions. Controlled cases cover early leader exit with surviving descendants, cancellation, lost ownership, bounded observation and once-only finalization. These checks do not establish native provider, PostgreSQL or full browser-navigation guarantees. Type checking retains the repository's TypeScript 7 `@typescript/native` alias and TypeScript 6 compatibility alias.

The session test oracle treats only an official unauthenticated `401` as absence of a session. Provider `503`, TLS, transport and timeout failures fail qualification. A controlled expired-session `401` exercises UI detail removal. The native revoked-session case passed after restoring a cookie following actual logout/revocation and requiring consent refusal without a decision. It does not prove natural session expiry or switching to a second account.

See the accepted [human CLI consent workflow](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md) for the backend-owned contract.
