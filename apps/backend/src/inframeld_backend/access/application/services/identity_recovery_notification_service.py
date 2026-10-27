import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_association_facts_dto import (
    IdentityRecoveryAssociationFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_notification_result_dto import (
    IdentityRecoveryNotificationResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.protocols.identity_recovery_admitter import (
    IdentityRecoveryAdmitter,
)
from inframeld_backend.access.application.protocols.identity_recovery_association_facts_reader import (
    IdentityRecoveryAssociationFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_evidence_writer import (
    IdentityRecoveryEvidenceWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_notification_handler import (
    IdentityRecoveryNotificationHandler,
)
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryNotificationService(IdentityRecoveryNotificationHandler):
    def __init__(
        self,
        transactions: TransactionManager,
        admitter: IdentityRecoveryAdmitter,
        evidence: IdentityRecoveryEvidenceWriter,
        recoveries: IdentityRecoveryRepository,
        *,
        installation_id: InstallationId,
        facts: IdentityRecoveryAssociationFactsReader,
        database_timeout_seconds: float = 5.0,
    ) -> None:
        self._facts = facts
        self._transactions = transactions
        self._admitter = admitter
        self._evidence = evidence
        self._recoveries = recoveries
        self._installation_id = installation_id
        self._database_timeout = database_timeout_seconds

    @override
    async def admit(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryNotificationResultDTO:
        async with self._database_stage():
            async with self._transactions.begin():
                operation_id = await self._admitter.admit(event)
                await self._evidence.record_admission(event, operation_id)

            return IdentityRecoveryNotificationResultDTO(
                operation_id, IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED
            )

    @override
    async def associate_settings(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        async with self._database_stage():
            async with self._transactions.begin():
                facts = await self._facts.read(evidence)
                admission = self._select_settings_admission(evidence, facts)
                if admission is not None:
                    await self._evidence.record_settings_association(evidence, admission)
            if admission is None:
                return None
            return IdentityRecoveryNotificationResultDTO(
                admission.operation_id, IdentityRecoveryEvidenceType.SETTINGS_FLOW_ASSOCIATED
            )

    @override
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        async with self._database_stage():
            async with self._transactions.begin():
                facts = await self._facts.read(evidence)
                admission = self._select_password_admission(evidence, facts)

                if admission is None:
                    return None

                recovery = await self._recoveries.get(
                    installation_id=self._installation_id,
                    authority=admission.event.identity.authority,
                    flow_id=admission.event.flow_id,
                )

                if recovery.subject != evidence.identity.subject or recovery.identity != (
                    self._installation_id,
                    admission.event.identity.authority,
                    admission.event.flow_id,
                ):
                    raise RuntimeError("The loaded recovery does not match its original admission.")

                recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)

                await self._recoveries.save(recovery)

                recorded_at = await self._evidence.record_password_saved(evidence, admission)
                if not recovery.is_released and not recovery.is_cleanup_confirmed:
                    budget = IdentityRecoveryCleanupRunBudget(recorded_at)
                    await self._evidence.ensure_initial_cleanup_handoff(
                        evidence, admission, budget=budget
                    )

            return IdentityRecoveryNotificationResultDTO(
                admission.operation_id, IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
            )

    def _select_settings_admission(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        facts: IdentityRecoveryAssociationFactsDTO,
    ) -> IdentityRecoveryAdmissionDTO | None:
        session = facts.session_binding
        if session is not None:
            if session.session_id != evidence.session_id:
                raise RuntimeError("The facts do not match the requested native session.")
            if session.identity != evidence.identity:
                raise ConflictError("The native session belongs to another recovery identity.")

        source = evidence.source_recovery_flow_id
        if source is not None:
            admission = self._require_matching_admission(facts.source_admission, evidence)
            if admission.event.flow_id != source:
                raise RuntimeError("The facts do not match the requested recovery source.")
            if session is not None and session.operation_id != admission.operation_id:
                raise ConflictError(
                    "The native session is already associated with another recovery."
                )
        elif session is not None:
            admission = self._require_matching_admission(facts.session_admission, evidence)
            if session.operation_id != admission.operation_id:
                raise RuntimeError("The session facts do not match their original admission.")
        else:
            if facts.settings_binding is not None:
                raise ConflictError("The native settings binding has changed.")
            return None

        self._require_version(facts)
        settings = facts.settings_binding
        if settings is not None:
            if settings.settings_flow_id != evidence.settings_flow_id:
                raise RuntimeError("The facts do not match the requested settings flow.")
            if (
                settings.identity,
                settings.operation_id,
                settings.session_id,
                settings.source_recovery_flow_id,
            ) != (evidence.identity, admission.operation_id, evidence.session_id, source):
                raise ConflictError("The native settings binding conflicts.")
        return admission

    def _select_password_admission(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        facts: IdentityRecoveryAssociationFactsDTO,
    ) -> IdentityRecoveryAdmissionDTO | None:
        settings = facts.settings_binding
        if settings is None:
            if evidence.source_recovery_flow_id is not None or facts.session_binding is not None:
                raise ConflictError(
                    "Password evidence requires an existing native settings association."
                )
            return None

        if settings.settings_flow_id != evidence.settings_flow_id:
            raise RuntimeError("The facts do not match the requested settings flow.")

        if (settings.identity, settings.session_id) != (evidence.identity, evidence.session_id):
            raise ConflictError("Password evidence does not match its native settings association.")

        admission = self._require_matching_admission(facts.settings_admission, evidence)

        if settings.operation_id != admission.operation_id:
            raise RuntimeError("The settings facts do not match their original admission.")

        if (
            evidence.source_recovery_flow_id is not None
            and evidence.source_recovery_flow_id != admission.event.flow_id
        ):
            raise ConflictError("Password evidence names a different original recovery.")

        self._require_version(facts)

        return admission

    def _require_matching_admission(
        self,
        admission: IdentityRecoveryAdmissionDTO | None,
        evidence: IdentityRecoverySettingsEvidenceDTO,
    ) -> IdentityRecoveryAdmissionDTO:
        if admission is None or admission.event.identity != evidence.identity:
            raise ConflictError(
                "Native evidence requires its matching original recovery admission."
            )
        return admission

    def _require_version(self, facts: IdentityRecoveryAssociationFactsDTO) -> None:
        if facts.current_version is None:
            raise DependencyUnavailableError(
                "Recovery requires its original credential version state."
            )

    @asynccontextmanager
    async def _database_stage(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self._database_timeout):
                yield
        except TimeoutError:
            raise DependencyUnavailableError() from None
