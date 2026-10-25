#!/usr/bin/env bash

# Qualify the development profile using new project-scoped data and no published ports.
set -euo pipefail
set -m

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_dir}/.." && pwd)"
cd "${repository_root}"
qualification_dir="$(mktemp -d "${TMPDIR:-/tmp}/inframeld-dev-oauth-XXXXXXXX")"
qualification_project="$(basename "${qualification_dir}" | tr '[:upper:]' '[:lower:]')"
qualification_image="localhost/${qualification_project}-backend:check"
qualification_compose=()
qualification_runtime="${INFRAMELD_CONTAINER_RUNTIME:-}"
active_pid=""

case "${qualification_runtime}" in
    podman) qualification_compose=(podman compose) ;;
    docker) qualification_compose=(docker compose) ;;
    "")
        if command -v podman >/dev/null 2>&1; then
            qualification_runtime=podman
            qualification_compose=(podman compose)
        else
            qualification_runtime=docker
            qualification_compose=(docker compose)
        fi
        ;;
    *) printf 'Use podman or docker.\n' >&2; exit 2 ;;
esac

qualified_compose() {
    PODMAN_COMPOSE_WARNING_LOGS=false "${qualification_compose[@]}" -p "${qualification_project}" \
        -f "${qualification_dir}/compose.json" "$@"
}

run_development_command() {
    env PODMAN_COMPOSE_WARNING_LOGS=false \
        INFRAMELD_CONTAINER_RUNTIME="${qualification_runtime}" \
        INFRAMELD_DEV_COMPOSE_FILE="${qualification_dir}/compose.json" \
        INFRAMELD_DEV_COMPOSE_PROJECT="${qualification_project}" \
        bash "${script_dir}/dev-compose.sh" "$@"
}

qualification_ids() {
    local kind="$1" label
    for label in com.docker.compose.project io.podman.compose.project; do
        if [[ "${kind}" == container ]]; then
            "${qualification_runtime}" ps -aq --filter "label=${label}=${qualification_project}"
        else
            "${qualification_runtime}" network ls -q --filter "label=${label}=${qualification_project}"
        fi
    done | sort -u | sed '/^$/d'
}

qualification_container_command() {
    local id="$1" output remaining
    shift
    if output="$("${qualification_runtime}" "$@" "${id}" 2>&1)"; then
        return 0
    fi
    remaining="$(qualification_ids container)" || return 1
    # A stopped --rm setup container can disappear before explicit removal.
    case $'\n'"${remaining}"$'\n' in
        *$'\n'"${id}"$'\n'*) printf '%s\n' "${output}" >&2; return 1 ;;
    esac
}

remove_qualification_resources() {
    local id remaining
    remaining="$(qualification_ids container)" || return 1
    if [[ -n "${remaining}" ]]; then
        while IFS= read -r id; do
            qualification_container_command "${id}" stop --time 5 || return 1
            qualification_container_command "${id}" rm --volumes || return 1
        done <<< "${remaining}"
    fi
    remaining="$(qualification_ids network)" || return 1
    if [[ -n "${remaining}" ]]; then
        while IFS= read -r id; do
            "${qualification_runtime}" network rm "${id}" >/dev/null || return 1
        done <<< "${remaining}"
    fi
    if [[ -f "${qualification_dir}/compose.json" ]]; then
        while IFS= read -r id; do
            [[ "${id}" == "${qualification_project}_"* ]] || return 1
            if "${qualification_runtime}" volume inspect "${id}" >/dev/null 2>&1; then
                "${qualification_runtime}" volume rm "${id}" >/dev/null || return 1
            fi
        done < <(uv run --project apps/backend python -c 'import json,sys; c=json.load(open(sys.argv[1])); print("\n".join(v["name"] for v in c["volumes"].values()))' "${qualification_dir}/compose.json")
    fi
    [[ -z "$(qualification_ids container)" && -z "$(qualification_ids network)" ]]
}

cleanup() {
    local exit_status=$?
    trap - EXIT
    trap '' INT TERM
    if ! remove_qualification_resources; then
        [[ "${exit_status}" -ne 0 ]] || exit_status=1
    fi
    if "${qualification_runtime}" image inspect "${qualification_image}" >/dev/null 2>&1; then
        if ! "${qualification_runtime}" image rm "${qualification_image}"; then
            [[ "${exit_status}" -ne 0 ]] || exit_status=1
        fi
    fi
    rm -rf -- "${qualification_dir}"
    exit "${exit_status}"
}

interrupt_run() {
    trap '' INT TERM
    if [[ -n "${active_pid}" ]]; then
        kill -TERM -- "-${active_pid}" 2>/dev/null || true
        wait "${active_pid}" 2>/dev/null || true
    fi
    exit "$1"
}

run_step() {
    "$@" </dev/null &
    active_pid=$!
    local exit_status=0
    wait "${active_pid}" || exit_status=$?
    active_pid=""
    return "${exit_status}"
}

trap cleanup EXIT
trap 'interrupt_run 130' INT
trap 'interrupt_run 143' TERM
export INFRAMELD_FINGERPRINT_KEY_HOST_FILE="${qualification_dir}/fingerprint.key"
uv run --project apps/backend python - "${INFRAMELD_FINGERPRINT_KEY_HOST_FILE}" <<'PY'
from pathlib import Path
from secrets import token_bytes
import sys
key = Path(sys.argv[1])
key.write_bytes(token_bytes(32))
# Disposable test-only material must be readable by the container's non-root UID.
key.chmod(0o644)
PY

PODMAN_COMPOSE_WARNING_LOGS=false "${qualification_compose[@]}" -p "${qualification_project}" \
    -f "${repository_root}/compose.dev.yaml" config > "${qualification_dir}/rendered.yaml"

uv run --project apps/backend python - "${qualification_dir}" "${qualification_project}" "${qualification_image}" "${repository_root}" <<'PY'
import json
from pathlib import Path
import sys
import yaml
directory, project, image = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
root = Path(sys.argv[4])
config = yaml.safe_load((directory / 'rendered.yaml').read_text())
for service in config['services'].values():
    service.pop('ports', None)
    if 'build' in service:
        service['image'] = image
        service['build']['context'] = str(root)
    mounts = []
    for mount in service.get('volumes', []):
        if isinstance(mount, str) and mount.startswith('.'):
            source, rest = mount.split(':', 1)
            mount = f'{(root / source).resolve()}:{rest}'
        elif isinstance(mount, dict) and mount.get('type') == 'bind':
            mount['source'] = str((root / mount['source']).resolve())
        mounts.append(mount)
    if mounts:
        service['volumes'] = mounts
for name, volume in config['volumes'].items():
    if volume is None:
        volume = config['volumes'][name] = {}
    volume['name'] = f'{project}_{name}'
    volume.pop('external', None)
(directory / 'compose.json').write_text(json.dumps(config))
PY

run_step run_development_command up
run_step qualified_compose run --rm --no-deps -T backend python -m inframeld_backend.migrate
run_step run_development_command all

run_step qualified_compose exec -T backend python -c '
import json, time, urllib.request
deadline = time.monotonic() + 60
while True:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            assert json.load(response) == {"status": "ok"}
        break
    except OSError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(0.25)
'
run_step run_development_command configure-oauth > "${qualification_dir}/repeated.json"
uv run --project apps/backend python - "${qualification_dir}/repeated.json" <<'PY'
import json, sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text().splitlines()
assert json.loads(lines[-1]) == {'clientId': 'inframeld-cli', 'outcome': 'unchanged'}
PY
run_step run_development_command restart-all
run_step run_development_command configure-oauth > "${qualification_dir}/restarted.json"
uv run --project apps/backend python - "${qualification_dir}/restarted.json" <<'PY'
import json, sys
from pathlib import Path
lines = Path(sys.argv[1]).read_text().splitlines()
assert json.loads(lines[-1]) == {'clientId': 'inframeld-cli', 'outcome': 'unchanged'}
print('Development OAuth setup, API startup and persisted registration passed in an isolated project.')
PY
