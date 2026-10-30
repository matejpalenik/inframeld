"""Expose local delivery records and a read-only backlog plan as JSON commands."""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

from github import GitHubClient
from model import (
    MILESTONE,
    REPOSITORY,
    assess_merge,
    integer_value,
    issue_numbers,
    list_value,
    object_value,
    string_value,
)
from planner import create_plan
from rehearsal import rehearse
from state import StateStore, occupied_assignments, read_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    plan = subcommands.add_parser("plan", help="Read the v1 backlog, no dispatch or GitHub writes")
    plan.add_argument("--state", type=Path, help="Existing runtime state outside every checkout")
    plan.add_argument(
        "--snapshot", type=Path, help="Read an offline snapshot instead of querying GitHub"
    )
    plan.add_argument(
        "--no-local-worktrees", action="store_true", help="Omit local git worktree inventory"
    )
    status = subcommands.add_parser("status", help="Validate and summarize local runtime state")
    status.add_argument("--state", type=Path, required=True)
    initialize = subcommands.add_parser(
        "init", help="Initialize finite local scope, never launch workers"
    )
    initialize.add_argument("--state", type=Path, required=True)
    initialize.add_argument("--input", type=Path, required=True)
    apply = subcommands.add_parser("apply", help="Apply one local coordinator record update")
    apply.add_argument("--state", type=Path, required=True)
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--coordinator-id", required=True)
    apply.add_argument("--expected-revision", type=int, required=True)
    assess = subcommands.add_parser(
        "assess-merge", help="Assess evidence, never merge or authorize a merge"
    )
    assess.add_argument("--state", type=Path, required=True)
    assess.add_argument("--issue", type=int, required=True)
    assess.add_argument("--observation", type=Path, required=True)
    subcommands.add_parser(
        "rehearse", help="Run deterministic disposable scenarios without GitHub calls"
    )
    return parser


def _worktrees() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain", "-z"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError(
            "local worktree inventory failed, reconcile ownership before proceeding"
        ) from error
    records: list[dict[str, str]] = []
    for block in result.stdout.split("\0\0"):
        record: dict[str, str] = {}
        for field in block.split("\0"):
            if field:
                name, _, value = field.partition(" ")
                record[name] = value
        if record:
            records.append(record)
    return records


def _snapshot(value: dict[str, object]) -> None:
    if value.get("schema_version") != 1 or value.get("repository") != REPOSITORY:
        raise ValueError("unexpected snapshot schema or repository")
    milestone = object_value(value.get("milestone"), "milestone")
    if milestone.get("number") != MILESTONE or milestone.get("title") != "v1":
        raise ValueError("snapshot must describe milestone 1 titled v1")
    issues = [object_value(item, "issue") for item in list_value(value.get("issues"), "issues")]
    numbers = [integer_value(issue.get("number"), "issue number", 1) for issue in issues]
    if len(set(numbers)) != len(numbers) or sorted(numbers) != sorted(
        issue_numbers(value.get("allowed_issues"), "allowed_issues")
    ):
        raise ValueError("snapshot scope must exactly match the captured finite issue set")


def _execute(arguments: argparse.Namespace) -> dict[str, object]:
    command = cast("str", arguments.command)
    if command == "rehearse":
        return rehearse()
    if command == "plan":
        offline = cast("Path | None", arguments.snapshot)
        snapshot = read_json(offline) if offline else GitHubClient().snapshot()
        _snapshot(snapshot)
        claims: list[dict[str, object]] = []
        state_path = cast("Path | None", arguments.state)
        if state_path is not None:
            state = StateStore(state_path).read()
            claims = occupied_assignments(state)
        issues = [object_value(item, "issue") for item in list_value(snapshot["issues"], "issues")]
        prs = [
            object_value(item, "PR") for item in list_value(snapshot.get("open_prs"), "open_prs")
        ]
        return {
            "schema_version": 1,
            "source": "offline_file" if offline else "github_read_only",
            "snapshot": snapshot,
            "plan": create_plan(issues, claims, prs),
            "local_worktrees": [] if arguments.no_local_worktrees else _worktrees(),
            "github_mutations": 0,
            "workers_started": 0,
        }
    path = cast("Path", arguments.state)
    store = StateStore(path)
    if command == "status":
        state = store.read()
        return {
            **state,
            "occupied_issues": sorted(
                integer_value(item["issue"], "issue", 1) for item in occupied_assignments(state)
            ),
            "merge_authorized_by_helper": False,
            "ownership_expires_automatically": False,
            "uncertain_merges_require_github_reconciliation": True,
        }
    if command == "init":
        source = read_json(cast("Path", arguments.input))
        return store.initialize(
            run_id=string_value(source.get("run_id"), "run_id"),
            coordinator_id=string_value(source.get("coordinator_id"), "coordinator_id"),
            authorization_reference=string_value(
                source.get("authorization_reference"), "authorization_reference"
            ),
            allowed_issues=issue_numbers(source.get("allowed_issues"), "allowed_issues"),
            mode=string_value(source.get("mode", "rehearsal"), "mode"),
        )
    if command == "apply":
        return store.apply(
            run_id=cast("str", arguments.run_id),
            coordinator_id=cast("str", arguments.coordinator_id),
            expected_revision=cast("int", arguments.expected_revision),
            operation=read_json(cast("Path", arguments.input)),
        )
    if command == "assess-merge":
        state = store.read()
        assignments = object_value(state["assignments"], "assignments")
        key = str(integer_value(cast("int", arguments.issue), "issue", 1))
        assignment = object_value(assignments.get(key), "assigned issue")
        observation = read_json(cast("Path", arguments.observation))
        assessment = assess_merge(assignment, observation)
        if assignment["merge_state"] in ("uncertain", "merged"):
            return {
                "verdict": "blocked",
                "reasons": [
                    "Reconcile uncertain or completed merge state before any further attempt."
                ],
                "merge_authorized_by_helper": False,
            }
        return {**asdict(assessment), "merge_authorized_by_helper": False}
    raise ValueError(f"unsupported command: {command}")


def run(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        result = _execute(options)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 1 if result.get("all_passed") is False else 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "error", "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
