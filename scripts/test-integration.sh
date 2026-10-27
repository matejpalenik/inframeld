#!/usr/bin/env bash

set -euo pipefail
# Give each asynchronous step its own process group so cancellation also stops
# a build or Compose subprocess before project cleanup begins.
set -m

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${repository_root}"
active_pid=""

cleanup_test_services() {
    local exit_status=$?
    trap - EXIT
    trap '' INT TERM
    if ! "${script_dir}/dev-compose.sh" test-services-down; then
        printf 'Integration cleanup failed. Run ./scripts/dev-compose.sh test-services-down to retry.\n' >&2
        if [[ "${exit_status}" -eq 0 ]]; then
            exit_status=1
        fi
    fi
    exit "${exit_status}"
}

interrupt_run() {
    local exit_status="$1"
    trap '' INT TERM
    if [[ -n "${active_pid}" ]]; then
        kill -TERM -- "-${active_pid}" 2>/dev/null || true
        wait "${active_pid}" 2>/dev/null || true
    fi
    exit "${exit_status}"
}

run_step() {
    # These steps are noninteractive. With job control enabled, inheriting the
    # terminal lets Podman suspend the background job when it reads stdin.
    "$@" </dev/null &
    active_pid=$!
    local exit_status=0
    wait "${active_pid}" || exit_status=$?
    active_pid=""
    return "${exit_status}"
}

trap cleanup_test_services EXIT
trap 'interrupt_run 130' INT
trap 'interrupt_run 143' TERM

run_step "${script_dir}/dev-compose.sh" test-services-up
run_step "${script_dir}/dev-compose.sh" test-run "$@"
