"""Verify PostgreSQL enforces the core scoped Access relationships."""

import os
from collections.abc import Generator
from dataclasses import dataclass
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.support.postgres import database_session, insert_row

from inframeld_backend.access.domain.action_values import ActionId
from inframeld_backend.access.domain.group_values import AccessGroupId
from inframeld_backend.access.domain.identity_values import IdentityAuthority, IdentitySubject
from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.access.domain.principal import PrincipalId, PrincipalKind, PrincipalStatus
from inframeld_backend.access.domain.project_values import ProjectId, ProjectStatus
from inframeld_backend.access.infrastructure.postgres.models.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.postgres.models.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.postgres.models.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.postgres.models.group_action_grant_row import (
    GroupActionGrantRow,
)
from inframeld_backend.access.infrastructure.postgres.models.group_manager_row import (
    GroupManagerRow,
)
from inframeld_backend.access.infrastructure.postgres.models.group_membership_row import (
    GroupMembershipRow,
)
from inframeld_backend.access.infrastructure.postgres.models.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.postgres.models.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.postgres.models.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.postgres.models.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.postgres.migration_runner import run_migrations

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)


@dataclass(frozen=True, slots=True)
class AccessRecordIds:
    """Identify the people, projects, application, and group created for a test."""

    organization_id: OrganizationId
    project_id: ProjectId
    other_project_id: ProjectId
    human_id: PrincipalId
    other_human_id: PrincipalId
    application_id: PrincipalId
    group_id: AccessGroupId


@pytest.fixture
def access_session(temporary_postgres_settings: DatabaseSettings) -> Generator[Session]:
    """Provide an ORM session over the real migrated Access schema."""
    run_migrations(temporary_postgres_settings)
    with database_session(temporary_postgres_settings) as session:
        yield session


@pytest.fixture
def access_record_ids(access_session: Session) -> AccessRecordIds:
    """Create two projects and their human, application, and group records."""
    ids = AccessRecordIds(
        organization_id=OrganizationId(uuid4()),
        project_id=ProjectId(uuid4()),
        other_project_id=ProjectId(uuid4()),
        human_id=PrincipalId(uuid4()),
        other_human_id=PrincipalId(uuid4()),
        application_id=PrincipalId(uuid4()),
        group_id=AccessGroupId(uuid4()),
    )

    insert_row(
        access_session, OrganizationRow(id=ids.organization_id.value, name="Test organization")
    )
    for principal_id, kind, display_name in (
        (ids.human_id, PrincipalKind.HUMAN, "Alice"),
        (ids.other_human_id, PrincipalKind.HUMAN, "Bob"),
        (ids.application_id, PrincipalKind.APPLICATION, "SupportBot"),
    ):
        insert_row(
            access_session,
            PrincipalRow(
                id=principal_id.value,
                organization_id=ids.organization_id.value,
                kind=kind,
                status=PrincipalStatus.ACTIVE,
                display_name=display_name,
            ),
        )
    for project_id, name in (
        (ids.project_id, "Support"),
        (ids.other_project_id, "Test"),
    ):
        insert_row(
            access_session,
            ProjectRow(
                id=project_id.value,
                organization_id=ids.organization_id.value,
                name=name,
                status=ProjectStatus.ACTIVE,
            ),
        )
    insert_row(
        access_session,
        ApplicationAccountRow(
            principal_id=ids.application_id.value,
            organization_id=ids.organization_id.value,
            project_id=ids.project_id.value,
            principal_kind=PrincipalKind.APPLICATION,
        ),
    )
    for project_id, principal_id, kind, application_id in (
        (ids.project_id, ids.human_id, PrincipalKind.HUMAN, None),
        (ids.other_project_id, ids.other_human_id, PrincipalKind.HUMAN, None),
        (ids.project_id, ids.application_id, PrincipalKind.APPLICATION, ids.application_id),
    ):
        insert_row(
            access_session,
            ProjectMembershipRow(
                project_id=project_id.value,
                principal_id=principal_id.value,
                organization_id=ids.organization_id.value,
                principal_kind=kind,
                application_principal_id=(
                    application_id.value if application_id is not None else None
                ),
            ),
        )
    insert_row(
        access_session,
        AccessGroupRow(
            id=ids.group_id.value, project_id=ids.project_id.value, name="SupportKnowledge"
        ),
    )

    return ids


def test_group_membership_rejects_a_principal_from_another_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep a project's group from including a member of a different project."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            GroupMembershipRow(
                project_id=access_record_ids.project_id.value,
                group_id=access_record_ids.group_id.value,
                principal_id=access_record_ids.other_human_id.value,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_group_memberships_project_member"


def test_project_grant_rejects_a_recipient_from_another_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep project action grants attached to a member of that same project."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ProjectActionGrantRow(
                project_id=access_record_ids.project_id.value,
                recipient_principal_id=access_record_ids.other_human_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ActionId("build").value,
                can_grant=False,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_project_action_grants_recipient"


def test_group_manager_requires_membership_in_that_group(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Require a human to join a group before they can manage that group."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            GroupManagerRow(
                project_id=access_record_ids.project_id.value,
                group_id=access_record_ids.group_id.value,
                principal_id=access_record_ids.human_id.value,
                principal_kind=PrincipalKind.HUMAN,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_group_managers_group_member"


def test_application_member_cannot_manage_a_group(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Restrict group management to human members, even when an app joins the group."""
    insert_row(
        access_session,
        GroupMembershipRow(
            project_id=access_record_ids.project_id.value,
            group_id=access_record_ids.group_id.value,
            principal_id=access_record_ids.application_id.value,
        ),
    )

    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            GroupManagerRow(
                project_id=access_record_ids.project_id.value,
                group_id=access_record_ids.group_id.value,
                principal_id=access_record_ids.application_id.value,
                principal_kind=PrincipalKind.APPLICATION,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "ck_group_managers_human_only"


def test_human_group_member_can_become_a_group_manager(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Allow group management after the human has ordinary membership."""
    insert_row(
        access_session,
        GroupMembershipRow(
            project_id=access_record_ids.project_id.value,
            group_id=access_record_ids.group_id.value,
            principal_id=access_record_ids.human_id.value,
        ),
    )

    insert_row(
        access_session,
        GroupManagerRow(
            project_id=access_record_ids.project_id.value,
            group_id=access_record_ids.group_id.value,
            principal_id=access_record_ids.human_id.value,
            principal_kind=PrincipalKind.HUMAN,
        ),
    )

    manager_count_row = access_session.execute(
        select(func.count())
        .select_from(GroupManagerRow)
        .where(
            GroupManagerRow.project_id == access_record_ids.project_id.value,
            GroupManagerRow.group_id == access_record_ids.group_id.value,
            GroupManagerRow.principal_id == access_record_ids.human_id.value,
        )
    ).one()

    assert manager_count_row == (1,)


def test_verified_identity_pair_maps_to_only_one_human(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep each verified identity source and subject attached to one stable human."""
    insert_row(
        access_session,
        HumanIdentityLinkRow(
            authority=IdentityAuthority("kratos:local").value,
            subject=IdentitySubject("alice-local-id").value,
            organization_id=access_record_ids.organization_id.value,
            principal_id=access_record_ids.human_id.value,
            principal_kind=PrincipalKind.HUMAN,
        ),
    )
    insert_row(
        access_session,
        HumanIdentityLinkRow(
            authority=IdentityAuthority("oidc:company").value,
            subject=IdentitySubject("alice-company-id").value,
            organization_id=access_record_ids.organization_id.value,
            principal_id=access_record_ids.human_id.value,
            principal_kind=PrincipalKind.HUMAN,
        ),
    )

    identity_count_row = access_session.execute(
        select(func.count(), func.count(HumanIdentityLinkRow.principal_id.distinct()))
        .select_from(HumanIdentityLinkRow)
        .where(
            HumanIdentityLinkRow.organization_id == access_record_ids.organization_id.value,
            HumanIdentityLinkRow.principal_id == access_record_ids.human_id.value,
        )
    ).one()

    assert identity_count_row == (2, 1)

    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            HumanIdentityLinkRow(
                authority=IdentityAuthority("kratos:local").value,
                subject=IdentitySubject("alice-local-id").value,
                organization_id=access_record_ids.organization_id.value,
                principal_id=access_record_ids.other_human_id.value,
                principal_kind=PrincipalKind.HUMAN,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "pk_human_identity_links"


def test_human_identity_link_rejects_an_application_principal(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Prevent an application account from being treated as a verified human login."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            HumanIdentityLinkRow(
                authority=IdentityAuthority("kratos:local").value,
                subject=IdentitySubject("support-bot-id").value,
                organization_id=access_record_ids.organization_id.value,
                principal_id=access_record_ids.application_id.value,
                principal_kind=PrincipalKind.APPLICATION,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "ck_identity_links_human_only"


def test_application_membership_cannot_escape_its_owning_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal bound to the project recorded by its account."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ProjectMembershipRow(
                project_id=access_record_ids.other_project_id.value,
                principal_id=access_record_ids.application_id.value,
                organization_id=access_record_ids.organization_id.value,
                principal_kind=PrincipalKind.APPLICATION,
                application_principal_id=access_record_ids.application_id.value,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_project_memberships_application_account"


def test_group_action_grant_rejects_a_recipient_from_another_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep a group's action grants limited to members of the group's project."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            GroupActionGrantRow(
                project_id=access_record_ids.project_id.value,
                group_id=access_record_ids.group_id.value,
                recipient_principal_id=access_record_ids.other_human_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ActionId("add-documents").value,
                can_grant=False,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_group_action_grants_recipient"


def test_application_action_grant_rejects_an_application_from_another_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep human key-management grants attached to the application's owning project."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ApplicationActionGrantRow(
                project_id=access_record_ids.other_project_id.value,
                application_principal_id=access_record_ids.application_id.value,
                recipient_principal_id=access_record_ids.other_human_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ActionId("issue-keys").value,
                can_grant=False,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_application_action_grants_application"


def test_application_action_grant_cannot_target_an_application_principal(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Reserve application-account administration grants for human project members."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ApplicationActionGrantRow(
                project_id=access_record_ids.project_id.value,
                application_principal_id=access_record_ids.application_id.value,
                recipient_principal_id=access_record_ids.application_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ActionId("issue-keys").value,
                can_grant=False,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "ck_application_action_grants_human_only"


def test_application_action_grant_rejects_a_recipient_from_another_project(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Require a human who manages an application's keys to belong to its project."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ApplicationActionGrantRow(
                project_id=access_record_ids.project_id.value,
                application_principal_id=access_record_ids.application_id.value,
                recipient_principal_id=access_record_ids.other_human_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ActionId("issue-keys").value,
                can_grant=False,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "fk_application_action_grants_recipient"


def test_application_project_grant_cannot_delegate(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal from delegating its project action grants."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            ProjectActionGrantRow(
                project_id=access_record_ids.project_id.value,
                recipient_principal_id=access_record_ids.application_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ActionId("build").value,
                can_grant=True,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "ck_project_action_grants_application_use_only"


def test_application_group_grant_cannot_delegate(
    access_session: Session, access_record_ids: AccessRecordIds
) -> None:
    """Keep an application principal from delegating its group action grants."""
    with pytest.raises(IntegrityError) as error:
        insert_row(
            access_session,
            GroupActionGrantRow(
                project_id=access_record_ids.project_id.value,
                group_id=access_record_ids.group_id.value,
                recipient_principal_id=access_record_ids.application_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ActionId("query").value,
                can_grant=True,
            ),
        )

    assert isinstance(error.value.orig, psycopg.Error)
    assert error.value.orig.diag.constraint_name == "ck_group_action_grants_application_use_only"
