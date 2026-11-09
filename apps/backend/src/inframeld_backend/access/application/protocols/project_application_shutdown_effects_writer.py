from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProjectApplicationShutdownEffectsWriter(Protocol):
    """Apply local application shutdown inside an authentic caller's transaction.

    The caller owns admission authority for the exact original deletion obligation,
    its active READ COMMITTED transaction, original deadline, rollback, revision,
    audit and parent checkpoint. Scope IDs and a DELETING Project are integrity
    preconditions, not an admission certificate. This capability is not exposed
    through a public or worker entrypoint until an authentic caller is delivered.
    """

    @abstractmethod
    async def shutdown(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
    ) -> bool:
        """Retire this Project's actual accounts, including accounts without membership.

        Retain Organization, Project, account and ordered key coordination through
        the caller's transaction. Refresh scope, lifecycle and database time after
        waits. Revoke every associated key, preserving existing revocation times,
        then remove received grants and group/Project memberships in FK-safe order,
        together with human administration grants targeting these accounts.

        Preserve inert identity/account/key metadata, attribution, human managers,
        groups/default references, unrelated Projects and Project-owned work.
        True means local rows changed in the uncommitted caller transaction.
        False means the complete checked local state needed no change. Neither
        result proves admission, commit or business completion. Never commit,
        reset the caller's deadline, swallow cancellation or return False after
        partial failure. The caller remains responsible for consistent progress.

        Raises:
            RuntimeError: Caller transaction, isolation, scope or lifecycle is invalid.
        """
        ...
