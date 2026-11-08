# Inframeld account UI

In the intended combined journey, an existing human starts sign-in from the Inframeld CLI, completes native Kratos password or email-code login, checks the account subject and installation on the consent page, then returns to the CLI for its result. This increment supplies the account pages. The public CLI sign-in command and qualification of the client handoff remain separate work. The backend owns consent, identity currentness and permissions. The browser never receives the CLI tokens or maintenance proof payload.

This standalone account application is independent of Studio. Kratos owns identity registration, verification, login, recovery and security settings. The delivered Access APIs own admission and invitations. The UI renders native fields and errors, with finite configured TOTP, backup-code and OIDC support. Unsupported scripted provider interactions stop instead of dropping a required factor or claiming universal passkey support. The current twenty-case local native profile and its independent SQL verification have passed, including the literal invitation guide's preview, activation and original-recovery modes. Invitation identity-switch coverage explicitly dispatches the focus handler with real cookies and does not establish OS focus-event delivery. Packaged ingress, saved CLI accounts, bootstrap and private starters remain separate consumers.

## Routes and requests

- `/login` starts a native Kratos browser flow or renders its checked flow ID. Native forms preserve CSRF, method, constraints and provider messages, with separate password and code forms.
- `/registration`, `/verification`, `/recovery` and `/settings` render their exact native browser flows. Profile-first registration, password settings, configured factor enrollment and native errors remain provider-owned. Successful settings may resolve one exact same-identity official successor under the original read budget, preserving the original completion message without rewriting native actions.
- `/invitations` explicitly previews intended scope or recovers an exact original activation through the generated application client. Preview needs a verified browser identity, not existing local admission. New activation is a separate decision. Manual recovery restores the saved identity, token and key and sends the original request before fresh preview. Neither a preview nor password persistence grants access by itself.
- `/consent` inspects the current request through the generated `@inframeld/sdk`. Allow and cancel are explicit actions. Remember approval starts unchecked. Browser writes send real cookies, the real browser Origin and `X-Inframeld-CSRF: 1`.
- `/logout` prepares a native logout link. The user must activate it. Browser logout does not promise revocation of CLI credentials.
- `/error` gives a safe stopping point without reflecting provider errors or untrusted return URLs.
- `/` separately checks the current native identity and ordinary product access. A generic product denial does not diagnose recovery or admission, and the page never claims that CLI sign-in succeeded.

Consent rechecks identity after focus or restored-page navigation and removes stale account details. A lost decision response stays unknown and cannot be automatically submitted again. Restart from the requesting client if the page cannot confirm its result.

Invitation focus/restoration only rereads identity. It never activates or recovers automatically. Blur hides protected details and aborts the UI wait. A dispatched activation can remain uncertain, so its identity-bound original context stays in page memory until an explicit discard, observed identity mismatch or reload. It is not persisted in browser storage. Cancellation does not prove rollback. The user must preserve the original request privately and explicitly restore it under the same identity after reload. The [account guide](../docs/src/app/guides/account-and-consent/page.mdx) and [invitation guide](../docs/src/app/guides/manage-invitations/page.mdx) describe those tasks.

The earlier fourteen-case native component qualification covers existing-human password/code login, explicit logout, Allow/Cancel through Hydra, revoked-cookie refusal, profile-first registration, verification, password settings, configured TOTP/backup-code challenges and cross-site OIDC. It does not qualify the expanded recovery/invitation/guide fixture or OIDC settings. A test-only in-process Node receiver on literal `127.0.0.1` with an ephemeral port receives the actual registered callback without retaining a PKCE verifier or exchanging the code. It is not a proof consumer. This does not qualify an OS browser or packaged ingress. The [shared repair-only transient acquisition capability and source-built examples](../../docs/development/guides/recipient-proof.md) have selected native-driver coverage in the [verification report](../../docs/development/reports/recipient-proof-verification.md). Full #160 and the complete sign-in/repair acceptance under [#298](https://github.com/matejpalenik/inframeld/issues/298) remain separate. Account and invitation human acceptance remain unperformed under [#371](https://github.com/matejpalenik/inframeld/issues/371) and [#357](https://github.com/matejpalenik/inframeld/issues/357).

The official `@ory/client-fetch` frontend client owns native provider reads. Server calls use fixed private upstreams and forward only the current request's cookie. The generated Inframeld client owns application API calls. No handwritten application API client or Hydra administration is part of the browser app.

## HTTPS reference profile

The HTTPS reference profile has two fixed origins:

| Origin                                | Public routes                                           |
| ------------------------------------- | ------------------------------------------------------- |
| `https://inframeld.account.test:8443` | Account UI, Kratos public browser routes, Inframeld API |
| `https://hydra.account.test:8443/`    | Hydra public OAuth/OIDC endpoints                       |

A single TLS gateway forwards native cookies, Origin, CSRF and redirects without translating their paths or manufacturing identity claims. Kratos and Hydra administration stay private. The API audience and public API identity equal the account origin without a trailing slash. The issuer includes its trailing slash.

[`.env.example`](.env.example) lists the server-only UI settings. Internal provider/API addresses are not public component props. The optional `INFRAMELD_ACCOUNT_OIDC_FORM_ACTION_ORIGINS` is a JSON array, default `[]`, with at most eight canonical HTTPS origins and 4096 UTF-8 bytes. Configure the actual upstream browser authorization/navigation origins, which may differ from the issuer. An invalid list is rejected in full and the account UI stops safely. The list extends only CSP `form-action`, preserving exact native action checks and other directives. It is not provider discovery trust or an allowance for browser-supplied origins. This profile uses gateway forwarding, without a duplicate Next.js API proxy.

The current default HTTP development ports are **not supported for the final recipient-proof producer**. They do not qualify Rust HTTPS discovery. They remain unchanged. Running `pnpm --filter @inframeld/web dev` at `http://localhost:3000` can develop the app, but does not establish a supported CLI sign-in journey.

The separate [qualification fixture](tests/fixtures/README.md) requires host Bash, the repository's pinned Python 3.13 environment and an available container engine with Compose. The host must provide POSIX `waitid` with `WNOWAIT`, process-group signalling and `ps`. The repository pins Python 3.13.12. Its standard-library [account lifecycle owner](../../scripts/run_account_ui.py) retains each phase leader until group signalling ends, then releases that process identity. A recorded PID is diagnostic information, not later cleanup authority. It stages a disposable web/SDK source context and supplies private DNS routing and a fresh private CA without host DNS/trust changes, published ports, insecure TLS flags or a fabricated managed-local context. The wrapper requires a successful runtime volume-name baseline before build/startup and an exact final name-set match before confirming cleanup. The covered native browser/provider navigation cases and cleanup passed in this pinned private profile. The [verification report](../../docs/development/reports/recipient-proof-verification.md) distinguishes selected native-driver coverage from remaining operator/system-browser qualification. Packaged ingress #95 and human acceptance remain separate.

Existing-human navigation startup and retries go through `scripts/test-account-ui.sh --login-only` from the repository root. The same wrapper has a closed `--recipient-proof` profile for the source-built shared Rust examples, with selected native-driver coverage recorded in the [verification report](../../docs/development/reports/recipient-proof-verification.md). The wrapper owns the explicit dependency order, runs fresh TLS initializers once, and requires TCP database readiness before migrations under one 180-second startup budget. Runtime web, identity and browser commands use installed Node/package entry points without invoking pnpm. After a failed run, complete cleanup and reconciliation before a fresh wrapper invocation. The [fixture instructions](tests/fixtures/README.md) describe those gates and recovery.

## Browser privacy

Native session and CSRF cookies are necessary browser state. Login, consent and callback URLs necessarily contain flow IDs, challenges, state or authorization codes. Browsers may retain those URLs in history or session restoration. Do not copy them into logs, tickets, traces or screenshots.

The account application does not persist OAuth credentials, PKCE verifiers, maintenance proof payloads, invitation tokens or original activation context in web storage, IndexedDB, caches or service workers. Invitation tokens never enter URLs. Native enrollment secrets and backup codes are intentional current-flow UI output, with no logging or storage. Account responses use `no-store` and `no-referrer`. These controls reduce exposure and do not erase browser history. Static compiled assets retain Next.js immutable caching and contain no per-request flow data.

## Private checks

From the repository root, using the pinned toolchain. The web `dev`, `build`, `typecheck` and `test` commands build the committed TypeScript SDK before consuming its output:

```bash
mise exec -- pnpm install --frozen-lockfile
mise exec -- pnpm --filter @inframeld/web test
mise exec -- pnpm --filter @inframeld/web lint
mise exec -- pnpm --filter @inframeld/web format:check
mise exec -- pnpm --filter @inframeld/web typecheck
mise exec -- pnpm --filter @inframeld/web build
```

Unit tests exercise native form rendering, official/generated HTTP contracts, consent races and safe uncertain outcomes. Harness lifecycle tests use private process substitutes for startup ordering, readiness, failure propagation and retained process ownership. The existing web test command also invokes the standard-library Python ownership regressions. Controlled cases cover early leader exit with surviving descendants, cancellation, lost ownership, bounded observation and once-only finalization. These checks do not establish native provider, PostgreSQL or full browser-navigation guarantees. Type checking retains the repository's TypeScript 7 `@typescript/native` alias and TypeScript 6 compatibility alias.

The session test oracle treats only an official unauthenticated `401` as absence of a session. Provider `503`, TLS, transport and timeout failures fail qualification. A controlled expired-session `401` exercises UI detail removal. The native revoked-session case passed after restoring a cookie following actual logout/revocation and requiring consent refusal without a decision. It does not prove natural session expiry or switching to a second account.

See the accepted [human CLI consent workflow](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md) for the backend-owned contract.
