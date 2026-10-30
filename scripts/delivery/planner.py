"""Describe dependency readiness without dispatching implementation work."""

from pathlib import PurePosixPath

from model import integer_value, issue_numbers, list_value, string_value

DECISION_LABELS = {"needs-decision", "needs-source-scope", "needs-scope", "source-scope"}


def paths_overlap(first: str, second: str) -> bool:
    left, right = PurePosixPath(first), PurePosixPath(second)
    return left == right or left in right.parents or right in left.parents


def create_plan(
    issues: list[dict[str, object]],
    claims: list[dict[str, object]] | None = None,
    open_prs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Propose leaf issues while preserving decisions, dependencies, and ownership."""
    records: dict[int, dict[str, object]] = {}
    for issue in issues:
        number = integer_value(issue.get("number"), "issue number", 1)
        if number in records:
            raise ValueError("duplicate issue in snapshot")
        records[number] = issue
    active_claims = claims or []
    prs = open_prs or []
    claimed = {integer_value(claim.get("issue"), "claimed issue", 1) for claim in active_claims}
    pr_issues: dict[int, list[int]] = {}
    for pr in prs:
        for number in issue_numbers(pr.get("issues", []), "PR issues"):
            pr_issues.setdefault(number, []).append(integer_value(pr.get("number"), "PR number", 1))
    candidates: list[int] = []
    decisions: list[int] = []
    epics: list[int] = []
    blocked: dict[str, list[int]] = {}
    external: dict[str, object] = {}
    owned: dict[str, object] = {}
    unlocks: dict[str, list[int]] = {str(number): [] for number in records}
    for number, issue in records.items():
        labels = {
            string_value(label, "label").lower()
            for label in list_value(issue.get("labels", []), "labels")
        }
        blockers = issue_numbers(issue.get("blockers", []), "blockers")
        children = issue_numbers(issue.get("children", []), "children")
        decision = bool(labels & DECISION_LABELS) or any(
            marker in label
            for label in labels
            for marker in ("needs-decision", "source-scope", "needs-scope")
        )
        epic = "epic" in labels or bool(children)
        if decision:
            decisions.append(number)
        if epic:
            epics.append(number)
        if blockers:
            blocked[str(number)] = blockers
            outside = [dependency for dependency in blockers if dependency not in records]
            if outside:
                external[str(number)] = outside
            for dependency in blockers:
                if str(dependency) in unlocks:
                    unlocks[str(dependency)].append(number)
        if number in claimed or number in pr_issues:
            owned[str(number)] = {
                "local_claim": number in claimed,
                "open_prs": pr_issues.get(number, []),
            }
        outside_dependencies = list_value(
            issue.get("external_dependencies", []), "external_dependencies"
        )
        if outside_dependencies:
            external[str(number)] = outside_dependencies
        if not (
            decision
            or epic
            or blockers
            or outside_dependencies
            or number in claimed
            or number in pr_issues
        ):
            candidates.append(number)
    conflicts: list[dict[str, object]] = []
    for index, left in enumerate(active_claims):
        left_paths = list_value(left.get("paths", []), "claim paths")
        left_contracts = list_value(left.get("contracts", []), "claim contracts")
        for right in active_claims[index + 1 :]:
            right_paths = list_value(right.get("paths", []), "claim paths")
            overlapping = [
                str(path)
                for path in left_paths
                if any(paths_overlap(str(path), str(other)) for other in right_paths)
            ]
            shared_contracts = sorted(
                set(map(str, left_contracts))
                & set(map(str, list_value(right.get("contracts", []), "claim contracts")))
            )
            if left.get("issue") == right.get("issue") or overlapping or shared_contracts:
                conflicts.append(
                    {
                        "issues": [left.get("issue"), right.get("issue")],
                        "paths": overlapping,
                        "contracts": shared_contracts,
                    }
                )
    return {
        "candidate_issues": sorted(candidates),
        "proposed_assignments": [
            {
                "issue": number,
                "eligibility": "dependency_ready_only",
                "code_scope_review_required": True,
            }
            for number in sorted(candidates)
        ],
        "safe_parallel_worker_count": None,
        "unmapped_open_prs": [
            integer_value(pr.get("number"), "PR number", 1)
            for pr in prs
            if not issue_numbers(pr.get("issues", []), "PR issues")
        ],
        "decision_issues": sorted(decisions),
        "aggregation_issues": sorted(epics),
        "blocked_issues": blocked,
        "external_blockers": external,
        "existing_ownership": owned,
        "ownership_conflicts": conflicts,
        "direct_unlocks": {key: sorted(value) for key, value in unlocks.items() if value},
        "code_independence_verified": False,
        "dispatch_performed": False,
        "decisions_required": [
            "Confirm acceptance scope and inspect code paths and contracts before claiming candidates.",
            "Reconcile open PRs, worktrees, and local claims with their current owners.",
            "Resolve source-scope and needs-decision labels with the human before eligibility.",
        ],
    }
