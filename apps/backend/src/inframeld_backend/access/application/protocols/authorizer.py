from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO


class Authorizer[RequestType, ResultType](Protocol):
    """Decide whether an authenticated caller may perform a requested operation.

    Each permission family defines its request and result, such as performing
    a project action or granting that action to someone else.
    """

    @abstractmethod
    async def require_authorization(
        self,
        *,
        access: AccessContextDTO,
        request: RequestType,
    ) -> ResultType:
        """Check current permission before reserving, replaying or changing work.

        Call on every attempt, including retries, inside the caller's transaction.
        Keep acquired locks until that transaction ends. Do not open, commit or
        roll back a transaction, or execute the requested business change.

        Args:
            access: Authenticated caller identity, without a current account-status
                or permission snapshot.
            request: Target and permission details required by this family.
                The trusted workflow selects the permission needed for its work.

        Returns:
            The family's checked facts and authorized scope for this transaction.
            The result does not establish permission for a later attempt.

        Raises:
            ResourceNotFoundError: The target is unavailable under the family's
                visibility rules.
            AccessDeniedError: The target is visible but the caller or requested
                operation fails the family's access requirements.
            DependencyUnavailableError: A required dependency cannot supply
                current authorization facts.
        """
        ...
