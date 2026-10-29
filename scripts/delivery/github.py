"""Read paginated GitHub facts through the user's authenticated gh CLI."""

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

from model import MILESTONE, REPOSITORY, integer_value, list_value, object_value, string_value

type Transport = Callable[[str, dict[str, object]], dict[str, object]]
PAGE = "pageInfo { hasNextPage endCursor }"
REFERENCE = "number state url repository { nameWithOwner }"
ISSUES_QUERY = """
query SnapshotIssues($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    milestone(number: 1) {
      number title state
      issues(first: 100, after: $cursor, states: OPEN) {
        nodes {
          number title body updatedAt url state
          parent { REFERENCE }
          labels(first: 100) { nodes { name } PAGE }
          blockedBy(first: 100) { nodes { REFERENCE } PAGE }
          blocking(first: 100) { nodes { REFERENCE } PAGE }
          subIssues(first: 100) { nodes { REFERENCE } PAGE }
        }
        PAGE
      }
    }
  }
}
""".replace("REFERENCE", REFERENCE).replace("PAGE", PAGE)
PRS_QUERY = """
query SnapshotPRs($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 100, after: $cursor, states: OPEN) {
      nodes {
        number url title headRefName baseRefName headRefOid baseRefOid updatedAt isDraft
        closingIssuesReferences(first: 100) { nodes { REFERENCE } PAGE }
      }
      PAGE
    }
  }
}
""".replace("REFERENCE", REFERENCE).replace("PAGE", PAGE)


def _gh(query: str, variables: dict[str, object]) -> dict[str, object]:
    """Send only GraphQL query operations, never mutations or a shell command."""
    if not query.lstrip().startswith("query "):
        raise ValueError("only read-only GraphQL queries are supported")
    command = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is not None:
            command.extend(["-F", f"{key}={value}"])
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=90)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"GitHub read failed: {error.stderr.strip()}") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"GitHub read failed: {error}") from error
    response = object_value(cast("object", json.loads(result.stdout)), "GitHub response")
    if response.get("errors"):
        raise ValueError("GitHub returned GraphQL errors, snapshot is incomplete")
    return object_value(response.get("data"), "GitHub data")


def _connection(value: object) -> tuple[list[dict[str, object]], str | None]:
    connection = object_value(value, "connection")
    nodes = [
        object_value(item, "connection node")
        for item in list_value(connection.get("nodes"), "nodes")
    ]
    page = object_value(connection.get("pageInfo"), "pageInfo")
    if page.get("hasNextPage") is False:
        return nodes, None
    if page.get("hasNextPage") is not True:
        raise ValueError("missing pagination status")
    return nodes, string_value(page.get("endCursor"), "pagination cursor")


def _reference(item: dict[str, object]) -> dict[str, object]:
    repository = object_value(item.get("repository"), "referenced repository")
    return {
        "number": integer_value(item.get("number"), "reference number", 1),
        "state": string_value(item.get("state"), "reference state"),
        "url": string_value(item.get("url"), "reference URL"),
        "repository": string_value(repository.get("nameWithOwner"), "reference repository"),
    }


class GitHubClient:
    def __init__(self, transport: Transport | None = None) -> None:
        self.transport: Transport = transport or _gh
        owner, name = REPOSITORY.split("/")
        self.variables: dict[str, object] = {"owner": owner, "name": name}

    def _repository(self, query: str, variables: dict[str, object]) -> dict[str, object]:
        return object_value(
            self.transport(query, {**self.variables, **variables}).get("repository"), "repository"
        )

    def _relation(
        self,
        number: int,
        field: str,
        initial: object,
        *,
        pull_request: bool = False,
    ) -> list[dict[str, object]]:
        nodes, cursor = _connection(initial)
        seen: set[str] = set()
        entity = "pullRequest" if pull_request else "issue"
        operation = "PRIssues" if pull_request else "IssueRelation"
        selection = "name" if field == "labels" else REFERENCE
        query = (
            f"query {operation}($owner: String!, $name: String!, $number: Int!, $cursor: String) {{ "
            f"repository(owner: $owner, name: $name) {{ {entity}(number: $number) {{ "
            f"{field}(first: 100, after: $cursor) {{ nodes {{ {selection} }} {PAGE} }} }} }} }}"
        )
        while cursor is not None:
            if cursor in seen:
                raise ValueError("GitHub pagination repeated a cursor")
            seen.add(cursor)
            repository = self._repository(query, {"number": number, "cursor": cursor})
            parent = object_value(repository.get(entity), entity)
            page, cursor = _connection(parent.get(field))
            nodes.extend(page)
        return nodes

    def _issues(self) -> tuple[list[dict[str, object]], dict[str, object]]:
        issues: list[dict[str, object]] = []
        cursor: str | None = None
        seen: set[str] = set()
        metadata: dict[str, object] = {}
        while True:
            repository = self._repository(ISSUES_QUERY, {"cursor": cursor})
            milestone = object_value(repository.get("milestone"), "milestone")
            if milestone.get("number") != MILESTONE or milestone.get("title") != "v1":
                raise ValueError("expected milestone 1 titled v1")
            metadata = {field: milestone.get(field) for field in ("number", "title", "state")}
            page, next_cursor = _connection(milestone.get("issues"))
            for raw in page:
                number = integer_value(raw.get("number"), "issue number", 1)
                relations = {
                    field: [
                        _reference(item) for item in self._relation(number, field, raw.get(field))
                    ]
                    for field in ("blockedBy", "blocking", "subIssues")
                }
                labels = [
                    string_value(item.get("name"), "label")
                    for item in self._relation(number, "labels", raw.get("labels"))
                ]
                blockers = relations["blockedBy"]
                parent = (
                    _reference(object_value(raw["parent"], "parent"))
                    if raw.get("parent") is not None
                    else None
                )
                issues.append(
                    {
                        "number": number,
                        "title": string_value(raw.get("title"), "issue title"),
                        "body": raw.get("body"),
                        "updated_at": string_value(raw.get("updatedAt"), "issue updated_at"),
                        "url": string_value(raw.get("url"), "issue URL"),
                        "state": raw.get("state"),
                        "labels": labels,
                        "parent": parent,
                        "blockers": [
                            item["number"]
                            for item in blockers
                            if item["state"] == "OPEN" and item["repository"] == REPOSITORY
                        ],
                        "external_dependencies": [
                            item
                            for item in blockers
                            if item["state"] == "OPEN" and item["repository"] != REPOSITORY
                        ],
                        "children": [item["number"] for item in relations["subIssues"]],
                        "native_relations": relations,
                    }
                )
            if next_cursor is None:
                break
            if next_cursor in seen:
                raise ValueError("GitHub issue pagination repeated a cursor")
            seen.add(next_cursor)
            cursor = next_cursor
        numbers = [item["number"] for item in issues]
        if len(set(numbers)) != len(numbers):
            raise ValueError("GitHub issue snapshot contains duplicate numbers")
        return issues, metadata

    def _prs(self) -> list[dict[str, object]]:
        prs: list[dict[str, object]] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            repository = self._repository(PRS_QUERY, {"cursor": cursor})
            page, next_cursor = _connection(repository.get("pullRequests"))
            for raw in page:
                number = integer_value(raw.get("number"), "PR number", 1)
                closing = [
                    _reference(item)
                    for item in self._relation(
                        number,
                        "closingIssuesReferences",
                        raw.get("closingIssuesReferences"),
                        pull_request=True,
                    )
                ]
                prs.append(
                    {
                        "number": number,
                        "url": string_value(raw.get("url"), "PR URL"),
                        "title": raw.get("title"),
                        "branch": raw.get("headRefName"),
                        "base_branch": raw.get("baseRefName"),
                        "head_sha": raw.get("headRefOid"),
                        "base_sha": raw.get("baseRefOid"),
                        "draft": raw.get("isDraft"),
                        "updated_at": raw.get("updatedAt"),
                        "issues": [
                            item["number"] for item in closing if item["repository"] == REPOSITORY
                        ],
                        "closing_references": closing,
                    }
                )
            if next_cursor is None:
                break
            if next_cursor in seen:
                raise ValueError("GitHub PR pagination repeated a cursor")
            seen.add(next_cursor)
            cursor = next_cursor
        return prs

    def snapshot(self) -> dict[str, object]:
        """Capture a finite launch scope and all native relation pages.

        GitHub does not provide an atomic transaction over this query sequence.
        The coordinator must refresh issue and PR revisions before dispatch and
        again before assessing a merge.
        """
        issues, milestone = self._issues()
        prs = self._prs()
        return {
            "schema_version": 1,
            "mode": "read_only_snapshot",
            "repository": REPOSITORY,
            "milestone": milestone,
            "captured_at": datetime.now(UTC).isoformat(),
            "atomic_github_snapshot": False,
            "allowed_issues": sorted(cast("int", issue["number"]) for issue in issues),
            "issues": issues,
            "open_prs": prs,
        }
