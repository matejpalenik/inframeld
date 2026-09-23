#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/.." && pwd)"
compose_file="${repository_root}/compose.dev.yaml"

usage() {
    cat <<'EOF'
Usage: ./scripts/dev-compose.sh <command>

Commands:
  up       Start only the development PostgreSQL service in the background.
  reset-db Delete the development database volume and recreate an empty PostgreSQL service.
  all      Build and start PostgreSQL and the backend image.
  restart-db   Restart PostgreSQL without removing its persistent volume.
  restart-all  Restart all currently created development containers.
  down     Stop all development services without removing the database volume.
  status   Show the service status.
  check    Verify that PostgreSQL is accepting connections.
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

command_name="${1:-}"
shift || true

case "${command_name}" in
    up)
        compose up -d postgres
        ;;
    reset-db)
        compose down -v
        compose up -d postgres
        ;;
    all)
        compose up -d --build "$@"
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
    *)
        usage >&2
        exit 2
        ;;
esac
