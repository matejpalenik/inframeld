"""Verify PostgreSQL enforces the core scoped Access relationships."""

import os
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from inframeld_backend.shared.infrastructure.migrations import run_migrations
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)


@dataclass(frozen=True, slots=True)
class AccessRecordIds:
    """Identify the people, projects, application, and group created for a test."""

    organization_id: UUID
    project_id: UUID
    other_project_id: UUID
    human_id: UUID
    other_human_id: UUID
    application_id: UUID
    group_id: UUID


@pytest.fixture
def access_connection(
    temporary_postgres_settings: DatabaseSettings,
) -> Generator[Connection[Any]]:
    """Run the Access migrations and provide a fresh PostgreSQL connection."""
    run_migrations(temporary_postgres_settings)

    with psycopg.connect(
        host=temporary_postgres_settings.host,
        port=temporary_postgres_settings.port,
        dbname=temporary_postgres_settings.name,
        user=temporary_postgres_settings.user,
        password=temporary_postgres_settings.password.get_secret_value(),
        autocommit=True,
    ) as connection:
        yield connection


@pytest.fixture
def access_record_ids(access_connection: Connection[Any]) -> AccessRecordIds:
    """Create two projects and their human, application, and group records."""
    ids = AccessRecordIds(
        organization_id=uuid4(),
        project_id=uuid4(),
        other_project_id=uuid4(),
        human_id=uuid4(),
        other_human_id=uuid4(),
        application_id=uuid4(),
        group_id=uuid4(),
    )

    access_connection.execute(
        "INSERT INTO organizations (id, name) VALUES (%s, %s)",
        (ids.organization_id, "Test organization"),
    )
    for principal_id, kind, display_name in (
        (ids.human_id, "human", "Alice"),
        (ids.other_human_id, "human", "Bob"),
        (ids.application_id, "application", "SupportBot"),
    ):
        access_connection.execute(
            """
            INSERT INTO principals (id, organization_id, kind, status, display_name)
            VALUES (%s, %s, %s, 'active', %s)
            """,
            (principal_id, ids.organization_id, kind, display_name),
        )
    for project_id, name in (
        (ids.project_id, "Support"),
        (ids.other_project_id, "Test"),
    ):
        access_connection.execute(
            "INSERT INTO projects (id, organization_id, name, status) VALUES (%s, %s, %s, 'active')",
            (project_id, ids.organization_id, name),
        )
    access_connection.execute(
        """
        INSERT INTO application_accounts (principal_id, organization_id, project_id, principal_kind)
        VALUES (%s, %s, %s, 'application')
        """,
        (ids.application_id, ids.organization_id, ids.project_id),
    )
    for project_id, principal_id, kind, application_id in (
        (ids.project_id, ids.human_id, "human", None),
        (ids.other_project_id, ids.other_human_id, "human", None),
        (ids.project_id, ids.application_id, "application", ids.application_id),
    ):
        access_connection.execute(
            """
            INSERT INTO project_memberships
                (project_id, principal_id, organization_id, principal_kind, application_principal_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, principal_id, ids.organization_id, kind, application_id),
        )
    access_connection.execute(
        "INSERT INTO access_groups (id, project_id, name) VALUES (%s, %s, %s)",
        (ids.group_id, ids.project_id, "SupportKnowledge"),
    )

    return ids


def test_group_membership_rejects_a_principal_from_another_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep a project's group from including a member of a different project."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO group_memberships (project_id, group_id, principal_id)
            VALUES (%s, %s, %s)
            """,
            (
                access_record_ids.project_id,
                access_record_ids.group_id,
                access_record_ids.other_human_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_group_memberships_project_member"


def test_project_grant_rejects_a_recipient_from_another_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep project action grants attached to a member of that same project."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO project_action_grants
                (project_id, recipient_principal_id, recipient_kind, action, can_grant)
            VALUES (%s, %s, 'human', 'build', false)
            """,
            (access_record_ids.project_id, access_record_ids.other_human_id),
        )

    assert error.value.diag.constraint_name == "fk_project_action_grants_recipient"


def test_group_manager_requires_membership_in_that_group(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Require a human to join a group before they can manage that group."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO group_managers (project_id, group_id, principal_id, principal_kind)
            VALUES (%s, %s, %s, 'human')
            """,
            (
                access_record_ids.project_id,
                access_record_ids.group_id,
                access_record_ids.human_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_group_managers_group_member"


def test_application_member_cannot_manage_a_group(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Restrict group management to human members, even when an app joins the group."""
    access_connection.execute(
        """
        INSERT INTO group_memberships (project_id, group_id, principal_id)
        VALUES (%s, %s, %s)
        """,
        (
            access_record_ids.project_id,
            access_record_ids.group_id,
            access_record_ids.application_id,
        ),
    )

    with pytest.raises(CheckViolation) as error:
        access_connection.execute(
            """
            INSERT INTO group_managers (project_id, group_id, principal_id, principal_kind)
            VALUES (%s, %s, %s, 'application')
            """,
            (
                access_record_ids.project_id,
                access_record_ids.group_id,
                access_record_ids.application_id,
            ),
        )

    assert error.value.diag.constraint_name == "ck_group_managers_human_only"


def test_human_group_member_can_become_a_group_manager(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Allow group management after the human has ordinary membership."""
    access_connection.execute(
        """
        INSERT INTO group_memberships (project_id, group_id, principal_id)
        VALUES (%s, %s, %s)
        """,
        (
            access_record_ids.project_id,
            access_record_ids.group_id,
            access_record_ids.human_id,
        ),
    )

    access_connection.execute(
        """
        INSERT INTO group_managers (project_id, group_id, principal_id, principal_kind)
        VALUES (%s, %s, %s, 'human')
        """,
        (
            access_record_ids.project_id,
            access_record_ids.group_id,
            access_record_ids.human_id,
        ),
    )

    manager_count_row = access_connection.execute(
        """
        SELECT count(*) FROM group_managers
        WHERE project_id = %s AND group_id = %s AND principal_id = %s
        """,
        (
            access_record_ids.project_id,
            access_record_ids.group_id,
            access_record_ids.human_id,
        ),
    ).fetchone()

    assert manager_count_row == (1,)


def test_verified_identity_pair_maps_to_only_one_human(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep each verified identity source and subject attached to one stable human."""
    access_connection.execute(
        """
        INSERT INTO human_identity_links
            (authority, subject, organization_id, principal_id, principal_kind)
        VALUES (%s, %s, %s, %s, 'human')
        """,
        (
            "kratos:local",
            "alice-local-id",
            access_record_ids.organization_id,
            access_record_ids.human_id,
        ),
    )
    access_connection.execute(
        """
        INSERT INTO human_identity_links
            (authority, subject, organization_id, principal_id, principal_kind)
        VALUES (%s, %s, %s, %s, 'human')
        """,
        (
            "oidc:company",
            "alice-company-id",
            access_record_ids.organization_id,
            access_record_ids.human_id,
        ),
    )

    identity_count_row = access_connection.execute(
        """
        SELECT count(*), count(DISTINCT principal_id)
        FROM human_identity_links
        WHERE organization_id = %s AND principal_id = %s
        """,
        (access_record_ids.organization_id, access_record_ids.human_id),
    ).fetchone()

    assert identity_count_row == (2, 1)

    with pytest.raises(UniqueViolation) as error:
        access_connection.execute(
            """
            INSERT INTO human_identity_links
                (authority, subject, organization_id, principal_id, principal_kind)
            VALUES (%s, %s, %s, %s, 'human')
            """,
            (
                "kratos:local",
                "alice-local-id",
                access_record_ids.organization_id,
                access_record_ids.other_human_id,
            ),
        )

    assert error.value.diag.constraint_name == "pk_human_identity_links"


def test_human_identity_link_rejects_an_application_principal(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Prevent an application account from being treated as a verified human login."""
    with pytest.raises(CheckViolation) as error:
        access_connection.execute(
            """
            INSERT INTO human_identity_links
                (authority, subject, organization_id, principal_id, principal_kind)
            VALUES ('kratos:local', 'support-bot-id', %s, %s, 'application')
            """,
            (access_record_ids.organization_id, access_record_ids.application_id),
        )

    assert error.value.diag.constraint_name == "ck_identity_links_human_only"


def test_application_membership_cannot_escape_its_owning_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal bound to the project recorded by its account."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO project_memberships
                (project_id, principal_id, organization_id, principal_kind, application_principal_id)
            VALUES (%s, %s, %s, 'application', %s)
            """,
            (
                access_record_ids.other_project_id,
                access_record_ids.application_id,
                access_record_ids.organization_id,
                access_record_ids.application_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_project_memberships_application_account"


def test_group_action_grant_rejects_a_recipient_from_another_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep a group's action grants limited to members of the group's project."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO group_action_grants
                (project_id, group_id, recipient_principal_id, recipient_kind, action, can_grant)
            VALUES (%s, %s, %s, 'human', 'add-documents', false)
            """,
            (
                access_record_ids.project_id,
                access_record_ids.group_id,
                access_record_ids.other_human_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_group_action_grants_recipient"


def test_application_action_grant_rejects_an_application_from_another_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep human key-management grants attached to the application's owning project."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO application_action_grants
                (
                    project_id,
                    application_principal_id,
                    recipient_principal_id,
                    recipient_kind,
                    action,
                    can_grant
                )
            VALUES (%s, %s, %s, 'human', 'issue-keys', false)
            """,
            (
                access_record_ids.other_project_id,
                access_record_ids.application_id,
                access_record_ids.other_human_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_application_action_grants_application"


def test_application_action_grant_cannot_target_an_application_principal(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Reserve application-account administration grants for human project members."""
    with pytest.raises(CheckViolation) as error:
        access_connection.execute(
            """
            INSERT INTO application_action_grants
                (
                    project_id,
                    application_principal_id,
                    recipient_principal_id,
                    recipient_kind,
                    action,
                    can_grant
                )
            VALUES (%s, %s, %s, 'application', 'issue-keys', false)
            """,
            (
                access_record_ids.project_id,
                access_record_ids.application_id,
                access_record_ids.application_id,
            ),
        )

    assert error.value.diag.constraint_name == "ck_application_action_grants_human_only"


def test_application_action_grant_rejects_a_recipient_from_another_project(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Require a human who manages an application's keys to belong to its project."""
    with pytest.raises(ForeignKeyViolation) as error:
        access_connection.execute(
            """
            INSERT INTO application_action_grants
                (
                    project_id,
                    application_principal_id,
                    recipient_principal_id,
                    recipient_kind,
                    action,
                    can_grant
                )
            VALUES (%s, %s, %s, 'human', 'issue-keys', false)
            """,
            (
                access_record_ids.project_id,
                access_record_ids.application_id,
                access_record_ids.other_human_id,
            ),
        )

    assert error.value.diag.constraint_name == "fk_application_action_grants_recipient"


def test_application_project_grant_cannot_delegate(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal from delegating its project action grants."""
    with pytest.raises(CheckViolation) as error:
        access_connection.execute(
            """
            INSERT INTO project_action_grants
                (project_id, recipient_principal_id, recipient_kind, action, can_grant)
            VALUES (%s, %s, 'application', 'build', true)
            """,
            (access_record_ids.project_id, access_record_ids.application_id),
        )

    assert error.value.diag.constraint_name == "ck_project_action_grants_application_use_only"


def test_application_group_grant_cannot_delegate(
    access_connection: Connection[Any], access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal from delegating its group action grants."""
    with pytest.raises(CheckViolation) as error:
        access_connection.execute(
            """
            INSERT INTO group_action_grants
                (project_id, group_id, recipient_principal_id, recipient_kind, action, can_grant)
            VALUES (%s, %s, %s, 'application', 'query', true)
            """,
            (
                access_record_ids.project_id,
                access_record_ids.group_id,
                access_record_ids.application_id,
            ),
        )

    assert error.value.diag.constraint_name == "ck_group_action_grants_application_use_only"
