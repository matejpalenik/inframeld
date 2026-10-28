#!/usr/bin/env bash

cleanup_test_services() {
    local exit_status=$?
    trap - EXIT
    trap '' INT TERM
    if ! stop_active_step && [[ "${exit_status}" -eq 0 ]]; then
        exit_status=1
    fi
    if ! run_cleanup "${1:-60}"; then
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
    stop_active_step || true
    exit "${exit_status}"
}

wait_for_step_group() {
    local group="$1"
    local deadline=$((SECONDS + 5))
    while kill -0 -- "-${group}" 2>/dev/null; do
        if ((SECONDS >= deadline)); then
            return 1
        fi
        sleep 0.1
    done
}

stop_active_step() {
    [[ -n "${active_pid:-}" ]] || return 0
    local group="${active_pid}"
    active_pid=""
    kill -TERM -- "-${group}" 2>/dev/null || true
    if ! wait_for_step_group "${group}"; then
        kill -KILL -- "-${group}" 2>/dev/null || true
        if ! wait_for_step_group "${group}"; then
            printf 'Integration process group %s survived TERM and KILL.\n' "${group}" >&2
            if ! kill -0 "${group}" 2>/dev/null; then
                wait "${group}" 2>/dev/null || true
            fi
            return 1
        fi
    fi
    wait "${group}" 2>/dev/null || true
}

run_step() {
    # These steps are noninteractive. With job control enabled, inheriting the
    # terminal lets Podman suspend the background job when it reads stdin.
    "$@" </dev/null &
    active_pid=$!
    local exit_status=0
    wait "${active_pid}" || exit_status=$?
    if ! stop_active_step && [[ "${exit_status}" -eq 0 ]]; then
        exit_status=1
    fi
    return "${exit_status}"
}

run_cleanup() {
    local work_budget="$1"
    # Only the parent shields finalization. Keep driver descendants in this
    # group and restore their ability to respond to termination signals.
    (
        trap - EXIT INT TERM
        set +m
        cleanup_stack
    ) </dev/null &
    active_pid=$!
    local deadline=$((SECONDS + work_budget))
    local exit_status=0
    while kill -0 "${active_pid}" 2>/dev/null; do
        if ((SECONDS >= deadline)); then
            printf 'Integration cleanup exceeded its %s-second work budget. Cleanup may be incomplete.\n' "${work_budget}" >&2
            stop_active_step || true
            return 1
        fi
        sleep 0.1
    done
    wait "${active_pid}" || exit_status=$?
    if ! stop_active_step && [[ "${exit_status}" -eq 0 ]]; then
        exit_status=1
    fi
    return "${exit_status}"
}

cleanup_stack() {
    "${script_dir}/dev-compose.sh" test-services-down
}

main() {
    set -euo pipefail
    # Each noninteractive phase owns a process group for cancellation.
    set -m
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    repository_root="$(cd -- "${script_dir}/.." && pwd)"
    cd "${repository_root}"
    active_pid=""
    trap 'cleanup_test_services 60' EXIT
    trap 'interrupt_run 130' INT
    trap 'interrupt_run 143' TERM
    run_step "${script_dir}/dev-compose.sh" test-services-up
    run_step "${script_dir}/dev-compose.sh" test-run "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
