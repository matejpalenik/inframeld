#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/.." && pwd)"
compose_file="${repository_root}/compose.dev.yaml"
test_compose_file="${repository_root}/compose.test.yaml"

usage() {
    cat <<'EOF'
Usage: ./scripts/dev-compose.sh <command>

Commands:
  up           Start PostgreSQL and Kratos in the background and wait for readiness.
  reset-db     Recreate only the application database; keep Kratos identities.
  all          Build and start PostgreSQL, Kratos, and the backend image.
  restart-db   Restart PostgreSQL without removing its persistent volume.
  restart-all  Restart all currently created development containers.
  down     Stop all development services without removing their database volumes.
  status   Show the service status.
  check    Verify that PostgreSQL is accepting connections.
  test-services-up    Prepare the integration image and start its private dependencies.
  test-run [args...]   Run integration tests; optional arguments are passed to pytest.
  test-services-down  Remove project-labelled test containers/networks; keep volumes.
EOF
}

if [[ ! -f "${compose_file}" ]]; then
    printf 'Compose file not found: %s\n' "${compose_file}" >&2
    exit 1
fi

runtime="${INFRAMELD_CONTAINER_RUNTIME:-}"
compose_command=()

select_compose_command() {
    case "${runtime}" in
        podman)
            if podman compose version >/dev/null 2>&1; then
                compose_command=(podman compose)
            elif command -v podman-compose >/dev/null 2>&1; then
                compose_command=(podman-compose)
            else
                printf 'Podman Compose is not available.\n' >&2
                exit 1
            fi
            ;;
        docker)
            if docker compose version >/dev/null 2>&1; then
                compose_command=(docker compose)
            else
                printf 'Docker Compose is not available.\n' >&2
                exit 1
            fi
            ;;
        "")
            if command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
                compose_command=(podman compose)
            elif command -v podman-compose >/dev/null 2>&1; then
                compose_command=(podman-compose)
            elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
                compose_command=(docker compose)
            else
                printf 'No supported Compose command was found. Install Podman Compose or Docker Compose.\n' >&2
                exit 1
            fi
            ;;
        *)
            printf 'Unsupported INFRAMELD_CONTAINER_RUNTIME: %s\n' "${runtime}" >&2
            printf 'Use podman or docker.\n' >&2
            exit 1
            ;;
    esac
}

select_compose_command
container_command="${compose_command[0]}"
if [[ "${container_command}" == "podman-compose" ]]; then
    container_command=podman
fi

compose() {
    "${compose_command[@]}" -f "${compose_file}" "$@"
}

test_compose() {
    PODMAN_COMPOSE_WARNING_LOGS=false "${compose_command[@]}" -p inframeld-test -f "${test_compose_file}" "$@"
}

wait_for_postgres() {
    local max_attempts=60
    local attempt
    local readiness_output=""

    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if readiness_output="$(compose exec -T postgres pg_isready -U inframeld -d inframeld 2>&1)"; then
            printf 'PostgreSQL is ready at 127.0.0.1:15432.\n'
            return 0
        fi

        if ((attempt < max_attempts)); then
            sleep 1
        fi
    done

    printf 'PostgreSQL did not become ready after %s attempts.\n' "${max_attempts}" >&2
    printf 'Required dependency: the postgres service from compose.dev.yaml.\n' >&2
    printf 'Inspect it with: pnpm dev:db:status\n' >&2
    printf 'Last readiness check: %s\n' "${readiness_output}" >&2
    return 1
}

wait_for_kratos() {
    local max_attempts=60
    local attempt
    local readiness_output=""

    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if readiness_output="$(curl --fail --silent --show-error --max-time 2 http://127.0.0.1:14434/health/ready 2>&1)"; then
            printf 'Kratos is ready at 127.0.0.1:14434.\n'
            return 0
        fi

        if ((attempt < max_attempts)); then
            sleep 1
        fi
    done

    printf 'Kratos did not become ready after %s attempts.\n' "${max_attempts}" >&2
    printf 'Required dependency: the kratos service from compose.dev.yaml.\n' >&2
    printf 'Last readiness check: %s\n' "${readiness_output}" >&2
    return 1
}

# Read actual project resources, including containers left by older profiles.
# Query both label conventions because Podman can use either Compose provider.
test_resource_ids() {
    local kind="$1"
    local label podman_ids docker_ids
    local query=()
    if [[ "${kind}" == "container" ]]; then
        query=(ps -aq --no-trunc)
    else
        query=(network ls -q --no-trunc)
    fi
    if [[ -n "${2:-}" ]]; then
        query+=(--filter "label=com.docker.compose.service=$2")
    fi
    label="io.podman.compose.project=inframeld-test"
    podman_ids="$("${container_command}" "${query[@]}" --filter "label=${label}")" || return 1
    label="com.docker.compose.project=inframeld-test"
    docker_ids="$("${container_command}" "${query[@]}" --filter "label=${label}")" || return 1
    printf '%s\n%s\n' "${podman_ids}" "${docker_ids}" | sort -u | sed '/^$/d'
}

test_container_command() {
    local id="$1"
    shift
    local output remaining
    if output="$("${container_command}" "$@" "${id}" 2>&1)"; then
        return 0
    fi
    remaining="$(test_resource_ids container)" || return 1
    case $'\n'"${remaining}"$'\n' in
        *$'\n'"${id}"$'\n'*) printf '%s\n' "${output}" >&2; return 1 ;;
    esac
    # A --rm runner can disappear between listing it and stopping/removing it.
    # Only accept that race after confirming the resource is already gone.
    return 0
}

cleanup_test_services() {
    local remaining id dependencies attempt networks service runners
    local ids=()
    # One-off runners have no runtime dependencies under run --no-deps. Stop
    # them explicitly before touching providers, including the old Hydra runner.
    for service in integration-tests hydra-tests; do
        runners="$(test_resource_ids container "${service}")" || return 1
        if [[ -n "${runners}" ]]; then
            while IFS= read -r id; do
                test_container_command "${id}" stop --time 5 || return 1
            done <<< "${runners}"
        fi
    done
    # Podman records container dependencies. Remove their children first rather
    # than letting Compose attempt to delete a database with dependent orphans.
    for ((attempt = 1; attempt <= 20; attempt++)); do
        remaining="$(test_resource_ids container)" || return 1
        [[ -n "${remaining}" ]] || break
        ids=()
        while IFS= read -r id; do ids+=("${id}"); done <<< "${remaining}"
        dependencies=""
        if [[ "${container_command}" == "podman" ]]; then
            dependencies="$(podman inspect --format '{{range .Dependencies}}{{.}} {{end}}' "${ids[@]}")" || return 1
            dependencies="${dependencies//$'\n'/ }"
        fi
        for id in "${ids[@]}"; do
            case " ${dependencies} " in
                *" ${id} "*) continue ;;
            esac
            # Stop children before their providers so interrupted pytest cannot
            # keep making requests while its database is being shut down.
            # Keep real errors visible and retry remaining resources.
            test_container_command "${id}" stop --time 5 || continue
            # --volumes removes anonymous image volumes, retaining named test data.
            test_container_command "${id}" rm --volumes || continue
        done
        sleep 0.25
    done
    remaining="$(test_resource_ids container)" || return 1
    if [[ -n "${remaining}" ]]; then
        printf 'Test container cleanup failed; remaining IDs:\n%s\n' "${remaining}" >&2
        return 1
    fi

    networks="$(test_resource_ids network)" || return 1
    if [[ -n "${networks}" ]]; then
        while IFS= read -r id; do
            "${container_command}" network rm "${id}" >/dev/null || return 1
        done <<< "${networks}"
    fi
    remaining="$(test_resource_ids network)" || return 1
    if [[ -n "${remaining}" ]]; then
        printf 'Test network cleanup failed; remaining IDs:\n%s\n' "${remaining}" >&2
        return 1
    fi
}

command_name="${1:-}"
shift || true

case "${command_name}" in
    up)
        compose up -d postgres kratos
        wait_for_postgres
        wait_for_kratos
        ;;
    reset-db)
        compose down
        compose up -d postgres
        wait_for_postgres
        compose exec -T postgres dropdb --maintenance-db=postgres --if-exists --force -U inframeld inframeld
        compose exec -T postgres createdb --maintenance-db=postgres -U inframeld inframeld
        compose up -d kratos
        wait_for_kratos
        ;;
    all)
        compose up -d --build "$@"
        wait_for_postgres
        wait_for_kratos
        ;;
    restart-db)
        compose restart postgres "$@"
        ;;
    restart-all)
        compose restart "$@"
        ;;
    down)
        compose down "$@"
        ;;
    status)
        compose ps "$@"
        ;;
    check)
        if readiness_output="$(compose exec -T postgres pg_isready -U inframeld -d inframeld 2>&1)"; then
            printf 'PostgreSQL is ready at 127.0.0.1:15432.\n'
        else
            printf 'PostgreSQL integration dependency is not ready.\n' >&2
            printf 'Required dependency: the postgres service from compose.dev.yaml.\n' >&2
            printf 'Start it with: pnpm dev:db\n' >&2
            printf 'Inspect it with: pnpm dev:db:status\n' >&2
            printf 'Details: %s\n' "${readiness_output}" >&2
            exit 1
        fi
        ;;
    test-services-up)
        cleanup_test_services
        if [[ -n "${INFRAMELD_INTEGRATION_IMAGE:-}" ]]; then
            # CI loads the current image after a cache-aware Buildx build.
            # Require it locally instead of pulling or rebuilding a different image.
            if ! "${container_command}" image inspect "${INFRAMELD_INTEGRATION_IMAGE}" >/dev/null; then
                printf 'Prebuilt integration image is not available locally: %s\n' "${INFRAMELD_INTEGRATION_IMAGE}" >&2
                exit 1
            fi
            printf 'Using prebuilt integration image: %s\n' "${INFRAMELD_INTEGRATION_IMAGE}"
        else
            test_compose build integration-tests
        fi
        test_compose up -d postgres mailpit mock-oidc recovery-hooks kratos kratos-expiring hydra
        ;;
    test-run)
        # Replace this shell so interruption can terminate the Compose process.
        exec env PODMAN_COMPOSE_WARNING_LOGS=false "${compose_command[@]}" \
            -p inframeld-test -f "${test_compose_file}" \
            run --rm --no-deps -T integration-tests "$@"
        ;;
    test-services-down)
        cleanup_test_services
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
