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
    for image in "${INFRAMELD_ACCOUNT_PROOF_IMAGE}" "${INFRAMELD_ACCOUNT_WEB_IMAGE}" "${INFRAMELD_ACCOUNT_BACKEND_IMAGE}"; do
        remaining=""
        if ! remaining="$("${account_runtime}" image ls -q --filter "reference=${image}")"; then
            result=1
            continue
        fi
        if [[ -n "${remaining}" ]]; then
            "${account_runtime}" image rm --no-prune "${image}" || result=1
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

prepare_contexts() {
    "${account_python}" "${account_root}/apps/web/tests/fixtures/prepare_build_context.py" \
        "${account_root}" "${account_directory}/web-context" || return "$?"
    "${account_python}" "${account_root}/apps/web/tests/fixtures/prepare_build_context.py" \
        "${account_root}" "${account_directory}/proof-context" --recipient-proof
}

build_stack() {
    # Both source builds share the original 600-second phase, including Cargo.
    "${account_compose[@]}" build backend web || return "$?"
    "${account_compose[@]}" --profile qualification build proof-driver
}

account_container_state() {
    # Convert one bounded inspect object to closed lifecycle facts without logging it.
    "${account_python}" -c '
import json, re, sys
raw = sys.stdin.buffer.read(65537)
if len(raw) > 65536: raise SystemExit(1)
data = json.loads(raw)
project, identity, service, browser = sys.argv[1:]
if not re.fullmatch("[0-9a-f]{64}", identity) or data.get("Id") != identity: raise SystemExit(1)
config, host, state = data["Config"], data["HostConfig"], data["State"]
labels = config["Labels"]
for suffix, expected in (("project", project), ("service", service)):
    observed = [labels[key] for key in ("com.docker.compose." + suffix, "io.podman.compose." + suffix) if key in labels]
    if not observed or any(value != expected for value in observed): raise SystemExit(1)
if config.get("User") != "10001:10001" or host.get("Privileged") is not False: raise SystemExit(1)
if host.get("Init") is not True or host.get("PidMode") not in ("", "private"): raise SystemExit(1)
if service in ("proof-driver", "proof-denied-driver") and host.get("NetworkMode") != "container:" + browser: raise SystemExit(1)
status, code = state.get("Status"), state.get("ExitCode")
health = state.get("Health", {}).get("Status", "absent")
if status not in ("created", "running", "exited", "dead") or type(code) is not int or not 0 <= code <= 255: raise SystemExit(1)
if health not in ("starting", "healthy", "unhealthy", "absent"): raise SystemExit(1)
print(status, code, health)
' "${account_project}" "$1" "$2" "$3"
}

account_service_container_id() {
    local service="$1" label observed identities=""
    for label in io.podman.compose.project com.docker.compose.project; do
        observed="$("${account_runtime}" ps -aq --no-trunc \
            --filter "label=${label}=${account_project}" \
            --filter "label=com.docker.compose.service=${service}")" || return "$?"
        identities+=$'\n'"${observed}"
    done
    observed="$(printf '%s\n' "${identities}" | LC_ALL=C sort -u | sed '/^$/d')" || return "$?"
    [[ "${observed}" =~ ^[0-9a-f]{64}$ ]] || return 1
    printf '%s\n' "${observed}"
}

recipient_proof_stack() {
    local browser_id denied_id driver_id snapshot browser_state browser_code health driver_state driver_code readiness
    # One original 300-second phase owns both explicit attempts and all three containers.
    "${account_compose[@]}" --profile qualification up -d --no-deps --no-build browser-tests || return "$?"
    browser_id="$(account_service_container_id browser-tests)" || return "$?"
    [[ "${browser_id}" =~ ^[0-9a-f]{64}$ ]] || return 1
    while true; do
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${browser_id}" |
            account_container_state "${browser_id}" browser-tests "${browser_id}")" || return 1
        read -r browser_state browser_code health <<<"${snapshot}"
        [[ "${browser_state}" == running && "${health}" != unhealthy ]] || return 1
        if [[ "${health}" == healthy ]]; then break; fi
        sleep 0.05 || return "$?"
    done
    "${account_compose[@]}" --profile qualification up -d --no-deps --no-build proof-denied-driver || return "$?"
    denied_id="$(account_service_container_id proof-denied-driver)" || return "$?"
    [[ "${denied_id}" =~ ^[0-9a-f]{64}$ && "${denied_id}" != "${browser_id}" ]] || return 1
    while true; do
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${denied_id}" |
            account_container_state "${denied_id}" proof-denied-driver "${browser_id}")" || return 1
        read -r driver_state driver_code health <<<"${snapshot}"
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${browser_id}" |
            account_container_state "${browser_id}" browser-tests "${browser_id}")" || return 1
        read -r browser_state browser_code health <<<"${snapshot}"
        [[ "${browser_state}" == running && "${driver_state}" != dead ]] || return 1
        if [[ "${driver_state}" == exited ]]; then
            [[ "${driver_code}" == 1 ]] || return 1
            break
        fi
        sleep 0.05 || return "$?"
    done
    # Exit1 alone is insufficient. The typed denial and independent no-effect read must both pass.
    "${account_runtime}" logs "${denied_id}" 2>&1 |
        "${account_compose[@]}" exec -T backend python /fixture/backend.py verify-denied-result || return "$?"
    while true; do
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${browser_id}" |
            account_container_state "${browser_id}" browser-tests "${browser_id}")" || return 1
        read -r browser_state browser_code health <<<"${snapshot}"
        [[ "${browser_state}" == running ]] || return 1
        readiness=0
        "${account_compose[@]}" --profile qualification exec -T browser-tests node -e '
const fs = require("node:fs");
try { if (!fs.lstatSync("/run/account-proof/allow-ready").isFile()) process.exit(1); }
catch (error) { process.exit(error.code === "ENOENT" ? 10 : 1); }
' || readiness="$?"
        case "${readiness}" in
            0) break ;;
            10) sleep 0.05 || return "$?" ;;
            *) return "${readiness}" ;;
        esac
    done
    "${account_compose[@]}" --profile qualification up -d --no-deps --no-build proof-driver || return "$?"
    driver_id="$(account_service_container_id proof-driver)" || return "$?"
    [[ "${driver_id}" =~ ^[0-9a-f]{64}$ && "${driver_id}" != "${browser_id}" && "${driver_id}" != "${denied_id}" ]] || return 1
    while true; do
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${driver_id}" |
            account_container_state "${driver_id}" proof-driver "${browser_id}")" || return 1
        read -r driver_state driver_code health <<<"${snapshot}"
        if [[ "${driver_state}" == dead ]]; then return 1; fi
        if [[ "${driver_state}" == exited && "${driver_code}" != 0 ]]; then return "${driver_code}"; fi
        snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${browser_id}" |
            account_container_state "${browser_id}" browser-tests "${browser_id}")" || return 1
        read -r browser_state browser_code health <<<"${snapshot}"
        if [[ "${browser_state}" == dead ]]; then return 1; fi
        if [[ "${browser_state}" == exited && "${browser_code}" != 0 ]]; then return "${browser_code}"; fi
        if [[ "${driver_state}" == exited && "${browser_state}" == exited ]]; then break; fi
        sleep 0.05 || return "$?"
    done
    snapshot="$("${account_runtime}" inspect --format '{{json .}}' "${denied_id}" |
        account_container_state "${denied_id}" proof-denied-driver "${browser_id}")" || return 1
    read -r driver_state driver_code health <<<"${snapshot}"
    [[ "${driver_state}" == exited && "${driver_code}" == 1 ]] || return 1
    "${account_runtime}" logs "${driver_id}" 2>&1 |
        "${account_compose[@]}" exec -T backend python /fixture/backend.py verify-proof-result
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
