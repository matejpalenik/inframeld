#!/usr/bin/env bash
set -euo pipefail
umask 077
# Trust only in this disposable container user's NSS database. Never alter host trust.
# Playwright 1.64.1 pins Chromium 156. M146+ defaults to this path.
account_nss="${HOME}/.local/share/pki/nssdb"
for database in "${HOME}/.pki/nssdb" "${account_nss}"; do
    if [[ -e "${database}" || -L "${database}" ]]; then
        printf 'Unexpected existing browser trust database.\n' >&2
        exit 1
    fi
done
if [[ -n "${XDG_DATA_HOME:-}" && "${XDG_DATA_HOME}" != "${HOME}/.local/share" ]]; then
    printf 'Unexpected browser trust location.\n' >&2
    exit 1
fi
# This disposable runner has no interactive input, including NSS password answers.
exec </dev/null
mkdir -p "${account_nss}"
certutil -N -d "sql:${account_nss}" --empty-password
printf 'Fresh browser trust database initialized.\n'
export NODE_EXTRA_CA_CERTS=/run/account-trust/ca.pem
node --import tsx tests/fixtures/check-untrusted.ts
printf 'Untrusted browser certificate check completed.\n'
certutil -A -d "sql:${account_nss}" -n account-ui-fixture -t 'C,,' -i /run/account-trust/ca.pem
certutil -L -d "sql:${account_nss}" -n account-ui-fixture >/dev/null
printf 'Fixture certificate import and readback completed.\n'
if [[ "${INFRAMELD_ACCOUNT_PROOF_MODE:-0}" == bootstrap ]]; then
    exec node --import tsx --test --test-concurrency=1 tests/browser/native-bootstrap-proof.test.ts
fi
if [[ "${INFRAMELD_ACCOUNT_PROOF_MODE:-0}" == 1 ]]; then
    exec node --import tsx --test --test-concurrency=1 \
        --test-name-pattern '^recipient-proof ' tests/browser/native-hydra-login-consent.test.ts
fi
exec node --import tsx --test --test-concurrency=1 tests/browser/*.test.ts
