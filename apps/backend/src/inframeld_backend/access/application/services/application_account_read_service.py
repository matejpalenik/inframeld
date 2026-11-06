import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_account_read_facts_dto import (
    ApplicationAccountReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_facts_dto import (
    ApplicationKeysFactsDTO,
)
from inframeld_backend.access.application.dtos.application_keys_page_dto import (
    ApplicationKeysPageDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.application_account_facts_reader import (
    ApplicationAccountFactsReader,
)
from inframeld_backend.access.application.protocols.application_account_reader import (
    ApplicationAccountReader,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.application_keys_cursor import (
    ApplicationKeysCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class ApplicationAccountReadService(ApplicationAccountReader):
    def __init__(self, account_facts_reader: ApplicationAccountFactsReader) -> None:
        self._account_facts_reader = account_facts_reader

    @override
    async def get_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, principal_id: PrincipalId
    ) -> ApplicationAccountMetadataDTO:
        return await self._read_account(access, project_id, principal_id)

    @override
    async def resolve_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, name: ResourceName
    ) -> ApplicationAccountMetadataDTO:
        return await self._read_account(access, project_id, name)

    @override
    async def list_keys(
        self, *, access: AccessContextDTO, query: ListApplicationKeysQuery
    ) -> ApplicationKeysPageDTO:
        try:
            cursor = (
                ApplicationKeysCursor.from_token(query.cursor) if query.cursor is not None else None
            )
        except ValueError as error:
            raise InvalidInputError(
                "The continuation cursor is invalid or incompatible."
            ) from error

        facts = await self._read_keys(
            access=access,
            project_id=query.project_id,
            application_principal_id=query.application_principal_id,
            key_id=None,
            after=cursor.after if cursor is not None else None,
            limit=query.limit,
        )
        account = facts.account.account
        if cursor is not None and (
            cursor.installation_id,
            cursor.organization_id,
            cursor.project_id,
            cursor.application_principal_id,
        ) != (
            facts.account.installation_id,
            account.organization_id,
            account.project_id,
            account.principal_id,
        ):
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")
        if len(facts.keys) > query.limit + 1:
            raise RuntimeError("The key metadata observation exceeded its page bound.")
        previous = cursor.after.value.int if cursor is not None else -1
        for key in facts.keys:
            if key.key_id.value.int <= previous:
                raise RuntimeError("The key metadata observation changed its position or order.")
            previous = key.key_id.value.int
        items = facts.keys[: query.limit]
        continuation = (
            ApplicationKeysCursor(
                facts.account.installation_id,
                account.organization_id,
                account.project_id,
                account.principal_id,
                items[-1].key_id,
            ).to_token()
            if len(facts.keys) > query.limit
            else None
        )
        return ApplicationKeysPageDTO(items, continuation)

    @override
    async def get_key(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId,
    ) -> ApplicationKeyMetadataDTO:
        facts = await self._read_keys(
            access=access,
            project_id=project_id,
            application_principal_id=application_principal_id,
            key_id=key_id,
            after=None,
            limit=1,
        )
        if not facts.keys:
            raise ResourceNotFoundError()
        if len(facts.keys) != 1 or facts.keys[0].key_id != key_id:
            raise RuntimeError("The key metadata observation changed its exact key.")
        return facts.keys[0]

    async def _read_account(
        self, access: AccessContextDTO, project_id: ProjectId, selector: PrincipalId | ResourceName
    ) -> ApplicationAccountMetadataDTO:
        try:
            async with asyncio.timeout(5):
                facts = await self._account_facts_reader.read_account(
                    access=access, project_id=project_id, selector=selector
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None
        checked = self._require_account(access, project_id, facts)
        account = checked.account
        if isinstance(selector, PrincipalId) and account.principal_id != selector:
            raise RuntimeError("The account metadata observation changed its principal.")
        if isinstance(selector, ResourceName) and account.name != selector:
            raise RuntimeError("The account metadata observation changed its exact Name.")
        return account

    async def _read_keys(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId | None,
        after: ApplicationKeyId | None,
        limit: int,
    ) -> ApplicationKeysFactsDTO:
        try:
            async with asyncio.timeout(5):
                facts = await self._account_facts_reader.read_keys(
                    access=access,
                    project_id=project_id,
                    application_principal_id=application_principal_id,
                    key_id=key_id,
                    after=after,
                    limit=limit,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None
        checked = self._require_account(
            access, project_id, facts.account if facts is not None else None
        )
        if checked.account.principal_id != application_principal_id:
            raise RuntimeError("The key metadata observation changed its application.")
        if not checked.can_read_keys:
            raise AccessDeniedError()
        if facts is None:
            raise RuntimeError("The key metadata observation disappeared.")
        for key in facts.keys:
            if (key.application_principal_id, key.project_id) != (
                application_principal_id,
                project_id,
            ):
                raise RuntimeError("The key metadata observation changed its owning scope.")
        return facts

    @staticmethod
    def _require_account(
        access: AccessContextDTO,
        project_id: ProjectId,
        facts: ApplicationAccountReadFactsDTO | None,
    ) -> ApplicationAccountReadFactsDTO:
        """Check current human authority before disclosing exact account or key facts."""
        if facts is None:
            raise ResourceNotFoundError()
        action, account = facts.action, facts.account
        if (
            action.principal.id != access.actor_principal_id
            or account.project_id != project_id
            or account.organization_id != action.principal.organization_id
        ):
            raise RuntimeError("The account metadata observation changed its actor or scope.")
        RevisionValidation.require(account.access_revision)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=action.principal.status,
            project_status=action.project_status,
            is_project_member=action.is_project_member,
        ):
            raise ResourceNotFoundError()
        if (
            action.principal.kind is not PrincipalKind.HUMAN
            or not PrincipalAccessPolicy.may_use_product(eligibility)
        ):
            raise AccessDeniedError()
        if not action.has_exact_action_grant:
            raise ResourceNotFoundError()
        return facts
