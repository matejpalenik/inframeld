from datetime import datetime, timedelta
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_request_dto import (
    DeletionStatusAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.deletion_status_authorizer import (
    DeletionStatusAuthorizer,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.protocols.deletion_status_projection_reader import (
    DeletionStatusProjectionReader,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class DeletionStatusReadService(DeletionStatusLookup):
    """Authorize current initiator scope and interpret retained content-free facts."""

    def __init__(
        self,
        deletion_status_authorizer: DeletionStatusAuthorizer,
        deletion_status_projection_reader: DeletionStatusProjectionReader,
    ) -> None:
        self._deletion_status_authorizer = deletion_status_authorizer
        self._deletion_status_projection_reader = deletion_status_projection_reader

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: GetDeletionStatusQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
        authorized = await self._deletion_status_authorizer.require_authorization(
            access=access,
            request=DeletionStatusAuthorizationRequestDTO(query.operation_id),
        )
        if (
            authorized.operation_id != query.operation_id
            or authorized.principal_id != access.actor_principal_id
        ):
            raise RuntimeError("Deletion status authorization returned a different scope.")

        stored = await self._deletion_status_projection_reader.read(authorization=authorized)
        if stored is None or not self._matches_binding(stored.binding, authorized):
            return UnresolvedOperationDTO()
        if not self._has_owner_observation(stored):
            return UnresolvedOperationDTO()

        expiry = self._retention(stored)
        if expiry is not None and expiry <= stored.observed_at:
            return UnresolvedOperationDTO()

        return RetainedDeletionStatusDTO(
            stored.binding.operation_id,
            stored.job_status,
            stored.admission_confirmed,
            stored.access_blocked,
            stored.application_shutdown_complete,
            stored.physical_cleanup_complete,
            expiry,
        )

    @staticmethod
    def _matches_binding(
        binding: DeletionStatusBindingDTO, authorization: DeletionStatusAuthorizationDTO
    ) -> bool:
        """Keep retained deletion facts bound to the authorized original operation."""
        return (
            binding.operation_id == authorization.operation_id
            and binding.installation_id == authorization.installation_id
            and binding.organization_id == authorization.organization_id
            and binding.initiator_principal_id == authorization.principal_id
            and binding.authority_family is OperationLookupAuthorityFamily.PROJECT_ACTION_USE
            and binding.action_id is not None
            and binding.action_id.value == ProjectAction.DELETE_PROJECT.value
        )

    @staticmethod
    def _has_owner_observation(stored: DeletionStatusObservationDTO) -> bool:
        """Distinguish absent owner evidence from a partial or incoherent observation."""
        if stored.owner_revision is None:
            if any(
                value is not None
                for value in (
                    stored.owner_observed_at,
                    stored.job_status,
                    stored.admission_confirmed,
                    stored.access_blocked,
                    stored.application_shutdown_complete,
                    stored.physical_cleanup_complete,
                    stored.unfinished_obligation,
                    stored.retention_started_at,
                    stored.expires_at,
                )
            ):
                raise DependencyUnavailableError()
            return False

        if type(stored.owner_revision) is not int or stored.owner_revision < 1:
            raise DependencyUnavailableError()
        return True

    @staticmethod
    def _retention(stored: DeletionStatusObservationDTO) -> datetime | None:
        """Validate retained timing and completion evidence before reporting an expiry."""
        binding = stored.binding
        if binding.retention_days is None or binding.retention_policy_version is None:
            raise DependencyUnavailableError()
        try:
            profile = DeletionStatusRetentionProfile(
                binding.retention_days, binding.retention_policy_version
            )
        except (TypeError, ValueError):
            raise DependencyUnavailableError() from None

        now = DeletionStatusReadService._require_utc(stored.observed_at)
        recorded = DeletionStatusReadService._require_utc(binding.recorded_at)
        observed = DeletionStatusReadService._require_utc(stored.owner_observed_at)
        if recorded > observed or observed > now:
            raise DependencyUnavailableError()
        for confirmed in (
            stored.admission_confirmed,
            stored.access_blocked,
            stored.application_shutdown_complete,
            stored.physical_cleanup_complete,
        ):
            if confirmed is not None and type(confirmed) is not bool:
                raise DependencyUnavailableError()
        if stored.job_status is not None and type(stored.job_status) is not JobStatus:
            raise DependencyUnavailableError()

        if stored.retention_started_at is None:
            if stored.expires_at is not None or stored.physical_cleanup_complete is True:
                raise DependencyUnavailableError()
            DeletionStatusReadService._require_unfinished_obligation(stored)
            return None

        started = DeletionStatusReadService._require_utc(stored.retention_started_at)
        expiry = DeletionStatusReadService._require_utc(stored.expires_at)
        if (
            stored.unfinished_obligation is not None
            or not all(
                confirmed is True
                for confirmed in (
                    stored.admission_confirmed,
                    stored.access_blocked,
                    stored.application_shutdown_complete,
                    stored.physical_cleanup_complete,
                )
            )
            or not recorded <= started <= observed
        ):
            raise DependencyUnavailableError()
        try:
            expected_expiry = started + timedelta(days=profile.days)
        except OverflowError:
            raise DependencyUnavailableError() from None
        if expiry != expected_expiry:
            raise DependencyUnavailableError()
        return expiry

    @staticmethod
    def _require_unfinished_obligation(stored: DeletionStatusObservationDTO) -> None:
        """Reject cleanup obligations that disagree with their retained deletion scope."""
        obligation = stored.unfinished_obligation
        binding = stored.binding
        if obligation is None or (
            obligation.operation_id != binding.operation_id
            or obligation.installation_id != binding.installation_id
            or obligation.organization_id != binding.organization_id
            or obligation.project_id != binding.project_id
            or obligation.initiator_principal_id != binding.initiator_principal_id
            or type(obligation.source_revision) is not int
            or obligation.source_revision < 1
        ):
            raise DependencyUnavailableError()
        observed = DeletionStatusReadService._require_utc(obligation.observed_at)
        if not binding.recorded_at <= observed <= stored.observed_at:
            raise DependencyUnavailableError()

    @staticmethod
    def _require_utc(value: datetime | None) -> datetime:
        """Require an aware timestamp before comparing retained deletion evidence."""
        if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
            raise DependencyUnavailableError()
        return value
