"""Exercise delivery decisions using synthetic facts and disposable local records."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest.mock import patch

from cli import run
from github import GitHubClient
from model import assess_merge, assess_prerequisite, list_value, object_value
from planner import create_plan
from state import StateStore, validate_state

BASE = "a" * 40
HEAD = "b" * 40
UPDATED = "2026-10-29T12:00:00Z"


def receipt() -> dict[str, object]:
    return {
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "verdict": "ready",
        "reference": "synthetic:review",
        "findings": [],
        "reviewer_id": "independent-reviewer",
    }


def passing_assignment() -> dict[str, object]:
    check = {
        "name": "Quality",
        "base_sha": BASE,
        "head_sha": HEAD,
        "conclusion": "success",
        "applicable": True,
        "explanation": "",
        "reference": "synthetic:check",
    }
    return {
        "issue": 125,
        "worker_id": "worker-125",
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "blockers": [],
        "required_checks": ["Quality"],
        "evidence": {
            "acceptance": receipt(),
            "documentation": receipt(),
            "code_review": receipt(),
            "dx_review": receipt(),
            "checks": [check],
            "coderabbit": {
                **check,
                "name": "CodeRabbit",
                "issue_updated_at": UPDATED,
                "status": "completed",
                "comments": [],
            },
        },
    }


def observation() -> dict[str, object]:
    return {
        "required_checks": ["Quality"],
        "base_sha": BASE,
        "head_sha": HEAD,
        "issue_updated_at": UPDATED,
        "draft": False,
        "mergeable": True,
        "unresolved_review_threads": 0,
    }


def prerequisite_packet() -> dict[str, object]:
    scope = "Provide transient recipient proof without saved login management."
    remaining = ["Credential storage, refresh and logout remain undelivered."]
    evidence = deepcopy(object_value(passing_assignment()["evidence"], "evidence"))
    for role in ("acceptance", "documentation", "code_review", "dx_review"):
        object_value(evidence[role], role).update({"pr": 273, "scope": scope})
    return {
        "pr": 273,
        "scope": scope,
        "remaining_acceptance": remaining,
        "scope_review": {
            **receipt(),
            "scope": scope,
            "remaining_acceptance": remaining,
            "deferred_blockers": [82, 159],
            "dependency_rationale": "Reviewed explicit host context needs neither saved selection nor admission creation.",
        },
        "evidence": evidence,
        "observation": {**observation(), "pr": 273, "closing_issues": []},
    }


class PrerequisiteAssessmentTests(unittest.TestCase):
    def test_reviewed_support_can_be_ready_while_feature_stays_blocked(self) -> None:
        assignment = {**passing_assignment(), "blockers": [82, 159]}
        before = deepcopy(assignment)
        self.assertEqual(assess_prerequisite(assignment, prerequisite_packet()).verdict, "ready")
        self.assertEqual(assignment, before)
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_missing_stale_or_worker_scope_review_cannot_approve_support(self) -> None:
        changes: list[dict[str, object]] = [
            {"verdict": "changes_needed"},
            {"head_sha": "c" * 40},
            {"reviewer_id": "worker-125"},
            {"deferred_blockers": [82]},
            {"remaining_acceptance": []},
            {"scope": "Different change"},
        ]
        for change in changes:
            with self.subTest(change=change):
                packet = prerequisite_packet()
                object_value(packet["scope_review"], "scope review").update(change)
                self.assertNotEqual(
                    assess_prerequisite(
                        {**passing_assignment(), "blockers": [82, 159]}, packet
                    ).verdict,
                    "ready",
                )

    def test_support_cannot_close_issues_or_reuse_unscoped_reviews(self) -> None:
        for kind in ("closing", "unscoped", "failed_ci", "material_finding"):
            with self.subTest(kind=kind):
                packet = prerequisite_packet()
                evidence = object_value(packet["evidence"], "evidence")
                if kind == "closing":
                    object_value(packet["observation"], "observation")["closing_issues"] = [125]
                elif kind == "unscoped":
                    object_value(evidence["acceptance"], "acceptance").pop("scope")
                elif kind == "failed_ci":
                    object_value(list_value(evidence["checks"], "checks")[0], "check")[
                        "conclusion"
                    ] = "failure"
                else:
                    object_value(packet["scope_review"], "scope review")["findings"] = [
                        {"id": "unsupported-boundary", "priority": 2, "resolved": False}
                    ]
                self.assertNotEqual(
                    assess_prerequisite(
                        {**passing_assignment(), "blockers": [82, 159]}, packet
                    ).verdict,
                    "ready",
                )

    def test_support_retains_current_checks_reviews_and_merge_uncertainty(self) -> None:
        for kind in ("stale", "checks", "worker", "retired", "uncertain"):
            with self.subTest(kind=kind):
                assignment = {**passing_assignment(), "blockers": [82, 159]}
                packet = prerequisite_packet()
                evidence = object_value(packet["evidence"], "evidence")
                if kind == "stale":
                    object_value(packet["observation"], "observation")["head_sha"] = "c" * 40
                elif kind == "checks":
                    object_value(packet["observation"], "observation")["required_checks"] = [
                        "New gate"
                    ]
                elif kind == "worker":
                    object_value(evidence["code_review"], "review")["reviewer_id"] = "worker-125"
                elif kind == "retired":
                    assignment["claim_state"] = "retired"
                else:
                    assignment["prerequisite_merges"] = {"272": {"status": "uncertain"}}
                self.assertNotEqual(assess_prerequisite(assignment, packet).verdict, "ready")


class MergeAssessmentTests(unittest.TestCase):
    def test_complete_current_evidence_is_ready(self) -> None:
        self.assertEqual(assess_merge(passing_assignment(), observation()).verdict, "ready")

    def test_changed_head_base_or_issue_scope_invalidates_evidence(self) -> None:
        for field, changed in [
            ("head_sha", "c" * 40),
            ("base_sha", "c" * 40),
            ("issue_updated_at", "later"),
        ]:
            with self.subTest(field=field):
                current = observation()
                current[field] = changed
                self.assertEqual(assess_merge(passing_assignment(), current).verdict, "pending")

    def test_missing_documentation_or_dx_review_is_pending(self) -> None:
        for role in ["documentation", "dx_review", "acceptance", "code_review"]:
            assignment = passing_assignment()
            evidence = object_value(assignment["evidence"], "evidence")
            del evidence[role]
            with self.subTest(role=role):
                self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")

    def test_reviewer_requested_changes_and_material_findings_block_merge(self) -> None:
        for priority in [0, 1, 2]:
            assignment = passing_assignment()
            evidence = object_value(assignment["evidence"], "evidence")
            evidence["code_review"] = {
                **receipt(),
                "findings": [{"id": "defect", "priority": priority, "resolved": False}],
            }
            with self.subTest(priority=priority):
                self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        evidence["dx_review"] = {**receipt(), "verdict": "changes_needed"}
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_only_recorded_bounded_p2_risk_acceptance_can_waive_a_finding(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        evidence["code_review"] = {
            **receipt(),
            "findings": [
                {
                    "id": "bounded",
                    "priority": 2,
                    "resolved": False,
                    "human_acceptance_reference": "human:explicit-bounded-risk",
                }
            ],
        }
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")
        current = observation()
        current["human_risk_acceptances"] = [
            {
                **receipt(),
                "finding_id": "bounded",
                "role": "code_review",
                "review_reference": "synthetic:review",
                "priority": 2,
                "verified_human": True,
                "source": "direct_user_instruction",
                "accepted_by": "project-owner",
                "reference": "conversation:owner-message",
                "bounded_risk": "The owner explicitly accepts this bounded P2 risk.",
            }
        ]
        self.assertEqual(assess_merge(assignment, current).verdict, "ready")
        current["human_risk_acceptances"][0]["source"] = "agent_message"
        self.assertEqual(assess_merge(assignment, current).verdict, "blocked")
        evidence["code_review"] = {
            **receipt(),
            "findings": [
                {
                    "id": "serious",
                    "priority": 1,
                    "resolved": False,
                    "human_acceptance_reference": "human:explicit-bounded-risk",
                }
            ],
        }
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_terminal_coderabbit_outcomes_are_advisory_and_preserve_raw_evidence(self) -> None:
        for conclusion in (
            "success",
            "failure",
            "timed_out",
            "startup_failure",
            "action_required",
            "neutral",
            "cancelled",
            "skipped",
            "rate_limited",
            "too_many_files",
            "unknown",
            None,
        ):
            assignment = passing_assignment()
            evidence = object_value(assignment["evidence"], "evidence")
            rabbit = object_value(evidence["coderabbit"], "coderabbit")
            rabbit["conclusion"] = conclusion
            rabbit["analysis_completed"] = False
            before = deepcopy(assignment)
            with self.subTest(conclusion=conclusion):
                self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")
                self.assertEqual(assignment, before)

    def test_coderabbit_active_unknown_or_missing_observation_remains_pending(self) -> None:
        for status in (
            "queued",
            "in_progress",
            "QUEUED",
            "IN_PROGRESS",
            "waiting",
            "pending",
            "requested",
            "unknown",
            None,
        ):
            assignment = passing_assignment()
            rabbit = object_value(
                object_value(assignment["evidence"], "evidence")["coderabbit"], "rabbit"
            )
            rabbit["status"] = status
            with self.subTest(status=status):
                self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        assignment = passing_assignment()
        del object_value(assignment["evidence"], "evidence")["coderabbit"]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")

    def test_explicitly_reconciled_unreported_coderabbit_is_skipped_without_a_new_run(self) -> None:
        assignment = passing_assignment()
        rabbit = object_value(
            object_value(assignment["evidence"], "evidence")["coderabbit"], "rabbit"
        )
        rabbit.update({"status": "not_reported", "conclusion": None, "comments": []})
        with patch("github.subprocess.run", side_effect=AssertionError("Never trigger CodeRabbit")):
            self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")
        rabbit["conclusion"] = "success"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")

    def test_coderabbit_observation_needs_current_binding_and_explicit_raw_fields(self) -> None:
        for changes in (
            {"base_sha": "c" * 40},
            {"head_sha": "c" * 40},
            {"issue_updated_at": "changed"},
            {"issue_updated_at": None},
            {"reference": ""},
        ):
            assignment = passing_assignment()
            rabbit = object_value(
                object_value(assignment["evidence"], "evidence")["coderabbit"], "rabbit"
            )
            rabbit.update(changes)
            with self.subTest(changes=changes):
                self.assertNotEqual(assess_merge(assignment, observation()).verdict, "ready")
        for missing in ("conclusion", "comments"):
            assignment = passing_assignment()
            del object_value(
                object_value(assignment["evidence"], "evidence")["coderabbit"], "rabbit"
            )[missing]
            with self.subTest(missing=missing):
                self.assertNotEqual(assess_merge(assignment, observation()).verdict, "ready")

    def test_substantive_bot_comments_need_explicit_current_independent_review_coverage(
        self,
    ) -> None:
        cases: tuple[tuple[dict[str, object], str], ...] = (
            ({}, "ready"),
            ({"head_sha": "c" * 40}, "pending"),
            ({"issue_updated_at": "changed"}, "pending"),
            ({"reviewer_id": "worker-125"}, "blocked"),
            ({"verdict": "blocked"}, "blocked"),
            ({"reviewed_comments": []}, "pending"),
            (
                {"reviewed_comments": [{"id": "other", "review_reference": "synthetic:check"}]},
                "pending",
            ),
            (
                {"reviewed_comments": [{"id": "bot-1", "review_reference": "wrong-origin"}]},
                "pending",
            ),
        )
        for changes, expected in cases:
            assignment = passing_assignment()
            evidence = object_value(assignment["evidence"], "evidence")
            rabbit = object_value(evidence["coderabbit"], "rabbit")
            rabbit.update(
                {
                    "conclusion": "failure",
                    "comments": ["bot-1"],
                    "local_review_reference": "synthetic:review",
                }
            )
            review = object_value(evidence["code_review"], "review")
            review["reviewed_comments"] = [{"id": "bot-1", "review_reference": "synthetic:check"}]
            review.update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(assess_merge(assignment, observation()).verdict, expected)

    def test_bot_comment_coverage_can_dismiss_suggestions_without_inventing_findings(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        rabbit = object_value(evidence["coderabbit"], "rabbit")
        rabbit.update({"comments": ["bot-1"], "local_review_reference": "synthetic:review"})
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        review = object_value(evidence["dx_review"], "review")
        review["reviewed_comments"] = [{"id": "bot-1", "review_reference": "synthetic:check"}]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")
        review["findings"] = [{"id": "accepted-material-concern", "priority": 1, "resolved": False}]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_every_substantive_comment_must_be_covered_by_the_referenced_local_review(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        rabbit = object_value(evidence["coderabbit"], "rabbit")
        rabbit.update(
            {"comments": ["bot-1", "bot-2"], "local_review_reference": "synthetic:review"}
        )
        review = object_value(evidence["code_review"], "review")
        review["reviewed_comments"] = [{"id": "bot-1", "review_reference": "synthetic:check"}]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        review["reviewed_comments"].append({"id": "bot-2", "review_reference": "synthetic:check"})
        rabbit["local_review_reference"] = "unrelated-review"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        rabbit["local_review_reference"] = "synthetic:review"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")

    def test_advisory_bot_never_relaxes_other_required_ci_or_local_gates(self) -> None:
        for role in ("acceptance", "documentation", "code_review", "dx_review"):
            assignment = passing_assignment()
            del object_value(assignment["evidence"], "evidence")[role]
            with self.subTest(role=role):
                self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        for conclusion, expected in (("failure", "blocked"), ("neutral", "pending")):
            assignment = passing_assignment()
            checks = list_value(
                object_value(assignment["evidence"], "evidence")["checks"], "checks"
            )
            object_value(checks[0], "check")["conclusion"] = conclusion
            with self.subTest(conclusion=conclusion):
                self.assertEqual(assess_merge(assignment, observation()).verdict, expected)

    def test_actually_required_coderabbit_status_is_separate_from_advisory_analysis(self) -> None:
        for status, conclusion, expected in (
            ("completed", "success", "ready"),
            ("completed", "neutral", "ready"),
            ("completed", "skipped", "ready"),
            ("COMPLETED", "SKIPPED", "ready"),
            ("completed", "failure", "blocked"),
            ("completed", "rate_limited", "pending"),
            ("completed", None, "pending"),
            ("queued", "success", "pending"),
            ("in_progress", "skipped", "pending"),
            (None, "success", "pending"),
        ):
            assignment = passing_assignment()
            assignment["required_checks"] = ["Quality", "CodeRabbit"]
            evidence = object_value(assignment["evidence"], "evidence")
            object_value(evidence["coderabbit"], "rabbit")["conclusion"] = "failure"
            list_value(evidence["checks"], "checks").append(
                {
                    "name": "CodeRabbit",
                    "base_sha": BASE,
                    "head_sha": HEAD,
                    "reference": "synthetic:actual-required-status",
                    "status": status,
                    "conclusion": conclusion,
                    "applicable": True,
                }
            )
            current = {**observation(), "required_checks": ["Quality", "CodeRabbit"]}
            with self.subTest(status=status, conclusion=conclusion):
                self.assertEqual(assess_merge(assignment, current).verdict, expected)

    def test_skipped_check_needs_explicit_non_applicability(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        checks = [object_value(item, "check") for item in list_value(evidence["checks"], "checks")]
        checks[0]["conclusion"] = "skipped"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")
        checks[0]["applicable"] = False
        checks[0]["explanation"] = "The unchanged dependency input group did not apply."
        self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")

    def test_conflicts_failures_and_unknown_mergeability_are_never_ready(self) -> None:
        assignment = passing_assignment()
        assignment["blockers"] = ["Unresolved authority decision"]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")
        current = observation()
        current["mergeable"] = None
        self.assertEqual(assess_merge(passing_assignment(), current).verdict, "pending")
        current = observation()
        current["unresolved_review_threads"] = 1
        self.assertEqual(assess_merge(passing_assignment(), current).verdict, "blocked")
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        checks = [object_value(item, "check") for item in list_value(evidence["checks"], "checks")]
        checks[0]["conclusion"] = "failure"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_malformed_or_duplicate_check_evidence_is_rejected(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        checks = [object_value(item, "check") for item in list_value(evidence["checks"], "checks")]
        checks.append(deepcopy(checks[0]))
        evidence["checks"] = checks
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_optional_p3_does_not_block_delivery(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        evidence["dx_review"] = {
            **receipt(),
            "findings": [{"id": "optional", "priority": 3, "resolved": False}],
        }
        self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")

    def test_worker_cannot_supply_its_own_independent_reviews(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        object_value(evidence["code_review"], "review")["reviewer_id"] = "worker-125"
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")

    def test_required_check_scope_and_unreviewed_coderabbit_comments_fail_closed(self) -> None:
        current = observation()
        current["required_checks"] = ["Quality", "Security"]
        self.assertEqual(assess_merge(passing_assignment(), current).verdict, "pending")
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        rabbit = object_value(evidence["coderabbit"], "coderabbit")
        rabbit["comments"] = ["rabbit-p1"]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "pending")

    def test_risk_acceptance_cannot_waive_another_role_or_review_with_same_finding_id(self) -> None:
        assignment = passing_assignment()
        evidence = object_value(assignment["evidence"], "evidence")
        for role in ("code_review", "dx_review"):
            evidence[role] = {
                **receipt(),
                "reference": f"synthetic:{role}",
                "findings": [{"id": "shared-id", "priority": 2, "resolved": False}],
            }
        current = observation()
        risk: dict[str, object] = {
            **receipt(),
            "finding_id": "shared-id",
            "role": "code_review",
            "review_reference": "synthetic:code_review",
            "priority": 2,
            "verified_human": True,
            "source": "direct_user_instruction",
            "accepted_by": "owner",
            "reference": "conversation:human",
            "bounded_risk": "Code review risk only.",
        }
        current["human_risk_acceptances"] = [risk]
        self.assertEqual(assess_merge(assignment, current).verdict, "blocked")
        object_value(evidence["dx_review"], "dx")["findings"] = []
        self.assertEqual(assess_merge(assignment, current).verdict, "ready")
        risk["review_reference"] = "synthetic:another-review"
        self.assertEqual(assess_merge(assignment, current).verdict, "blocked")

    def test_duplicate_finding_ids_within_a_receipt_are_rejected(self) -> None:
        assignment = passing_assignment()
        review = object_value(
            object_value(assignment["evidence"], "evidence")["code_review"], "review"
        )
        review["findings"] = [
            {"id": "duplicate", "priority": 3, "resolved": False},
            {"id": "duplicate", "priority": 3, "resolved": False},
        ]
        self.assertEqual(assess_merge(assignment, observation()).verdict, "blocked")


class StateTests(unittest.TestCase):
    def test_initialization_persists_the_finite_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            StateStore(path).initialize(
                run_id="trial",
                coordinator_id="coordinator",
                authorization_reference="synthetic:human-instruction",
                allowed_issues=[125, 158],
            )
            self.assertTrue(path.is_file())
            state = json.loads(path.read_text())
            self.assertEqual(state["allowed_issues"], [125, 158])
            self.assertEqual(state["revision"], 0)

    def test_initialization_rejects_a_state_inside_a_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            checkout.mkdir()
            (checkout / ".git").write_text("gitdir: /somewhere")
            with self.assertRaisesRegex(ValueError, "outside"):
                StateStore(checkout / "state.json").initialize(
                    run_id="trial",
                    coordinator_id="coordinator",
                    authorization_reference="synthetic:human",
                    allowed_issues=[125],
                )

    def test_initialization_rejects_duplicate_or_invalid_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for issues in [[125, 125], [0], cast("list[int]", [True])]:
                with self.subTest(issues=issues), self.assertRaises(ValueError):
                    StateStore(Path(directory) / "state.json").initialize(
                        run_id="trial",
                        coordinator_id="coordinator",
                        authorization_reference="synthetic:human",
                        allowed_issues=issues,
                    )

    def make_store(self, directory: str) -> StateStore:
        store = StateStore(Path(directory) / "state.json")
        store.initialize(
            run_id="trial",
            coordinator_id="coordinator",
            authorization_reference="synthetic:human",
            allowed_issues=[125, 158],
        )
        return store

    def claim(self, issue: int = 125, **changes: object) -> dict[str, object]:
        return {
            "op": "claim",
            "issue": issue,
            "worker_id": f"worker-{issue}",
            "worktree": f"/synthetic/worktrees/{issue}",
            "branch": f"issue-{issue}",
            "paths": [f"features/{issue}"],
            "contracts": [],
            "base_sha": BASE,
            "head_sha": HEAD,
            "issue_updated_at": UPDATED,
            "required_checks": ["Quality"],
            "blockers": [],
            **changes,
        }

    def apply(
        self, store: StateStore, revision: int, operation: dict[str, object]
    ) -> dict[str, object]:
        return store.apply(
            run_id="trial",
            coordinator_id="coordinator",
            expected_revision=revision,
            operation=operation,
        )

    def test_claims_are_exclusive_and_stale_updates_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            with self.assertRaisesRegex(ValueError, "revision"):
                self.apply(store, 0, self.claim(158))
            with self.assertRaisesRegex(ValueError, "claimed"):
                self.apply(store, 1, self.claim())
            with self.assertRaisesRegex(ValueError, "scope"):
                self.apply(store, 1, self.claim(999))
            with self.assertRaisesRegex(ValueError, "overlap"):
                self.apply(store, 1, self.claim(158, paths=["features/125/child"]))
            with self.assertRaisesRegex(ValueError, "worktree"):
                self.apply(store, 1, self.claim(158, worktree="/synthetic/worktrees/125"))
            state = self.apply(store, 1, self.claim(158))
            self.assertEqual(state["revision"], 2)
            self.assertEqual(len(object_value(state["assignments"], "assignments")), 2)

    def test_wrong_run_or_coordinator_cannot_mutate_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            for run_id, owner in [("other", "coordinator"), ("trial", "worker")]:
                with (
                    self.subTest(run_id=run_id, owner=owner),
                    self.assertRaisesRegex(ValueError, "identity"),
                ):
                    store.apply(
                        run_id=run_id,
                        coordinator_id=owner,
                        expected_revision=0,
                        operation=self.claim(),
                    )
            self.assertEqual(store.read()["revision"], 0)

    def test_atomic_write_interruption_preserves_previous_valid_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            before = store.path.read_bytes()
            with (
                patch("state.os.replace", side_effect=OSError("simulated interruption")),
                self.assertRaises(OSError),
            ):
                self.apply(store, 0, self.claim())
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.read()["revision"], 0)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_corrupt_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            for content in ['{"schema_version":1,"schema_version":1}', '{"revision":NaN}', "{}"]:
                store.path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    store.read()

    def test_resource_unknown_cleanup_stays_occupied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            self.apply(store, 1, self.claim(158))
            reserve: dict[str, object] = {
                "op": "reserve",
                "issue": 125,
                "resource": "integration",
                "token": "lease-1",
                "head_sha": HEAD,
                "operation": "review",
                "reference": "synthetic:reservation",
            }
            self.apply(store, 2, reserve)
            with self.assertRaisesRegex(ValueError, "occupied"):
                self.apply(store, 3, {**reserve, "issue": 158, "token": "lease-2"})
            for cleanup in ["unknown", "dirty"]:
                with self.subTest(cleanup=cleanup), self.assertRaisesRegex(ValueError, "cleanup"):
                    self.apply(
                        store,
                        3,
                        {
                            "op": "release",
                            "resource": "integration",
                            "token": "lease-1",
                            "cleanup": cleanup,
                            "head_sha": HEAD,
                            "reference": "synthetic:cleanup",
                        },
                    )
            self.assertEqual(store.read()["revision"], 3)
            state = self.apply(
                store,
                3,
                {
                    "op": "release",
                    "resource": "integration",
                    "token": "lease-1",
                    "cleanup": "verified_clean",
                    "head_sha": HEAD,
                    "reference": "synthetic:cleanup",
                },
            )
            self.assertEqual(state["resources"], {})

    def test_rebase_invalidates_previous_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            state = self.apply(
                store,
                1,
                {
                    "op": "evidence",
                    "issue": 125,
                    "evidence": passing_assignment()["evidence"],
                    "base_sha": BASE,
                    "head_sha": HEAD,
                    "issue_updated_at": UPDATED,
                },
            )
            assignment = object_value(
                object_value(state["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assess_merge(assignment, observation()).verdict, "ready")
            state = self.apply(
                store,
                2,
                {
                    "op": "revise",
                    "issue": 125,
                    "base_sha": "c" * 40,
                    "head_sha": "d" * 40,
                    "issue_updated_at": UPDATED,
                },
            )
            self.assertEqual(
                assess_merge(
                    object_value(
                        object_value(state["assignments"], "assignments")["125"], "assignment"
                    ),
                    observation(),
                ).verdict,
                "pending",
            )
            with self.assertRaisesRegex(ValueError, "stale"):
                self.apply(
                    store,
                    3,
                    {
                        "op": "evidence",
                        "issue": 125,
                        "evidence": {},
                        "base_sha": BASE,
                        "head_sha": HEAD,
                        "issue_updated_at": UPDATED,
                    },
                )

    def test_supporting_merge_keeps_feature_open_and_preserves_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim(blockers=[82, 159]))
            operation: dict[str, object] = {
                "op": "observe_prerequisite_merge",
                "issue": 125,
                "pr": 273,
                "status": "uncertain",
                "source": "github",
                "head_sha": HEAD,
                "base_sha": BASE,
                "issue_updated_at": UPDATED,
                "reference": "https://github.com/matejpalenik/inframeld/pull/273",
                "observed_at": UPDATED,
                "scope": "Transient recipient proof",
                "assessment_reference": "synthetic:reviewed-support-packet",
            }
            self.apply(store, 1, operation)
            with self.assertRaisesRegex(ValueError, "uncertain"):
                self.apply(
                    store,
                    2,
                    {
                        "op": "revise",
                        "issue": 125,
                        "base_sha": BASE,
                        "head_sha": "c" * 40,
                        "issue_updated_at": UPDATED,
                    },
                )
            current = store.read()
            self.assertEqual(current["schema_version"], 2)
            with self.assertRaisesRegex(ValueError, "schema_version 2"):
                validate_state({**current, "schema_version": 1})
            assignment = object_value(
                object_value(current["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(
                assess_merge({**passing_assignment(), **assignment}, observation()).verdict,
                "blocked",
            )
            current = self.apply(store, 2, {**operation, "status": "merged", "merge_sha": "e" * 40})
            assignment = object_value(
                object_value(current["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assignment["merge_state"], "unmerged")
            self.assertEqual(assignment["blockers"], [82, 159])
            self.assertEqual(current["merge_observations"], {})
            with self.assertRaisesRegex(ValueError, "merged"):
                self.apply(store, 3, {**operation, "status": "not_merged"})
            current = self.apply(
                store,
                3,
                {
                    "op": "revise",
                    "issue": 125,
                    "base_sha": BASE,
                    "head_sha": "c" * 40,
                    "issue_updated_at": UPDATED,
                },
            )
            assignment = object_value(
                object_value(current["assignments"], "assignments")["125"], "assignment"
            )
            self.assertIn(
                "273", object_value(assignment["prerequisite_merges"], "supporting merges")
            )

    def test_unmerged_support_can_be_rebased_and_later_recorded_as_merged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            operation: dict[str, object] = {
                "op": "observe_prerequisite_merge",
                "issue": 125,
                "pr": 273,
                "status": "uncertain",
                "source": "github",
                "head_sha": HEAD,
                "base_sha": BASE,
                "issue_updated_at": UPDATED,
                "reference": "https://github.com/matejpalenik/inframeld/pull/273",
                "observed_at": UPDATED,
                "scope": "Transient recipient proof",
                "assessment_reference": "synthetic:original-scope-review",
            }
            self.apply(store, 1, operation)
            with self.assertRaisesRegex(ValueError, "preserve"):
                self.apply(
                    store, 2, {**operation, "status": "not_merged", "scope": "Changed scope"}
                )
            self.apply(store, 2, {**operation, "status": "not_merged"})
            revised = {"base_sha": "c" * 40, "head_sha": "d" * 40, "issue_updated_at": "later"}
            self.apply(store, 3, {"op": "revise", "issue": 125, **revised})
            state = self.apply(
                store,
                4,
                {
                    **operation,
                    **revised,
                    "status": "merged",
                    "merge_sha": "e" * 40,
                    "assessment_reference": "synthetic:refreshed-scope-review",
                },
            )
            assignment = object_value(
                object_value(state["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assignment["merge_state"], "unmerged")
            merged = object_value(
                object_value(assignment["prerequisite_merges"], "supporting merges")["273"],
                "merged",
            )
            self.assertEqual(merged["status"], "merged")
            self.assertEqual(merged["head_sha"], revised["head_sha"])
            self.assertEqual(len(list_value(assignment["history"], "history")), 4)

    def test_uncertain_merge_requires_observed_github_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            observe: dict[str, object] = {
                "op": "observe_merge",
                "issue": 125,
                "status": "uncertain",
                "head_sha": HEAD,
                "source": "github",
                "pr": 273,
                "reference": "https://github.com/matejpalenik/inframeld/pull/273",
                "observed_at": UPDATED,
            }
            self.apply(store, 1, observe)
            with self.assertRaisesRegex(ValueError, "uncertain"):
                self.apply(
                    store,
                    2,
                    {
                        "op": "revise",
                        "issue": 125,
                        "base_sha": BASE,
                        "head_sha": "c" * 40,
                        "issue_updated_at": UPDATED,
                    },
                )
            with self.assertRaisesRegex(ValueError, "merge_sha"):
                self.apply(store, 2, {**observe, "status": "merged"})
            state = self.apply(store, 2, {**observe, "status": "merged", "merge_sha": "e" * 40})
            self.assertEqual(
                object_value(
                    object_value(state["assignments"], "assignments")["125"], "assignment"
                )["merge_state"],
                "merged",
            )

    def test_concurrent_process_claims_cannot_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            operations: list[Path] = []
            for issue in (125, 158):
                path = Path(directory) / f"claim-{issue}.json"
                path.write_text(json.dumps(self.claim(issue)))
                operations.append(path)

            def invoke(path: Path) -> int:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).with_name("cli.py")),
                        "apply",
                        "--state",
                        str(store.path),
                        "--run-id",
                        "trial",
                        "--coordinator-id",
                        "coordinator",
                        "--expected-revision",
                        "0",
                        "--input",
                        str(path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                return result.returncode

            with ThreadPoolExecutor(max_workers=2) as executor:
                codes = list(executor.map(invoke, operations))
            self.assertEqual(sorted(codes), [0, 2])
            state = store.read()
            self.assertEqual(state["revision"], 1)
            self.assertEqual(len(object_value(state["assignments"], "assignments")), 1)

    def test_shared_contract_claims_remain_exclusive_after_owner_goes_idle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim(contracts=["public-sdk-session"]))
            with self.assertRaisesRegex(ValueError, "overlap"):
                self.apply(store, 1, self.claim(158, contracts=["public-sdk-session"]))
            self.assertEqual(store.read()["revision"], 1)

    def test_symlink_state_and_unsafe_claim_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            link = Path(directory) / "linked.json"
            link.symlink_to(store.path)
            with self.assertRaisesRegex(ValueError, "symlink"):
                StateStore(link)
            for path in ["../outside", "/absolute", "app/**", "app/../other"]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.apply(store, 0, self.claim(paths=[path]))
            self.assertEqual(store.read()["revision"], 0)

    def binding(self) -> dict[str, object]:
        return {"base_sha": BASE, "head_sha": HEAD, "issue_updated_at": UPDATED}

    def stop_cleanup(self, **changes: object) -> dict[str, object]:
        return {
            **self.binding(),
            "worker_id": "worker-125",
            "worktree": "/synthetic/worktrees/125",
            "branch": "issue-125",
            "stopped": True,
            "cleanup": "verified_clean",
            "verified_by_coordinator": True,
            "reference": "synthetic:verified-stop-cleanup",
            **changes,
        }

    def merged(self, store: StateStore, revision: int = 1) -> dict[str, object]:
        return self.apply(
            store,
            revision,
            {
                "op": "observe_merge",
                "issue": 125,
                "status": "merged",
                "source": "github",
                "pr": 273,
                "head_sha": HEAD,
                "merge_sha": "e" * 40,
                "reference": "https://github.com/matejpalenik/inframeld/pull/273",
                "observed_at": UPDATED,
            },
        )

    def test_merge_retirement_frees_verified_ownership_and_keeps_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim(contracts=["public-contract"]))
            self.merged(store)
            with self.assertRaisesRegex(ValueError, "overlap"):
                self.apply(
                    store, 2, self.claim(158, paths=["features/125"], contracts=["public-contract"])
                )
            self.apply(
                store,
                2,
                {
                    "op": "retire",
                    "issue": 125,
                    **self.binding(),
                    "stop_cleanup": self.stop_cleanup(),
                },
            )
            state = self.apply(
                store,
                3,
                self.claim(
                    158,
                    worker_id="worker-125",
                    worktree="/synthetic/worktrees/125",
                    branch="issue-125",
                    paths=["features/125"],
                    contracts=["public-contract"],
                ),
            )
            retired = object_value(
                object_value(state["assignments"], "assignments")["125"], "retired"
            )
            self.assertEqual(retired["claim_state"], "retired")
            self.assertEqual(retired["merge_state"], "merged")
            self.assertTrue(list_value(retired["history"], "history"))

    def test_resource_or_unknown_cleanup_prevents_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            self.apply(
                store,
                1,
                {
                    "op": "reserve",
                    "issue": 125,
                    "resource": "integration",
                    "token": "lease",
                    "head_sha": HEAD,
                    "operation": "review",
                    "reference": "synthetic:reserve",
                },
            )
            self.merged(store, 2)
            with self.assertRaisesRegex(ValueError, "occupied"):
                self.apply(
                    store,
                    3,
                    {
                        "op": "retire",
                        "issue": 125,
                        **self.binding(),
                        "stop_cleanup": self.stop_cleanup(),
                    },
                )
            self.apply(
                store,
                3,
                {
                    "op": "release",
                    "resource": "integration",
                    "token": "lease",
                    "head_sha": HEAD,
                    "cleanup": "verified_clean",
                    "reference": "synthetic:cleanup",
                },
            )
            for changes in [
                {"cleanup": "unknown"},
                {"stopped": False},
                {"verified_by_coordinator": False},
                {"head_sha": "c" * 40},
                {"worker_id": "someone-else"},
            ]:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.apply(
                        store,
                        4,
                        {
                            "op": "retire",
                            "issue": 125,
                            **self.binding(),
                            "stop_cleanup": self.stop_cleanup(**changes),
                        },
                    )
            self.assertEqual(store.read()["revision"], 4)

    def test_revise_rejects_silently_ignored_ownership_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            with self.assertRaisesRegex(ValueError, "unknown"):
                self.apply(
                    store,
                    1,
                    {"op": "revise", "issue": 125, **self.binding(), "paths": ["different"]},
                )
            with self.assertRaisesRegex(ValueError, "unknown"):
                self.apply(store, 1, self.claim(158, unrecognized_receipt="ignored-before"))
            self.assertEqual(store.read()["revision"], 1)

    def test_amend_replaces_bounded_scope_and_invalidates_prior_evidence_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            self.apply(store, 1, self.claim(158))
            self.apply(
                store,
                2,
                {
                    "op": "evidence",
                    "issue": 125,
                    **self.binding(),
                    "evidence": passing_assignment()["evidence"],
                },
            )
            amend: dict[str, object] = {
                "op": "amend",
                "issue": 125,
                **self.binding(),
                "reference": "synthetic:scope-recheck",
                "changes": {
                    "paths": ["new/feature"],
                    "contracts": ["new-contract"],
                    "required_checks": ["Quality", "Security"],
                    "blockers": ["Needs decision"],
                },
            }
            state = self.apply(store, 3, amend)
            assignment = object_value(
                object_value(state["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assignment["paths"], ["new/feature"])
            self.assertEqual(assignment["required_checks"], ["Quality", "Security"])
            self.assertEqual(assignment["blockers"], ["Needs decision"])
            self.assertEqual(assignment["evidence"], {})
            with self.assertRaisesRegex(ValueError, "overlap"):
                self.apply(store, 4, {**amend, "changes": {"paths": ["features/158"]}})
            with self.assertRaisesRegex(ValueError, "unknown"):
                self.apply(store, 4, {**amend, "changes": {"worker_id": "unverified-owner"}})
            self.assertEqual(store.read()["revision"], 4)

    def test_adopt_requires_verified_old_owner_stop_and_clears_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            self.apply(
                store,
                1,
                {
                    "op": "evidence",
                    "issue": 125,
                    **self.binding(),
                    "evidence": passing_assignment()["evidence"],
                },
            )
            adopt: dict[str, object] = {
                "op": "adopt",
                "issue": 125,
                **self.binding(),
                "worker_id": "replacement",
                "worktree": "/synthetic/replacement",
                "branch": "replacement-125",
                "stop_cleanup": self.stop_cleanup(),
            }
            with self.assertRaises(ValueError):
                self.apply(store, 2, {**adopt, "stop_cleanup": self.stop_cleanup(stopped=False)})
            state = self.apply(store, 2, adopt)
            assignment = object_value(
                object_value(state["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assignment["worker_id"], "replacement")
            self.assertEqual(assignment["evidence"], {})
            self.apply(
                store,
                3,
                self.claim(
                    158,
                    worker_id="worker-125",
                    worktree="/synthetic/worktrees/125",
                    branch="issue-125",
                ),
            )

    def test_retired_unmerged_issue_can_be_adopted_but_merged_issue_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            self.apply(store, 0, self.claim())
            self.apply(
                store,
                1,
                {
                    "op": "retire",
                    "issue": 125,
                    **self.binding(),
                    "stop_cleanup": self.stop_cleanup(),
                },
            )
            state = self.apply(
                store,
                2,
                {
                    "op": "adopt",
                    "issue": 125,
                    **self.binding(),
                    "worker_id": "replacement",
                    "worktree": "/synthetic/replacement",
                    "branch": "replacement-125",
                    "stop_cleanup": self.stop_cleanup(),
                },
            )
            assignment = object_value(
                object_value(state["assignments"], "assignments")["125"], "assignment"
            )
            self.assertEqual(assignment["claim_state"], "active")
            self.merged(store, 3)
            with self.assertRaisesRegex(ValueError, "merged"):
                self.apply(
                    store,
                    4,
                    {
                        "op": "adopt",
                        "issue": 125,
                        **self.binding(),
                        "worker_id": "another",
                        "worktree": "/synthetic/another",
                        "branch": "another-125",
                        "stop_cleanup": self.stop_cleanup(),
                    },
                )


class PlanningTests(unittest.TestCase):
    def test_only_unblocked_unclaimed_non_decision_leaves_are_candidates(self) -> None:
        issues: list[dict[str, object]] = [
            {"number": 1, "title": "Ready", "labels": [], "blockers": [], "children": []},
            {"number": 2, "title": "Dependent", "labels": [], "blockers": [1], "children": []},
            {
                "number": 3,
                "title": "Decision",
                "labels": ["needs-decision"],
                "blockers": [],
                "children": [],
            },
            {"number": 4, "title": "Parent", "labels": ["epic"], "blockers": [], "children": [1]},
        ]
        plan = create_plan(issues)
        self.assertEqual(plan.get("candidate_issues"), [1])
        self.assertEqual(plan.get("code_independence_verified"), False)

    def test_source_decisions_external_dependencies_and_existing_prs_prevent_claims(self) -> None:
        issues: list[dict[str, object]] = [
            {
                "number": 1,
                "title": "Decision",
                "labels": ["needs-decision/source-scope"],
                "blockers": [],
                "children": [],
            },
            {
                "number": 2,
                "title": "External",
                "labels": [],
                "blockers": [],
                "children": [],
                "external_dependencies": [{"repository": "other/repo", "number": 1}],
            },
            {"number": 3, "title": "In PR", "labels": [], "blockers": [], "children": []},
        ]
        plan = create_plan(
            issues, open_prs=[{"number": 273, "issues": [3]}, {"number": 272, "issues": []}]
        )
        self.assertEqual(plan["candidate_issues"], [])
        self.assertEqual(plan["decision_issues"], [1])
        self.assertEqual(plan.get("unmapped_open_prs"), [272])

    def test_unlocks_do_not_claim_that_blocked_dependency_cycles_can_run(self) -> None:
        issues: list[dict[str, object]] = [
            {"number": 1, "title": "First", "labels": [], "blockers": [2], "children": []},
            {"number": 2, "title": "Second", "labels": [], "blockers": [1], "children": []},
        ]
        plan = create_plan(issues)
        self.assertEqual(plan["candidate_issues"], [])
        self.assertEqual(plan["direct_unlocks"], {"1": [2], "2": [1]})


class GitHubSnapshotTests(unittest.TestCase):
    def connection(
        self, nodes: list[dict[str, object]], cursor: str | None = None
    ) -> dict[str, object]:
        return {
            "nodes": nodes,
            "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
        }

    def test_all_issue_relation_label_and_pr_pages_are_captured(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        relation: dict[str, object] = {
            "number": 7,
            "state": "OPEN",
            "url": "synthetic:issue-7",
            "repository": {"nameWithOwner": "matejpalenik/inframeld"},
        }

        def transport(query: str, variables: dict[str, object]) -> dict[str, object]:
            calls.append((query, variables))
            if "query SnapshotIssues" in query:
                if variables.get("cursor") == "issue-next":
                    issues = self.connection([])
                else:
                    issues = self.connection(
                        [
                            {
                                "number": 1,
                                "title": "Feature",
                                "body": "Current scope",
                                "updatedAt": UPDATED,
                                "url": "synthetic:issue-1",
                                "state": "OPEN",
                                "parent": None,
                                "labels": self.connection([{"name": "feature"}], "labels-next"),
                                "blockedBy": self.connection([relation], "blocked-next"),
                                "blocking": self.connection([]),
                                "subIssues": self.connection([]),
                            }
                        ],
                        "issue-next",
                    )
                return {
                    "repository": {
                        "milestone": {"number": 1, "title": "v1", "state": "OPEN", "issues": issues}
                    }
                }
            if "query IssueRelation" in query:
                field = "labels" if "labels(first:" in query else "blockedBy"
                nodes: list[dict[str, object]] = (
                    [{"name": "needs-decision"}]
                    if field == "labels"
                    else [{**relation, "number": 8}]
                )
                return {"repository": {"issue": {field: self.connection(nodes)}}}
            if "query SnapshotPRs" in query:
                if variables.get("cursor") == "pr-next":
                    prs = self.connection([])
                else:
                    prs = self.connection(
                        [
                            {
                                "number": 273,
                                "url": "synthetic:pr-273",
                                "headRefName": "issue-1",
                                "baseRefName": "main",
                                "baseRefOid": BASE,
                                "headRefOid": HEAD,
                                "updatedAt": UPDATED,
                                "isDraft": False,
                                "closingIssuesReferences": self.connection(
                                    [relation], "closing-next"
                                ),
                            }
                        ],
                        "pr-next",
                    )
                return {"repository": {"pullRequests": prs}}
            if "query PRIssues" in query:
                return {
                    "repository": {
                        "pullRequest": {
                            "closingIssuesReferences": self.connection([{**relation, "number": 8}])
                        }
                    }
                }
            self.fail("Unexpected query")

        snapshot = GitHubClient(transport).snapshot()
        self.assertEqual(snapshot["repository"], "matejpalenik/inframeld")
        self.assertEqual(snapshot["milestone"], {"number": 1, "title": "v1", "state": "OPEN"})
        issue = object_value(list_value(snapshot["issues"], "issues")[0], "issue")
        self.assertEqual(issue["body"], "Current scope")
        self.assertEqual(issue["labels"], ["feature", "needs-decision"])
        self.assertEqual(issue["blockers"], [7, 8])
        self.assertEqual(
            object_value(list_value(snapshot["open_prs"], "prs")[0], "pr")["issues"], [7, 8]
        )
        self.assertEqual(len(calls), 7)

    def test_incomplete_or_wrong_milestone_snapshot_fails_closed(self) -> None:
        for milestone in [None, {"number": 1, "title": "other", "issues": self.connection([])}]:

            def transport(
                query: str, variables: dict[str, object], current: object = milestone
            ) -> dict[str, object]:
                return {"repository": {"milestone": current}}

            with self.subTest(milestone=milestone), self.assertRaises(ValueError):
                GitHubClient(transport).snapshot()

    def test_pagination_missing_cursor_cannot_silently_truncate(self) -> None:
        def transport(query: str, variables: dict[str, object]) -> dict[str, object]:
            return {
                "repository": {
                    "milestone": {
                        "number": 1,
                        "title": "v1",
                        "state": "OPEN",
                        "issues": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": True, "endCursor": None},
                        },
                    }
                }
            }

        with self.assertRaisesRegex(ValueError, "cursor"):
            GitHubClient(transport).snapshot()


class CliTests(unittest.TestCase):
    def test_supporting_assessment_is_read_only_and_never_completes_the_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateTests().make_store(directory)
            StateTests().apply(store, 0, StateTests().claim(blockers=[82, 159]))
            packet = Path(directory) / "packet.json"
            packet.write_text(json.dumps(prerequisite_packet()))
            state_path = Path(directory) / "state.json"
            before = state_path.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                code = run(
                    [
                        "assess-prerequisite",
                        "--state",
                        str(state_path),
                        "--issue",
                        "125",
                        "--packet",
                        str(packet),
                    ]
                )
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result["verdict"], "ready")
            self.assertFalse(result["issue_complete"])
            self.assertFalse(result["merge_authorized_by_helper"])
            self.assertEqual(state_path.read_bytes(), before)

    def invoke(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = run(arguments)
        return code, json.loads(output.getvalue())

    def test_rehearsal_is_explicitly_synthetic_and_performs_no_remote_action(self) -> None:
        with patch("github.subprocess.run", side_effect=AssertionError("No gh call in rehearsal")):
            code, report = self.invoke(["rehearse"])
        self.assertEqual(code, 0)
        self.assertEqual(report["mode"], "rehearsal")
        self.assertEqual(report["github_mutations"], 0)
        self.assertEqual(report["live_goal_created"], False)
        self.assertTrue(report["all_passed"])
        self.assertGreaterEqual(len(list_value(report["scenarios"], "scenarios")), 8)

    def test_status_reports_validated_record_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            StateStore(path).initialize(
                run_id="trial",
                coordinator_id="coordinator",
                authorization_reference="synthetic:human",
                allowed_issues=[125],
            )
            before = path.stat().st_mtime_ns
            code, result = self.invoke(["status", "--state", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(result["run_id"], "trial")
            self.assertEqual(path.stat().st_mtime_ns, before)
            self.assertFalse(result["merge_authorized_by_helper"])

    def test_invalid_state_returns_bounded_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            output = io.StringIO()
            with redirect_stderr(output):
                code = run(["status", "--state", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "error")

    def test_offline_snapshot_never_invokes_gh_and_retains_finite_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "repository": "matejpalenik/inframeld",
                        "milestone": {"number": 1, "title": "v1"},
                        "issues": [
                            {
                                "number": 125,
                                "title": "Ready",
                                "labels": [],
                                "blockers": [],
                                "children": [],
                            }
                        ],
                        "open_prs": [],
                        "allowed_issues": [125],
                    }
                )
            )
            with patch(
                "github.subprocess.run", side_effect=AssertionError("Offline plan must not call gh")
            ):
                code, report = self.invoke(
                    ["plan", "--snapshot", str(path), "--no-local-worktrees"]
                )
            self.assertEqual(code, 0)
            self.assertEqual(object_value(report["snapshot"], "snapshot")["allowed_issues"], [125])
            self.assertEqual(object_value(report["plan"], "plan")["candidate_issues"], [125])

    def test_plan_and_status_keep_merged_owner_until_verified_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = StateTests()
            store = runtime.make_store(directory)
            runtime.apply(store, 0, runtime.claim())
            runtime.merged(store)
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "repository": "matejpalenik/inframeld",
                        "milestone": {"number": 1, "title": "v1"},
                        "issues": [
                            {
                                "number": 125,
                                "title": "Observed source",
                                "labels": [],
                                "blockers": [],
                                "children": [],
                            }
                        ],
                        "open_prs": [],
                        "allowed_issues": [125],
                    }
                )
            )
            arguments = [
                "plan",
                "--snapshot",
                str(snapshot),
                "--state",
                str(store.path),
                "--no-local-worktrees",
            ]
            _, report = self.invoke(arguments)
            ownership = object_value(
                object_value(report["plan"], "plan")["existing_ownership"], "ownership"
            )
            self.assertIn("125", ownership)
            _, status = self.invoke(["status", "--state", str(store.path)])
            self.assertEqual(status.get("occupied_issues"), [125])
            runtime.apply(
                store,
                2,
                {
                    "op": "retire",
                    "issue": 125,
                    **runtime.binding(),
                    "stop_cleanup": runtime.stop_cleanup(),
                },
            )
            _, report = self.invoke(arguments)
            ownership = object_value(
                object_value(report["plan"], "plan")["existing_ownership"], "ownership"
            )
            self.assertNotIn("125", ownership)
            _, status = self.invoke(["status", "--state", str(store.path)])
            self.assertEqual(status.get("occupied_issues"), [])


if __name__ == "__main__":
    unittest.main()
