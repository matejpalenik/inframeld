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
  test-db-up     Start the isolated PostgreSQL integration-test service.
  test-db-down   Stop and remove the integration-test service, keeping its test-only volume.
  test-services-up    Start PostgreSQL and Kratos for the full integration suite.
  test-services-down  Stop the test services, keeping their test-only volumes.
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

compose() {
    "${compose_command[@]}" -f "${compose_file}" "$@"
}

test_compose() {
    "${compose_command[@]}" -p inframeld-test -f "${test_compose_file}" "$@"
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

wait_for_test_postgres() {
    local max_attempts=60
    local attempt
    local readiness_output=""

    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if readiness_output="$(test_compose exec -T postgres pg_isready -U inframeld_test -d inframeld_test 2>&1)"; then
            printf 'Test PostgreSQL is ready at 127.0.0.1:15433.\n'
            return 0
        fi

        if ((attempt < max_attempts)); then
            sleep 1
        fi
    done

    printf 'Test PostgreSQL did not become ready after %s attempts.\n' "${max_attempts}" >&2
    printf 'Required dependency: the postgres service from compose.test.yaml.\n' >&2
    printf 'Last readiness check: %s\n' "${readiness_output}" >&2
    return 1
}

wait_for_test_kratos() {
    local max_attempts=60
    local attempt
    local readiness_output=""

    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if readiness_output="$(curl --fail --silent --show-error --max-time 2 http://127.0.0.1:14433/health/ready 2>&1)"; then
            printf 'Test Kratos is ready at 127.0.0.1:14433.\n'
            return 0
        fi

        if ((attempt < max_attempts)); then
            sleep 1
        fi
    done

    printf 'Test Kratos did not become ready after %s attempts.\n' "${max_attempts}" >&2
    printf 'Required dependency: the kratos service from compose.test.yaml.\n' >&2
    printf 'Last readiness check: %s\n' "${readiness_output}" >&2
    return 1
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
    test-db-up)
        test_compose up -d postgres
        wait_for_test_postgres
        ;;
    test-db-down)
        test_compose down --remove-orphans
        ;;
    test-services-up)
        test_compose up -d postgres kratos
        wait_for_test_postgres
        wait_for_test_kratos
        ;;
    test-services-down)
        test_compose down --remove-orphans
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
