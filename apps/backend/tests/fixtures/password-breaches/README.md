# Password-breach fixture TLS

The private integration stack generates fresh TLS credentials automatically. No certificate or private key is checked in, supplied through CI secrets or installed in the host trust store.

Kratos calls `https://password-breaches:8443/range/{prefix}`. All test Kratos variants and explicit fixture clients trust that stack's generated CA. Certificate and hostname verification remain enabled. The fixture returns a single breach for the public test password defined in `tests/support/password_breaches.py`. Other passwords have no listed breaches. Precomputed public vectors avoid password hashing in test support. Native Kratos tests independently verify the HIBP protocol meaning. Observations retain only five-character SHA-1 prefixes and counts.

## Automatic lifecycle

`pnpm test:integration` uses the same startup and cleanup path locally and in CI:

1. Remove stale test containers, networks and the two labelled TLS volumes. Preserve named database volumes.
2. Build or select the locked integration image, including the development-only `trustme` dependency.
3. Run `test-tls-init` without network access. Container root prepares volume ownership, then drops supplementary groups and switches to UID/GID `10001` before generating keys.
4. Generate a fresh CA and a server certificate for exactly `password-breaches`. The server certificate is valid from five minutes before generation until 24 hours after generation. The CA signing key stays in process memory and is never exported.
5. Start the fixture and providers. The runner requires verified HTTPS readiness within its existing startup deadline before executing tests.
6. Stop consumers, then delete only the TLS volumes. Failure and cancellation use the same cleanup. Startup recovers leftovers from abrupt termination.

| Volume | Contents | Consumers |
| --- | --- | --- |
| `inframeld_test_tls_trust` | Public `ca.pem` and `server-not-after.txt` expiry metadata | Kratos variants and test runner, read-only |
| `inframeld_test_tls_identity` | `server.pem` and `server.key` | Breach fixture only, read-only |

Both volumes have `org.inframeld.test-project=inframeld-test` and `org.inframeld.disposable-tls=true` labels. Cleanup requires the exact expected names and matching labels. A label mismatch fails visibly instead of deleting an unowned volume. Named database volumes survive.

Consumers read certificates under `/run/inframeld-test-tls/`. The trust directory has mode `0755`, the identity directory `0700`, public certificates `0644` and the private key `0600`. The initializer rejects non-empty output directories and never falls back to old credentials. Runtime consumers remain non-root.

Repeated `./scripts/dev-compose.sh test-run` commands reuse the running stack's certificates. To renew an expired certificate, stop and restart the stack. There is no rotation while consumers are running. The runner rejects expired or incomplete expiry metadata before waiting for services, with exact restart instructions. Shared paths belong to `tests/support/integration_services.py`, so clients do not depend on the issuer module.

Run one local integration operation at a time. Overlapping commands are unsupported. Manual stacks are explicitly started and stopped, without worktree ownership or reservations. See the [serial integration workflow](../../../../../docs/development/guides/testing.md#serial-integration-workflow) for cancellation, cleanup and CI behavior.

These temporary volumes may contain files on the container host's disk until deletion. Cleanup does not promise secure erasure. Generated material must not enter image layers, caches, logs or CI artifacts.

## Verify or recover

Run native password acceptance, rejection and explicit-trust checks:

```bash
pnpm test:integration tests/integration/kratos/test_password_breach_lookup.py
```

If cleanup was interrupted, retry it with:

```bash
./scripts/dev-compose.sh test-services-down
```

Do not use a broad volume prune or disable TLS verification to repair startup.
