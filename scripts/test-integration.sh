#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/.." && pwd)"
test_env_file="${repository_root}/apps/backend/.env.test"
cd "${repository_root}"

if [[ ! -f "${test_env_file}" ]]; then
    printf 'Backend test configuration is missing: %s\n' "${test_env_file}" >&2
    printf 'Create it with: cp apps/backend/.env.test.example apps/backend/.env.test\n' >&2
    exit 1
fi

cleanup_test_services() {
    local exit_status=$?
    trap - EXIT
    "${script_dir}/dev-compose.sh" test-services-down || true
    exit "${exit_status}"
}

trap cleanup_test_services EXIT

"${script_dir}/dev-compose.sh" test-services-up

# These values deliberately select the application PostgreSQL service in the
# test-only Compose project. Environment variables override .env.test.
export INFRAMELD_ENVIRONMENT=test
export INFRAMELD_TEST_ENV_FILE=.env.test
export INFRAMELD_DATABASE__HOST=127.0.0.1
export INFRAMELD_DATABASE__PORT=15433
export INFRAMELD_DATABASE__NAME=inframeld_test
export INFRAMELD_DATABASE__USER=inframeld_test
export INFRAMELD_DATABASE__PASSWORD=inframeld-test-only
export UV_LOCKED=1

pnpm --filter @inframeld/backend migrate
INFRAMELD_RUN_DB_INTEGRATION=1 INFRAMELD_RUN_KRATOS_INTEGRATION=1 \
    uv run --project apps/backend pytest apps/backend/tests/integration -q
