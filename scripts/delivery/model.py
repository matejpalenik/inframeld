"""Assess recorded evidence without authorizing or performing a GitHub merge."""

import re
from dataclasses import dataclass
from typing import cast

REPOSITORY = "matejpalenik/inframeld"
MILESTONE = 1
SHA = re.compile(r"[0-9a-f]{40}")


def object_value(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    result = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in result):
        raise ValueError(f"{name} must be a JSON object with string keys")
    return cast("dict[str, object]", result)


def list_value(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return cast("list[object]", value)


def string_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def integer_value(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def sha_value(value: object, name: str) -> str:
    result = string_value(value, name)
    if SHA.fullmatch(result) is None:
        raise ValueError(f"{name} must be a full lowercase commit SHA")
    return result


def issue_numbers(value: object, name: str) -> list[int]:
    result = [integer_value(item, name, 1) for item in list_value(value, name)]
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class MergeAssessment:
    verdict: str
    reasons: tuple[str, ...]


def _current(receipt: dict[str, object], assignment: dict[str, object]) -> bool:
    return all(
        receipt.get(field) == assignment.get(field)
        for field in ("base_sha", "head_sha", "issue_updated_at")
    )


def _accepted_risk(
    finding: dict[str, object],
    role: str,
    review_reference: str,
    assignment: dict[str, object],
    observation: dict[str, object],
) -> bool:
    """Consume coordinator-verified human evidence, never a worker's authority claim."""
    if finding.get("priority") != 2:
        return False
    for item in list_value(observation.get("human_risk_acceptances", []), "human risks"):
        risk = object_value(item, "human risk")
        if (
            risk.get("finding_id") == finding.get("id")
            and risk.get("role") == role
            and risk.get("review_reference") == review_reference
            and risk.get("priority") == 2
            and risk.get("verified_human") is True
            and risk.get("source") in ("direct_user_instruction", "github_human_review")
            and _current(risk, assignment)
            and string_value(risk.get("accepted_by"), "human identity")
            and string_value(risk.get("reference"), "human risk reference")
            and string_value(risk.get("bounded_risk"), "bounded risk")
        ):
            return True
    return False


def _finding_blocks(
    role: str,
    review: dict[str, object],
    assignment: dict[str, object],
    observation: dict[str, object],
) -> bool:
    blocked = False
    identifiers: set[str] = set()
    review_reference = string_value(review.get("reference"), "review reference")
    for item in list_value(review.get("findings"), "findings"):
        finding = object_value(item, "finding")
        identifier = string_value(finding.get("id"), "finding id")
        if identifier in identifiers:
            raise ValueError("duplicate finding IDs within a review receipt")
        identifiers.add(identifier)
        priority = integer_value(finding.get("priority"), "priority")
        if priority > 3 or not isinstance(finding.get("resolved"), bool):
            raise ValueError("findings need a P0-P3 priority and resolved boolean")
        if (
            finding["resolved"] is False
            and priority <= 2
            and not _accepted_risk(finding, role, review_reference, assignment, observation)
        ):
            blocked = True
    return blocked


def _check_result(check: dict[str, object], *, coderabbit_required: bool = False) -> str:
    string_value(check.get("reference"), "check reference")
    conclusion = check.get("conclusion")
    if coderabbit_required:
        status = check.get("status")
        if not isinstance(status, str) or status.casefold() != "completed":
            return "pending"
        if isinstance(conclusion, str):
            conclusion = conclusion.casefold()
    if conclusion in ("failure", "timed_out", "action_required", "startup_failure"):
        return "blocked"
    if coderabbit_required:
        return "ready" if conclusion in ("success", "neutral", "skipped") else "pending"
    if conclusion == "success" and check.get("applicable") is True:
        return "ready"
    if (
        conclusion == "skipped"
        and check.get("applicable") is False
        and isinstance(check.get("explanation"), str)
        and cast("str", check["explanation"]).strip()
    ):
        return "ready"
    return "pending"


def _coderabbit_result(
    rabbit: dict[str, object], evidence: dict[str, object], assignment: dict[str, object]
) -> str:
    """Wait for the observed run, then use independent local assessment of its comments."""
    reference = string_value(rabbit.get("reference"), "CodeRabbit reference")
    status = rabbit.get("status")
    if not isinstance(status, str) or status.casefold() not in ("completed", "not_reported"):
        return "pending"
    if "conclusion" not in rabbit or "comments" not in rabbit:
        return "pending"
    conclusion = rabbit["conclusion"]
    if conclusion is not None:
        string_value(conclusion, "raw CodeRabbit conclusion")
    comments = [
        string_value(item, "CodeRabbit comment id")
        for item in list_value(rabbit["comments"], "CodeRabbit comments")
    ]
    if len(set(comments)) != len(comments):
        raise ValueError("duplicate CodeRabbit comment IDs")
    if status.casefold() == "not_reported" and (conclusion is not None or comments):
        return "pending"
    if not comments:
        return "ready"
    local_reference = rabbit.get("local_review_reference")
    if not isinstance(local_reference, str) or not local_reference.strip():
        return "pending"
    for role in ("code_review", "dx_review"):
        if role not in evidence:
            continue
        review = object_value(evidence[role], role)
        if (
            review.get("reference") != local_reference
            or not _current(review, assignment)
            or review.get("verdict") != "ready"
            or string_value(review.get("reviewer_id"), "reviewer_id") == assignment["worker_id"]
        ):
            continue
        covered: set[tuple[str, str]] = set()
        for item in list_value(review.get("reviewed_comments", []), "reviewed_comments"):
            comment = object_value(item, "reviewed comment")
            covered.add(
                (
                    string_value(comment.get("id"), "reviewed comment id"),
                    string_value(comment.get("review_reference"), "bot comment origin"),
                )
            )
        if all((identifier, reference) in covered for identifier in comments):
            return "ready"
    return "pending"


def _strings_required(value: object) -> list[str]:
    if value is None:
        return []
    return [
        string_value(name, "observed required check")
        for name in list_value(value, "required_checks")
    ]


def assess_prerequisite(
    assignment: dict[str, object], packet: dict[str, object]
) -> MergeAssessment:
    """Assess a reviewed supporting PR without declaring its owning issue complete."""
    try:
        pr = integer_value(packet.get("pr"), "pr", 1)
        scope = string_value(packet.get("scope"), "scope")
        remaining = list_value(packet.get("remaining_acceptance"), "remaining_acceptance")
        if not remaining:
            raise ValueError("supporting PR must identify remaining issue acceptance")
        for item in remaining:
            string_value(item, "remaining acceptance item")
        review = object_value(packet.get("scope_review"), "scope_review")
        if not _current(review, assignment):
            raise ValueError("supporting scope review is stale")
        if (
            review.get("scope") != scope
            or review.get("remaining_acceptance") != remaining
            or review.get("deferred_blockers") != assignment.get("blockers")
        ):
            raise ValueError(
                "scope review must cover the exact boundary and every deferred blocker"
            )
        string_value(review.get("reference"), "scope review reference")
        string_value(review.get("dependency_rationale"), "dependency rationale")
        if review.get("verdict") != "ready" or string_value(
            review.get("reviewer_id"), "scope reviewer"
        ) == assignment.get("worker_id"):
            raise ValueError("supporting scope needs independent ready review")
        evidence = object_value(packet.get("evidence"), "supporting evidence")
        for role in ("acceptance", "documentation", "code_review", "dx_review"):
            receipt = object_value(evidence.get(role), role)
            if receipt.get("pr") != pr or receipt.get("scope") != scope:
                raise ValueError("every review must identify this supporting PR and scope")
        observed = object_value(packet.get("observation"), "observation")
        if observed.get("pr") != pr or observed.get("closing_issues") != []:
            raise ValueError(
                "supporting PR observation must match and contain no closing references"
            )
        if assignment.get("merge_state") in ("uncertain", "merged"):
            raise ValueError("reconcile uncertain or completed issue merge first")
        if _finding_blocks("scope_review", review, assignment, observed):
            raise ValueError("supporting scope has unresolved material findings")
        return assess_merge({**assignment, "blockers": [], "evidence": evidence}, observed)
    except ValueError as error:
        return MergeAssessment("blocked", (f"Invalid supporting PR evidence: {error}.",))


def assess_merge(assignment: dict[str, object], observation: dict[str, object]) -> MergeAssessment:
    """Fail closed on absent, stale, malformed, or incomplete review evidence.

    The caller must verify observations against GitHub and verify human risk
    receipts against the original human instruction. JSON is evidence storage,
    not an identity provider or an authorization boundary.
    """
    pending: list[str] = []
    blocked: list[str] = []
    try:
        integer_value(assignment.get("issue"), "issue", 1)
        sha_value(assignment.get("base_sha"), "base_sha")
        sha_value(assignment.get("head_sha"), "head_sha")
        string_value(assignment.get("issue_updated_at"), "issue_updated_at")
        if not _current(observation, assignment):
            pending.append("Observed base, head, or issue scope changed. Refresh all evidence.")
        if assignment.get("claim_state") == "retired":
            blocked.append("The assignment is retired.")
        supporting = object_value(assignment.get("prerequisite_merges", {}), "prerequisite_merges")
        if any(
            object_value(item, "supporting merge").get("status") == "uncertain"
            for item in supporting.values()
        ):
            blocked.append("A supporting PR merge is uncertain. Reconcile GitHub first.")
        blockers = list_value(assignment.get("blockers"), "blockers")
        if blockers:
            blocked.append("The assignment has unresolved blockers.")
        if observation.get("draft") is not False:
            pending.append("The PR is a draft or draft status is unknown.")
        if observation.get("mergeable") is False:
            blocked.append("GitHub reports a merge conflict.")
        elif observation.get("mergeable") is not True:
            pending.append("Mergeability is unknown.")
        threads = observation.get("unresolved_review_threads")
        if threads is None:
            pending.append("Review thread status is unknown.")
        elif integer_value(threads, "unresolved_review_threads") > 0:
            blocked.append("Review threads remain unresolved.")
        evidence = object_value(assignment.get("evidence", {}), "evidence")
        for role in ("acceptance", "documentation", "code_review", "dx_review"):
            if role not in evidence:
                pending.append(f"Missing {role} evidence.")
                continue
            review = object_value(evidence[role], role)
            string_value(review.get("reference"), f"{role} reference")
            if not _current(review, assignment):
                pending.append(f"{role} evidence is stale.")
                continue
            if role in ("code_review", "dx_review"):
                reviewer = string_value(review.get("reviewer_id"), f"{role} reviewer_id")
                if reviewer == string_value(assignment.get("worker_id"), "worker_id"):
                    blocked.append(f"{role} was performed by the implementation worker.")
            verdict = review.get("verdict")
            if verdict in ("changes_needed", "blocked"):
                blocked.append(f"{role} requires changes.")
            elif verdict != "ready":
                pending.append(f"{role} has not completed.")
            if _finding_blocks(role, review, assignment, observation):
                blocked.append(f"{role} has unresolved material findings.")
        required = [
            string_value(name, "required check")
            for name in list_value(assignment.get("required_checks"), "required_checks")
        ]
        if not required or len(set(required)) != len(required):
            raise ValueError("required_checks must be a nonempty unique list")
        observed_required = _strings_required(observation.get("required_checks"))
        if set(required) != set(observed_required):
            pending.append("Required checks changed or have not been reconciled with GitHub.")
        checks: dict[str, dict[str, object]] = {}
        for item in list_value(evidence.get("checks", []), "checks"):
            check = object_value(item, "check")
            name = string_value(check.get("name"), "check name")
            if name in checks:
                raise ValueError("duplicate check evidence")
            checks[name] = check
        for name in required:
            if name not in checks:
                pending.append(f"Missing check: {name}.")
                continue
            check = checks[name]
            if (
                check.get("head_sha") != assignment["head_sha"]
                or check.get("base_sha") != assignment["base_sha"]
            ):
                pending.append(f"Check {name} is stale.")
                continue
            result = _check_result(check, coderabbit_required=name.casefold() == "coderabbit")
            if result == "blocked":
                blocked.append(f"Check {name} failed.")
            elif result != "ready":
                pending.append(f"Check {name} has no passing result.")
        if "coderabbit" not in evidence:
            pending.append(
                "Record the observed CodeRabbit run or reconcile that none was reported."
            )
        else:
            rabbit = object_value(evidence["coderabbit"], "coderabbit")
            if not _current(rabbit, assignment):
                pending.append("CodeRabbit evidence is stale.")
            elif _coderabbit_result(rabbit, evidence, assignment) != "ready":
                pending.append("Wait for or reconcile CodeRabbit and assess its comments locally.")
    except ValueError as error:
        blocked.append(f"Malformed evidence: {error}.")
    reasons = tuple(blocked + pending)
    return MergeAssessment("blocked" if blocked else "pending" if pending else "ready", reasons)
