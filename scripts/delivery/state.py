"""Store one coordinator's local delivery record outside repository checkouts."""

import fcntl
import json
import os
import re
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import cast

from model import (
    MILESTONE,
    REPOSITORY,
    integer_value,
    issue_numbers,
    list_value,
    object_value,
    sha_value,
    string_value,
)
from planner import paths_overlap

BINDING_FIELDS = {"base_sha", "head_sha", "issue_updated_at"}
OWNER_FIELDS = {"worker_id", "worktree", "branch"}
AMEND_FIELDS = {"paths", "contracts", "required_checks", "blockers"}
OPERATION_FIELDS: dict[str, set[str]] = {
    "claim": {"op", "issue"} | BINDING_FIELDS | OWNER_FIELDS | AMEND_FIELDS,
    "revise": {"op", "issue"} | BINDING_FIELDS,
    "amend": {"op", "issue", "changes", "reference"} | BINDING_FIELDS,
    "adopt": {"op", "issue", "stop_cleanup"} | BINDING_FIELDS | OWNER_FIELDS,
    "retire": {"op", "issue", "stop_cleanup"} | BINDING_FIELDS,
    "evidence": {"op", "issue", "evidence"} | BINDING_FIELDS,
    "reserve": {"op", "issue", "resource", "token", "head_sha", "operation", "reference"},
    "release": {"op", "resource", "token", "head_sha", "cleanup", "reference"},
    "observe_merge": {
        "op",
        "issue",
        "status",
        "source",
        "pr",
        "head_sha",
        "reference",
        "observed_at",
    },
}
OPERATION_FIELDS["observe_prerequisite_merge"] = (
    OPERATION_FIELDS["observe_merge"] | BINDING_FIELDS | {"scope", "assessment_reference"}
)


def _known_fields(record: dict[str, object], allowed: set[str], name: str) -> None:
    unknown = set(record) - allowed
    if unknown:
        raise ValueError(f"unknown {name} fields: {', '.join(sorted(unknown))}")


def _operation_fields(record: dict[str, object], kind: str) -> None:
    if kind not in OPERATION_FIELDS:
        raise ValueError(f"unsupported operation: {kind}")
    required = OPERATION_FIELDS[kind]
    optional: set[str] = (
        {"merge_sha"}
        if kind in ("observe_merge", "observe_prerequisite_merge")
        and record.get("status") == "merged"
        else set()
    )
    _known_fields(record, required | optional, kind)
    missing = required - set(record)
    if missing:
        raise ValueError(f"missing {kind} fields: {', '.join(sorted(missing))}")


def _stop_cleanup(receipt: dict[str, object], assignment: dict[str, object]) -> None:
    fields = (
        BINDING_FIELDS
        | OWNER_FIELDS
        | {"stopped", "cleanup", "verified_by_coordinator", "reference"}
    )
    _known_fields(receipt, fields, "stop_cleanup")
    if _binding(receipt) != _binding(assignment) or any(
        receipt.get(field) != assignment[field] for field in OWNER_FIELDS
    ):
        raise ValueError("stop_cleanup does not identify the exact previous owner and revision")
    if (
        receipt.get("stopped") is not True
        or receipt.get("cleanup") != "verified_clean"
        or receipt.get("verified_by_coordinator") is not True
    ):
        raise ValueError("stop_cleanup needs a verified stopped owner and positive cleanup")
    string_value(receipt.get("reference"), "stop_cleanup reference")


def occupied_assignments(state: dict[str, object]) -> list[dict[str, object]]:
    """Keep all claims until a verified explicit retirement, including merged owners."""
    assignments = object_value(state.get("assignments"), "assignments")
    return [
        object_value(item, "assignment")
        for item in assignments.values()
        if object_value(item, "assignment").get("claim_state", "active") != "retired"
    ]


def _archive(
    assignment: dict[str, object], state: dict[str, object], operation: dict[str, object]
) -> None:
    previous = deepcopy({field: value for field, value in assignment.items() if field != "history"})
    history = list_value(assignment.setdefault("history", []), "assignment history")
    history.append(
        {
            "revision": integer_value(state["revision"], "revision") + 1,
            "operation": deepcopy(operation),
            "previous": previous,
        }
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def read_json(path: Path) -> dict[str, object]:
    try:
        result = cast(
            "object",
            json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON record: {error}") from error
    return object_value(result, "record")


def _paths(value: object) -> list[str]:
    result: list[str] = []
    for item in list_value(value, "paths"):
        path = string_value(item, "path")
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or str(pure) != path
            or any(char in path for char in "*?[]\\")
        ):
            raise ValueError(
                "claim paths must be normalized repository-relative paths without globs"
            )
        result.append(path)
    if not result or len(set(result)) != len(result):
        raise ValueError("claim paths must be nonempty and unique")
    return result


def _strings(value: object, name: str, *, nonempty: bool = False) -> list[str]:
    result = [string_value(item, name) for item in list_value(value, name)]
    if len(set(result)) != len(result) or (nonempty and not result):
        raise ValueError(f"{name} must be unique" + (" and nonempty" if nonempty else ""))
    return result


def _binding(record: dict[str, object]) -> tuple[str, str, str]:
    return (
        sha_value(record.get("base_sha"), "base_sha"),
        sha_value(record.get("head_sha"), "head_sha"),
        string_value(record.get("issue_updated_at"), "issue_updated_at"),
    )


def _assignment(record: dict[str, object]) -> None:
    integer_value(record.get("issue"), "issue", 1)
    string_value(record.get("worker_id"), "worker_id")
    worktree = string_value(record.get("worktree"), "worktree")
    if not Path(worktree).is_absolute():
        raise ValueError("worktree must be absolute")
    string_value(record.get("branch"), "branch")
    _paths(record.get("paths"))
    _strings(record.get("contracts"), "contracts")
    _strings(record.get("required_checks"), "required_checks", nonempty=True)
    list_value(record.get("blockers"), "blockers")
    object_value(record.get("evidence"), "evidence")
    _binding(record)
    supporting = object_value(record.get("prerequisite_merges", {}), "prerequisite_merges")
    for key, item in supporting.items():
        observation = object_value(item, "supporting merge")
        _validate_merge_observation(observation)
        _binding(observation)
        string_value(observation.get("scope"), "supporting scope")
        string_value(observation.get("assessment_reference"), "assessment_reference")
        if key != str(observation["pr"]) or observation.get("issue") != record["issue"]:
            raise ValueError("supporting merge must identify its issue and PR")
    if record.get("merge_state") not in ("unmerged", "uncertain", "merged", "not_merged"):
        raise ValueError("invalid merge_state")
    if record.get("claim_state", "active") not in ("active", "retired"):
        raise ValueError("invalid claim_state")
    for item in list_value(record.get("history", []), "assignment history"):
        event = object_value(item, "history event")
        integer_value(event.get("revision"), "history revision", 1)
        object_value(event.get("previous"), "previous assignment")
        object_value(event.get("operation"), "history operation")
    if record.get("claim_state") == "retired":
        if record["merge_state"] == "uncertain" or any(
            object_value(item, "supporting merge")["status"] == "uncertain"
            for item in supporting.values()
        ):
            raise ValueError("uncertain merge cannot be retired")
        _stop_cleanup(object_value(record.get("retirement_receipt"), "retirement_receipt"), record)


def _exclusive(records: dict[str, object]) -> None:
    assignments = [
        object_value(value, "assignment")
        for value in records.values()
        if object_value(value, "assignment").get("claim_state", "active") != "retired"
    ]
    for index, left in enumerate(assignments):
        for right in assignments[index + 1 :]:
            if left["worktree"] == right["worktree"]:
                raise ValueError("worktree is already claimed")
            if left["branch"] == right["branch"]:
                raise ValueError("branch is already claimed")
            if left["worker_id"] == right["worker_id"]:
                raise ValueError("worker is already claimed")
            if any(
                paths_overlap(first, second)
                for first in _paths(left["paths"])
                for second in _paths(right["paths"])
            ):
                raise ValueError("active claim paths overlap")
            if set(_strings(left["contracts"], "contracts")) & set(
                _strings(right["contracts"], "contracts")
            ):
                raise ValueError("active claim contracts overlap")


def validate_state(state: dict[str, object]) -> None:
    if state.get("schema_version") not in (1, 2) or isinstance(state.get("schema_version"), bool):
        raise ValueError("unsupported state schema_version")
    if (
        state.get("repository") != REPOSITORY
        or state.get("milestone") != MILESTONE
        or isinstance(state.get("milestone"), bool)
    ):
        raise ValueError("unexpected repository or milestone")
    if state.get("mode") not in ("live", "rehearsal"):
        raise ValueError("mode must be live or rehearsal")
    for field in ("run_id", "coordinator_id", "authorization_reference"):
        string_value(state.get(field), field)
    integer_value(state.get("revision"), "revision")
    allowed = issue_numbers(state.get("allowed_issues"), "allowed_issues")
    if not allowed:
        raise ValueError("allowed_issues must be a finite nonempty scope")
    assignments = object_value(state.get("assignments"), "assignments")
    for key, item in assignments.items():
        assignment = object_value(item, "assignment")
        _assignment(assignment)
        if state["schema_version"] == 1 and assignment.get("prerequisite_merges"):
            raise ValueError("supporting merge records require state schema_version 2")
        if key != str(assignment["issue"]) or assignment["issue"] not in allowed:
            raise ValueError("assignment is outside authorized scope")
    _exclusive(assignments)
    resources = object_value(state.get("resources"), "resources")
    for name, item in resources.items():
        if re.fullmatch(r"[a-z][a-z0-9:_-]*", name) is None:
            raise ValueError("invalid resource name")
        resource = object_value(item, "resource")
        issue = integer_value(resource.get("issue"), "resource issue", 1)
        if str(issue) not in assignments:
            raise ValueError("resource owner is not assigned")
        if object_value(assignments[str(issue)], "assignment").get("claim_state") == "retired":
            raise ValueError("retired assignment cannot retain an occupied resource")
        for field in ("token", "operation", "reference"):
            string_value(resource.get(field), field)
        sha_value(resource.get("head_sha"), "resource head_sha")
    observations = object_value(state.get("merge_observations"), "merge_observations")
    for key, item in observations.items():
        if key not in assignments:
            raise ValueError("merge observation has no assignment")
        observation = object_value(item, "merge observation")
        _validate_merge_observation(observation)
        assignment = object_value(assignments[key], "assignment")
        if (
            observation["status"] != assignment["merge_state"]
            or observation["head_sha"] != assignment["head_sha"]
        ):
            raise ValueError("merge observation does not match current assignment")
    for key, item in assignments.items():
        assignment = object_value(item, "assignment")
        if assignment["merge_state"] != "unmerged" and key not in observations:
            raise ValueError("merge state requires a matching observed GitHub receipt")


def _validate_merge_observation(record: dict[str, object]) -> None:
    status = record.get("status")
    if status not in ("uncertain", "merged", "not_merged"):
        raise ValueError("invalid observed merge status")
    if record.get("source") != "github":
        raise ValueError("merge reconciliation requires observed GitHub state")
    number = integer_value(record.get("pr"), "pr", 1)
    if record.get("reference") != f"https://github.com/{REPOSITORY}/pull/{number}":
        raise ValueError("merge reference must identify the observed repository PR")
    sha_value(record.get("head_sha"), "observed head_sha")
    string_value(record.get("observed_at"), "observed_at")
    if status == "merged":
        sha_value(record.get("merge_sha"), "merge_sha")


class StateStore:
    def __init__(self, path: Path) -> None:
        if not path.is_absolute():
            raise ValueError("state path must be absolute and outside repository checkouts")
        if path.is_symlink():
            raise ValueError("state path must not be a symlink")
        self.path = path.resolve()
        if any((parent / ".git").exists() for parent in self.path.parents):
            raise ValueError("state must be outside repository checkouts")

    @contextmanager
    def _lock(self) -> Generator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _write(self, state: dict[str, object]) -> None:
        validate_state(state)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".delivery-", suffix=".tmp", dir=self.path.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(state, output, indent=2, sort_keys=True, allow_nan=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary_path.unlink(missing_ok=True)

    def initialize(
        self,
        *,
        run_id: str,
        coordinator_id: str,
        authorization_reference: str,
        allowed_issues: list[int],
        mode: str = "rehearsal",
    ) -> dict[str, object]:
        state: dict[str, object] = {
            "schema_version": 1,
            "repository": REPOSITORY,
            "milestone": MILESTONE,
            "run_id": run_id,
            "coordinator_id": coordinator_id,
            "authorization_reference": authorization_reference,
            "allowed_issues": allowed_issues,
            "mode": mode,
            "revision": 0,
            "assignments": {},
            "resources": {},
            "merge_observations": {},
        }
        validate_state(state)
        with self._lock():
            if self.path.exists():
                raise ValueError("state already exists, initialize never overwrites a run")
            self._write(state)
        return state

    def read(self) -> dict[str, object]:
        if self.path.is_symlink():
            raise ValueError("state path must not be a symlink")
        result = read_json(self.path)
        validate_state(result)
        return result

    def apply(
        self,
        *,
        run_id: str,
        coordinator_id: str,
        expected_revision: int,
        operation: dict[str, object],
    ) -> dict[str, object]:
        """Apply one coordinator update under a process lock and revision check."""
        integer_value(expected_revision, "expected_revision")
        with self._lock():
            current = self.read()
            if current["run_id"] != run_id or current["coordinator_id"] != coordinator_id:
                raise ValueError("run or coordinator identity does not match")
            if current["revision"] != expected_revision:
                raise ValueError("stale expected_revision, read state again before updating")
            updated = deepcopy(current)
            self._operate(updated, operation)
            updated["revision"] = expected_revision + 1
            self._write(updated)
        return updated

    def _operate(self, state: dict[str, object], operation: dict[str, object]) -> None:
        kind = string_value(operation.get("op"), "op")
        _operation_fields(operation, kind)
        assignments = object_value(state["assignments"], "assignments")
        resources = object_value(state["resources"], "resources")
        if kind == "release":
            name = string_value(operation.get("resource"), "resource")
            resource = object_value(resources.get(name), "reserved resource")
            if operation.get("token") != resource["token"]:
                raise ValueError("reservation token does not match")
            if (
                operation.get("cleanup") != "verified_clean"
                or operation.get("head_sha") != resource["head_sha"]
            ):
                raise ValueError(
                    "cleanup is dirty, unknown, or bound to another revision, keep resource occupied"
                )
            string_value(operation.get("reference"), "cleanup reference")
            assignment = object_value(assignments[str(resource["issue"])], "assignment")
            _archive(assignment, state, operation)
            del resources[name]
            return
        issue = integer_value(operation.get("issue"), "issue", 1)
        key = str(issue)
        if issue not in issue_numbers(state["allowed_issues"], "allowed_issues"):
            raise ValueError("issue is outside authorized scope")
        if kind == "claim":
            if key in assignments:
                raise ValueError(
                    "issue is already claimed, stale ownership never expires automatically"
                )
            assignment = {field: value for field, value in operation.items() if field != "op"}
            assignment.update(
                {"evidence": {}, "merge_state": "unmerged", "claim_state": "active", "history": []}
            )
            worktree = Path(string_value(assignment.get("worktree"), "worktree"))
            if not worktree.is_absolute():
                raise ValueError("worktree must be absolute")
            assignment["worktree"] = str(worktree.resolve())
            _assignment(assignment)
            assignments[key] = assignment
            _exclusive(assignments)
            return
        assignment = object_value(assignments.get(key), "assigned issue")
        supporting = object_value(assignment.get("prerequisite_merges", {}), "prerequisite_merges")
        uncertain_support = any(
            object_value(item, "supporting merge")["status"] == "uncertain"
            for item in supporting.values()
        )
        if kind == "observe_prerequisite_merge":
            _validate_merge_observation(operation)
            if _binding(operation) != _binding(assignment):
                raise ValueError("supporting merge binding is stale")
            if assignment.get("claim_state") == "retired" or assignment["merge_state"] in (
                "uncertain",
                "merged",
            ):
                raise ValueError("supporting merge requires an active unmerged issue")
            string_value(operation.get("scope"), "supporting scope")
            string_value(operation.get("assessment_reference"), "assessment_reference")
            pr_key = str(operation["pr"])
            previous = (
                object_value(supporting[pr_key], "supporting merge")
                if pr_key in supporting
                else None
            )
            if previous is not None:
                if previous["status"] == "merged":
                    raise ValueError("a merged supporting receipt cannot be changed")
                if previous["status"] == "uncertain" and any(
                    previous.get(field) != operation.get(field)
                    for field in (
                        "base_sha",
                        "head_sha",
                        "issue_updated_at",
                        "scope",
                        "assessment_reference",
                    )
                ):
                    raise ValueError("reconciliation must preserve the supporting PR binding")
            if uncertain_support and (previous is None or previous["status"] != "uncertain"):
                raise ValueError("reconcile uncertain supporting merge first")
            _archive(assignment, state, operation)
            supporting[pr_key] = {
                field: value for field, value in operation.items() if field != "op"
            }
            assignment["prerequisite_merges"] = supporting
            state["schema_version"] = 2
            return
        if uncertain_support:
            raise ValueError("supporting merge is uncertain, reconcile GitHub state first")
        if kind == "observe_merge":
            _validate_merge_observation(operation)
            if operation["head_sha"] != assignment["head_sha"]:
                raise ValueError("observed merge head is stale")
            if assignment["merge_state"] == "merged" and operation["status"] != "merged":
                raise ValueError("a merged receipt cannot be reverted")
            _archive(assignment, state, operation)
            observations = object_value(state["merge_observations"], "merge_observations")
            observations[key] = {
                field: value for field, value in operation.items() if field != "op"
            }
            assignment["merge_state"] = operation["status"]
            return
        if assignment["merge_state"] == "uncertain":
            raise ValueError("merge is uncertain, reconcile GitHub state first")
        held_resources = any(
            object_value(item, "resource")["issue"] == issue for item in resources.values()
        )
        if kind in ("retire", "adopt", "amend", "revise"):
            if _binding(operation) != _binding(assignment) and kind != "revise":
                raise ValueError("lifecycle operation is stale for the assignment")
            if held_resources:
                raise ValueError(
                    "release occupied resources with verified cleanup before changing ownership or scope"
                )
        if kind == "retire":
            if assignment.get("claim_state") == "retired":
                raise ValueError("assignment is already retired")
            receipt = object_value(operation.get("stop_cleanup"), "stop_cleanup")
            _stop_cleanup(receipt, assignment)
            _archive(assignment, state, operation)
            assignment["claim_state"] = "retired"
            assignment["retirement_receipt"] = deepcopy(receipt)
            assignment["evidence"] = {}
            return
        if assignment["merge_state"] == "merged":
            raise ValueError("assignment is already merged and cannot be changed or adopted")
        if kind == "adopt":
            _stop_cleanup(object_value(operation.get("stop_cleanup"), "stop_cleanup"), assignment)
            _archive(assignment, state, operation)
            for field in OWNER_FIELDS:
                assignment[field] = operation[field]
            worktree = Path(string_value(assignment.get("worktree"), "worktree"))
            if not worktree.is_absolute():
                raise ValueError("worktree must be absolute")
            assignment["worktree"] = str(worktree.resolve())
            assignment["claim_state"] = "active"
            assignment.pop("retirement_receipt", None)
            assignment["evidence"] = {}
            _assignment(assignment)
            _exclusive(assignments)
            return
        if assignment.get("claim_state") == "retired":
            raise ValueError(
                "assignment is retired, adopt it with verified handoff before updating"
            )
        if kind == "revise":
            _binding(operation)
            _archive(assignment, state, operation)
            for field in BINDING_FIELDS:
                assignment[field] = operation[field]
            assignment["evidence"] = {}
            assignment["merge_state"] = "unmerged"
            object_value(state["merge_observations"], "merge_observations").pop(key, None)
        elif kind == "amend":
            changes = object_value(operation.get("changes"), "changes")
            _known_fields(changes, AMEND_FIELDS, "amend changes")
            if not changes:
                raise ValueError("amend changes must not be empty")
            string_value(operation.get("reference"), "amend reference")
            _archive(assignment, state, operation)
            assignment.update(deepcopy(changes))
            assignment["evidence"] = {}
            _assignment(assignment)
            _exclusive(assignments)
        elif kind == "evidence":
            if _binding(operation) != _binding(assignment):
                raise ValueError("evidence is stale for the assignment")
            assignment["evidence"] = deepcopy(object_value(operation.get("evidence"), "evidence"))
        elif kind == "reserve":
            name = string_value(operation.get("resource"), "resource")
            if name in resources:
                raise ValueError("resource is occupied until explicit verified cleanup")
            if operation.get("head_sha") != assignment["head_sha"]:
                raise ValueError("reservation head is stale")
            resources[name] = {
                field: operation.get(field)
                for field in ("issue", "head_sha", "token", "operation", "reference")
            }
        else:
            raise ValueError(f"unsupported operation: {kind}")
