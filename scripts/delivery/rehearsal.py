"""Run deterministic local examples without starting workers or touching GitHub."""

import tempfile
from contextlib import suppress
from copy import deepcopy
from pathlib import Path

from model import assess_merge, object_value
from state import StateStore

BASE = "a" * 40
HEAD = "b" * 40
UPDATED = "2026-10-29T12:00:00Z"


def _assignment() -> dict[str, object]:
    receipt: dict[str, object] = {
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "verdict": "ready",
        "reference": "rehearsal:review",
        "findings": [],
        "reviewer_id": "synthetic-independent-reviewer",
    }
    check: dict[str, object] = {
        "name": "Quality",
        "base_sha": BASE,
        "head_sha": HEAD,
        "conclusion": "success",
        "applicable": True,
        "explanation": "",
        "reference": "rehearsal:check",
    }
    return {
        "issue": 125,
        "worker_id": "synthetic-worker",
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "blockers": [],
        "required_checks": ["Quality"],
        "evidence": {
            "acceptance": deepcopy(receipt),
            "documentation": deepcopy(receipt),
            "code_review": deepcopy(receipt),
            "dx_review": deepcopy(receipt),
            "checks": [deepcopy(check)],
            "coderabbit": {**check, "analysis_completed": True, "findings": []},
        },
    }


def rehearse() -> dict[str, object]:
    """Exercise actual helper policy on clearly marked, disposable synthetic data."""
    scenarios: list[dict[str, object]] = []
    observation: dict[str, object] = {
        "required_checks": ["Quality"],
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "draft": False,
        "mergeable": True,
        "unresolved_review_threads": 0,
    }

    def record(name: str, expected: str, actual: str) -> None:
        scenarios.append(
            {"name": name, "expected": expected, "observed": actual, "passed": expected == actual}
        )

    record("complete-current-evidence", "ready", assess_merge(_assignment(), observation).verdict)
    for role in ("documentation", "dx_review"):
        assignment = _assignment()
        del object_value(assignment["evidence"], "evidence")[role]
        record(f"missing-{role}", "pending", assess_merge(assignment, observation).verdict)
    for field, changed in (
        ("head_sha", "c" * 40),
        ("base_sha", "d" * 40),
        ("issue_updated_at", "changed"),
    ):
        record(
            f"changed-{field}",
            "pending",
            assess_merge(_assignment(), {**observation, field: changed}).verdict,
        )
    assignment = _assignment()
    evidence = object_value(assignment["evidence"], "evidence")
    object_value(evidence["coderabbit"], "coderabbit")["conclusion"] = "rate_limited"
    record("coderabbit-rate-limit", "pending", assess_merge(assignment, observation).verdict)
    assignment = _assignment()
    assignment["blockers"] = ["Unresolved native dependency"]
    record("native-dependency", "blocked", assess_merge(assignment, observation).verdict)
    assignment = _assignment()
    evidence = object_value(assignment["evidence"], "evidence")
    for role in ("code_review", "dx_review"):
        object_value(evidence[role], role)["findings"] = [
            {"id": "same-id", "priority": 2, "resolved": False}
        ]
    risk = {
        "role": "code_review",
        "review_reference": "rehearsal:review",
        "finding_id": "same-id",
        "priority": 2,
        "verified_human": True,
        "source": "direct_user_instruction",
        "accepted_by": "synthetic-human",
        "reference": "rehearsal:human",
        "bounded_risk": "Only the code finding.",
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
    }
    record(
        "risk-cannot-cross-review-role",
        "blocked",
        assess_merge(assignment, {**observation, "human_risk_acceptances": [risk]}).verdict,
    )
    with tempfile.TemporaryDirectory(prefix="inframeld-delivery-rehearsal-") as directory:
        store = StateStore(Path(directory) / "state.json")
        store.initialize(
            run_id="synthetic-run",
            coordinator_id="synthetic-coordinator",
            authorization_reference="rehearsal:synthetic-instruction",
            allowed_issues=[125, 158],
        )

        def apply(revision: int, operation: dict[str, object]) -> dict[str, object]:
            return store.apply(
                run_id="synthetic-run",
                coordinator_id="synthetic-coordinator",
                expected_revision=revision,
                operation=operation,
            )

        claim: dict[str, object] = {
            "op": "claim",
            "issue": 125,
            "worker_id": "synthetic-worker",
            "branch": "synthetic-125",
            "worktree": "/synthetic/worktree/125",
            "paths": ["synthetic/feature"],
            "contracts": [],
            "base_sha": BASE,
            "head_sha": HEAD,
            "issue_updated_at": UPDATED,
            "required_checks": ["Quality"],
            "blockers": [],
        }
        apply(0, claim)
        for name, revision, operation in (
            ("duplicate-claim", 1, claim),
            ("stale-update", 0, {**claim, "issue": 158}),
        ):
            try:
                apply(revision, operation)
                result = "accepted"
            except ValueError:
                result = "rejected"
            record(name, "rejected", result)
        apply(
            1,
            {
                "op": "reserve",
                "issue": 125,
                "resource": "integration",
                "token": "synthetic-token",
                "head_sha": HEAD,
                "operation": "review",
                "reference": "rehearsal:reservation",
            },
        )
        with suppress(ValueError):
            apply(
                2,
                {
                    "op": "release",
                    "resource": "integration",
                    "token": "synthetic-token",
                    "cleanup": "unknown",
                    "head_sha": HEAD,
                    "reference": "rehearsal:cleanup",
                },
            )
        record(
            "unknown-cleanup",
            "occupied",
            "occupied" if object_value(store.read()["resources"], "resources") else "free",
        )
        apply(
            2,
            {
                "op": "observe_merge",
                "issue": 125,
                "status": "uncertain",
                "head_sha": HEAD,
                "source": "github",
                "pr": 999999,
                "reference": "https://github.com/matejpalenik/inframeld/pull/999999",
                "observed_at": UPDATED,
            },
        )
        assignments = object_value(store.read()["assignments"], "assignments")
        record(
            "uncertain-merge",
            "uncertain",
            str(object_value(assignments["125"], "assignment")["merge_state"]),
        )
        binding: dict[str, object] = {
            "base_sha": BASE,
            "head_sha": HEAD,
            "issue_updated_at": UPDATED,
        }
        cleanup: dict[str, object] = {
            **binding,
            "worker_id": "synthetic-worker",
            "worktree": "/synthetic/worktree/125",
            "branch": "synthetic-125",
            "stopped": True,
            "cleanup": "verified_clean",
            "verified_by_coordinator": True,
            "reference": "rehearsal:verified-stop",
        }
        try:
            apply(3, {"op": "retire", "issue": 125, **binding, "stop_cleanup": cleanup})
            result = "accepted"
        except ValueError:
            result = "rejected"
        record("uncertain-owner-stays-occupied", "rejected", result)
        apply(
            3,
            {
                "op": "observe_merge",
                "issue": 125,
                "status": "not_merged",
                "head_sha": HEAD,
                "source": "github",
                "pr": 999999,
                "reference": "https://github.com/matejpalenik/inframeld/pull/999999",
                "observed_at": UPDATED,
            },
        )
        apply(
            4,
            {
                "op": "release",
                "resource": "integration",
                "token": "synthetic-token",
                "head_sha": HEAD,
                "cleanup": "verified_clean",
                "reference": "rehearsal:verified-cleanup",
            },
        )
        state = apply(
            5,
            {
                "op": "amend",
                "issue": 125,
                **binding,
                "changes": {"paths": ["synthetic/amended"]},
                "reference": "rehearsal:amended-scope",
            },
        )
        assignment = object_value(
            object_value(state["assignments"], "assignments")["125"], "assignment"
        )
        record(
            "atomic-scope-amendment",
            "updated",
            "updated" if assignment["paths"] == ["synthetic/amended"] else "stale",
        )
        state = apply(
            6,
            {
                "op": "adopt",
                "issue": 125,
                **binding,
                "worker_id": "synthetic-replacement",
                "worktree": "/synthetic/replacement",
                "branch": "synthetic-replacement-125",
                "stop_cleanup": cleanup,
            },
        )
        assignment = object_value(
            object_value(state["assignments"], "assignments")["125"], "assignment"
        )
        record("verified-owner-adoption", "synthetic-replacement", str(assignment["worker_id"]))
        replacement_cleanup = {
            **cleanup,
            "worker_id": "synthetic-replacement",
            "worktree": "/synthetic/replacement",
            "branch": "synthetic-replacement-125",
        }
        apply(7, {"op": "retire", "issue": 125, **binding, "stop_cleanup": replacement_cleanup})
        state = apply(
            8,
            {
                **claim,
                "issue": 158,
                "worker_id": "synthetic-replacement",
                "worktree": "/synthetic/replacement",
                "branch": "synthetic-replacement-125",
                "paths": ["synthetic/amended"],
            },
        )
        record(
            "verified-retirement-releases-claims",
            "claimed-next-issue",
            "claimed-next-issue"
            if "158" in object_value(state["assignments"], "assignments")
            else "occupied",
        )
    return {
        "schema_version": 1,
        "mode": "rehearsal",
        "all_passed": all(item["passed"] is True for item in scenarios),
        "scenarios": scenarios,
        "github_reads": 0,
        "github_mutations": 0,
        "workers_started": 0,
        "product_operations": 0,
        "live_goal_created": False,
        "temporary_records_removed": True,
    }
