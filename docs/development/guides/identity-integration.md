# Identity Integration

<a id="native-login-and-browser-consent"></a>

### Native login and browser consent

The backend now exposes [cookie-only consent inspection and decisions](../../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#human-oauth-consent). It allows verified Kratos identities before local admission, while product endpoints still require admission. New remembered approvals default to one hour. All current browser, requested-access and recovery checks still run when consent was remembered.

Consent first rejects unsupported client, scopes or audience with 403, before browser verification or credential-state initialization. Credential selection and POST CSRF still run first. Inspection and denial use read-only checks. Supported approval follows capture state, verify browser, reread state and approve with the captured binding. It never upgrades an old binding or automatically retries an uncertain approval.

For a separately provisioned runtime, configure Kratos `oauth2_provider.url` to Hydra's private admin base URL. Point Hydra `urls.login` to the public Kratos `/self-service/login/browser` endpoint and keep Kratos's login form URL on the account UI. Point Hydra `urls.consent` to the account UI's consent page, which calls the backend API. Keep consistent public hostnames/routing so the UI and backend receive the correct Kratos cookie. Do not expose admin APIs or disable CSRF to make routing work.

The private test Compose file and backend lockfile own exact provider and SDK pins. Consult the [runtime security qualification](../../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md#provider-image-and-upgrade-qualification) before production use. The test setup is not security clearance.

Its `oauth2.token_hook` is an instrumented test probe, not production configuration. The [Access observations](../../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#native-hydra-consent) distinguish current consent checks and provider race results from unfinished durable cleanup and safe recovery release. The development stack does not gain Hydra provisioning, and browser pages remain future work.

<a id="human-bearer-configuration"></a>

### Human bearer configuration

Alice's token and browser cookie must resolve to the same local account. The backend has verification adapters for both paths. The integration stack runs real Kratos and Hydra services to test that boundary. Native backend login/consent integration is described above. Development-stack Hydra provisioning and complete browser/CLI delivery remain unfinished.

Provider cleanup is a separate Access capability, not a local setup command. See [the recovery boundary](../../../.agents/skills/inframeld-access-models/references/recovery-provider-cleanup.md#standalone-provider-cleanup-boundary).

When configuring the backend for a separately provisioned identity runtime, these are the supported settings:

| Environment variable | Meaning |
| --- | --- |
| `INFRAMELD_KRATOS__ADMIN_URL` | Explicit private Kratos identity API endpoint, required when Hydra is configured. |
| `INFRAMELD_HYDRA__ADMIN_URL` | Private Hydra endpoint used for introspection and consent administration. |
| `INFRAMELD_HYDRA__PUBLIC_URL` | Explicit public base URL used to validate consent continuations. Without it, bearer verification can work but consent returns 503. |
| `INFRAMELD_HYDRA__REMEMBER_CONSENT_SECONDS` | Positive whole remember duration, default 3,600 seconds. Does not change token or login lifetimes. |
| `INFRAMELD_HYDRA__ISSUER` | Exact trusted Hydra issuer identifier. Do not derive it from an incoming token. |
| `INFRAMELD_HYDRA__API_AUDIENCE` | Exact API audience the token must contain. |
| `INFRAMELD_HYDRA__CLIENT_ID` | Fixed supported client `inframeld-cli`, also the default. |
| `INFRAMELD_HYDRA__REQUIRED_SCOPE` | Fixed supported scope `inframeld:api`, also the default. |

`ApplicationSettings` rejects Hydra configuration unless Kratos and its admin URL are also present. Choose endpoints and issuer/audience identifiers for the actual installation. Keep admin APIs private, including during development. These settings neither provision Hydra nor register the CLI client. [The deployment guide](../../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md#identity-runtime) owns those runtime requirements.

Both cookie and bearer authentication use deployment-configurable limits: `INFRAMELD_HUMAN_AUTHENTICATION__PROVIDER_TIMEOUT_SECONDS` defaults to five seconds and `INFRAMELD_HUMAN_AUTHENTICATION__TOTAL_TIMEOUT_SECONDS` defaults to ten. The total covers provider verification and the local principal lookup. A provider receives only the time still available within that total. See [the authentication budget contract](../../../.agents/skills/inframeld-access-models/references/session-contracts.md#session-checks) for timeout behavior and the remaining CLI request limit.

---

## Configure a company OIDC provider locally

To enable company OIDC locally, register `http://127.0.0.1:14434/self-service/methods/oidc/callback/company` as the provider's redirect URI. Copy the development config to a private file, which Git ignores:

```bash
cp config/kratos/dev.yaml config/kratos/dev.local.yaml
```

In `dev.local.yaml`, add this block under the existing `selfservice.methods` key, using your provider's values:

<!-- prettier-ignore -->
```yaml
    oidc:
      enabled: true
      config:
        providers:
          - id: company
            provider: generic
            client_id: YOUR_CLIENT_ID
            client_secret: YOUR_CLIENT_SECRET
            issuer_url: https://YOUR_PROVIDER_ISSUER
            mapper_url: file:///etc/config/kratos/oidc.email.jsonnet
            claims_source: id_token
            scope:
              - openid
              - email
```

Under the existing `selfservice.flows.registration.after` key in that same file, add the OIDC session hook:

<!-- prettier-ignore -->
```yaml
        oidc:
          hooks:
            - hook: session
```

The same settings are in [`oidc.example.yaml`](../../../config/kratos/oidc.example.yaml). Finally, under `kratos` in `compose.dev.yaml`, comment out the default `command` and uncomment the `dev.local.yaml` command, then restart the services:

```bash
pnpm dev:db:down
pnpm dev:db
```
