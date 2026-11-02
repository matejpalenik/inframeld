#!/usr/bin/env bash

# These fixed phase bodies run only as children of the retained Python owner.
capture_volume_inventory() {
    local destination="$1"
    "${account_runtime}" volume ls -q >"${destination}.raw" || return "$?"
    LC_ALL=C sort -u "${destination}.raw" >"${destination}.txt" || return "$?"
}

runtime_preflight() {
    "${account_runtime}" version || return "$?"
    capture_volume_inventory "${account_directory}/volumes-before"
}

wait_for_postgres() {
    # Only final TCP startup is ready. The image's temporary server is socket-only.
    until "${account_compose[@]}" exec -T "$1" pg_isready -h 127.0.0.1 -U "$2" -d "$3" >/dev/null 2>&1; do
        sleep 0.25 || return "$?"
    done
}

startup_stack() {
    # All descendants share the one startup phase group and its outer deadline.
    set +m
    local service
    for service in account-tls-init breach-tls-init; do
        "${account_compose[@]}" run --rm --no-deps -T "${service}" || return "$?"
    done
    "${account_compose[@]}" up -d --no-deps --no-build postgres kratos-postgres hydra-postgres mailpit password-breaches || return "$?"
    wait_for_postgres postgres account_test account_ui_test || return "$?"
    wait_for_postgres kratos-postgres kratos_test kratos_test || return "$?"
    wait_for_postgres hydra-postgres hydra_test hydra_test || return "$?"
    for service in hydra-migrate kratos-migrate migrate; do
        "${account_compose[@]}" run --rm --no-deps -T "${service}" || return "$?"
    done
    "${account_compose[@]}" up -d --no-deps --no-build hydra kratos || return "$?"
    for service in oauth-client-setup identity-setup seed; do
        "${account_compose[@]}" run --rm --no-deps -T "${service}" || return "$?"
    done
    "${account_compose[@]}" up -d --no-deps --no-build backend web gateway
}

cleanup_stack() {
    local result=0 remaining label kind image
    if ! "${account_compose[@]}" --profile qualification down --volumes --remove-orphans; then result=1; fi
    for label in com.docker.compose.project io.podman.compose.project; do
        for kind in container network volume; do
            remaining=""
            case "${kind}" in
                container) remaining="$("${account_runtime}" ps -aq --filter "label=${label}=${account_project}")" || result=1 ;;
                network) remaining="$("${account_runtime}" network ls -q --filter "label=${label}=${account_project}")" || result=1 ;;
                volume) remaining="$("${account_runtime}" volume ls -q --filter "label=${label}=${account_project}")" || result=1 ;;
            esac
            if [[ -n "${remaining}" ]]; then
                printf 'Owned account %s resources remain.\n' "${kind}" >&2
                result=1
            fi
        done
    done
    for image in "${INFRAMELD_ACCOUNT_BACKEND_IMAGE}" "${INFRAMELD_ACCOUNT_WEB_IMAGE}"; do
        remaining=""
        if ! remaining="$("${account_runtime}" image ls -q --filter "reference=${image}")"; then
            result=1
            continue
        fi
        if [[ -n "${remaining}" ]]; then
            "${account_runtime}" image rm "${image}" || result=1
            remaining=""
            if ! remaining="$("${account_runtime}" image ls -q --filter "reference=${image}")"; then result=1; fi
            if [[ -n "${remaining}" ]]; then result=1; fi
        fi
    done
    # The exclusive runtime lease makes this a conservative leak detector.
    # A difference never grants ownership or permission to delete global volumes.
    if ! capture_volume_inventory "${account_directory}/volumes-after"; then
        printf 'Final account volume inventory failed.\n' >&2
        result=1
    elif [[ "${volume_baseline_complete:-false}" != true ]]; then
        printf 'Account volume baseline did not complete successfully.\n' >&2
        result=1
    elif ! cmp -s "${account_directory}/volumes-before.txt" "${account_directory}/volumes-after.txt"; then
        LC_ALL=C comm -13 "${account_directory}/volumes-before.txt" "${account_directory}/volumes-after.txt" >"${account_directory}/volumes-added.txt" || result=1
        LC_ALL=C comm -23 "${account_directory}/volumes-before.txt" "${account_directory}/volumes-after.txt" >"${account_directory}/volumes-missing.txt" || result=1
        printf 'Account volume names differ from the baseline. Retained diagnostics require reconciliation.\n' >&2
        result=1
    fi
    return "${result}"
}

main() {
    local repository_root
    repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Python 3.13 is required for the private account qualification owner.\n' >&2
        exit 2
    fi
    exec python3 -B "${repository_root}/scripts/run_account_ui.py" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
