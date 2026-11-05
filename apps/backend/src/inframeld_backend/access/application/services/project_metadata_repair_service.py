import asyncio
from datetime import UTC
from hmac import compare_digest
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
    ProjectMetadataMaintenanceError,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_facts_reader import (
    ProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_writer import (
    ProjectMetadataRepairWriter,
)
from inframeld_backend.access.application.protocols.project_metadata_repairer import (
    ProjectMetadataRepairer,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.policies.project_metadata_repair_policy import (
    ProjectMetadataRepairPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectMetadataRepairService(ProjectMetadataRepairer):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        metadata_repair_facts_reader: ProjectMetadataRepairFactsReader,
        metadata_repair_writer: ProjectMetadataRepairWriter,
        metadata_fingerprint_service: ProjectMetadataFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._metadata_repair_facts_reader = metadata_repair_facts_reader
        self._metadata_repair_writer = metadata_repair_writer
        self._metadata_fingerprint_service = metadata_fingerprint_service

    @override
    async def repair(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairResultDTO:
        binding = access.authentication_evidence
        code = ProjectMetadataMaintenanceErrorCode
        if not isinstance(binding, HumanOAuthCredentialBindingDTO):
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF)
        try:
            identity_id = UUID(binding.identity.subject.value)
        except ValueError:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        if identity_id != command.expected_identity_id:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if binding.installation_id != command.expected_installation_id:
            raise ProjectMetadataMaintenanceError(code.INSTALLATION_MISMATCH)
        fingerprint = self._metadata_fingerprint_service.for_repair(command, binding.identity)
        try:
            async with asyncio.timeout(5):
                async with self._transaction_manager.begin():
                    return await self._repair(access, command, binding.identity, fingerprint)
        except TimeoutError:
            raise ProjectMetadataMaintenanceError(code.DEPENDENCY_UNAVAILABLE) from None

    async def _repair(
        self,
        access: AccessContextDTO,
        command: RepairProjectMetadataAuthorityCommand,
        identity: VerifiedHumanIdentityDTO,
        fingerprint: RequestFingerprint,
    ) -> ProjectMetadataRepairResultDTO:
        """Check the host request against current Project facts before recording an authority repair."""
        code = ProjectMetadataMaintenanceErrorCode
        facts = await self._metadata_repair_facts_reader.read(access=access, command=command)
        if facts is None:
            raise ProjectMetadataMaintenanceError(code.IDENTITY_INELIGIBLE)
        if facts.installation_id != command.expected_installation_id:
            raise ProjectMetadataMaintenanceError(code.INSTALLATION_MISMATCH)
        if (
            facts.project_id != command.project_id
            or facts.recipient.id != access.actor_principal_id
        ):
            raise RuntimeError("Repair facts changed the verified recipient or Project.")
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.recipient,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if not HumanAuthenticationPolicy.may_authenticate(
            eligibility
        ) or not ProjectVisibilityPolicy.may_view_project(
            principal_status=facts.recipient.status,
            project_status=facts.project_status,
            is_project_member=facts.is_project_member,
        ):
            raise ProjectMetadataMaintenanceError(code.IDENTITY_INELIGIBLE)

        recorded = await self._metadata_repair_facts_reader.receipt(
            installation_id=facts.installation_id, operation_id=command.operation_id
        )
        if recorded is not None:
            return self._replay(recorded, facts, command, identity, fingerprint)
        if facts.access_revision != command.expected_access_revision:
            raise ProjectMetadataMaintenanceError(code.STALE_REVISION)
        if facts.eligible_grantor_exists is None:
            raise ProjectMetadataMaintenanceError(code.DEPENDENCY_UNAVAILABLE)
        if not ProjectMetadataRepairPolicy.may_assign(
            recipient_access=eligibility,
            is_project_member=facts.is_project_member,
            project_status=facts.project_status,
            eligible_grantor_exists=facts.eligible_grantor_exists,
        ):
            raise ProjectMetadataMaintenanceError(code.NOT_STRANDED)
        if facts.observed_at.tzinfo is None:
            raise RuntimeError("Repair authorization requires aware database time.")

        if facts.access_revision == RevisionValidation.MAX_VALUE:
            raise ProjectMetadataMaintenanceError(code.REVISION_EXHAUSTED)

        result = ProjectMetadataRepairResultDTO(
            operation_id=command.operation_id,
            installation_id=facts.installation_id,
            organization_id=facts.recipient.organization_id,
            project_id=facts.project_id,
            recipient_id=facts.recipient.id,
            access_revision=facts.access_revision + 1,
        )
        receipt = ProjectMetadataRepairReceiptDTO(
            fingerprint=fingerprint,
            identity=identity,
            expected_identity_id=command.expected_identity_id,
            operator_label=command.operator_label,
            reason=command.reason,
            before_revision=facts.access_revision,
            authorized_at=facts.observed_at.astimezone(UTC),
            result=result,
        )
        if not await self._metadata_repair_writer.record(receipt):
            winner = await self._metadata_repair_facts_reader.receipt(
                installation_id=facts.installation_id, operation_id=command.operation_id
            )
            if winner is None:
                raise RuntimeError("The winning repair receipt is unavailable.")
            return self._replay(winner, facts, command, identity, fingerprint)
        await self._metadata_repair_writer.assign(facts=facts, receipt=receipt)
        return result

    @staticmethod
    def _replay(
        receipt: ProjectMetadataRepairReceiptDTO,
        facts: ProjectMetadataRepairFactsDTO,
        command: RepairProjectMetadataAuthorityCommand,
        identity: VerifiedHumanIdentityDTO,
        fingerprint: RequestFingerprint,
    ) -> ProjectMetadataRepairResultDTO:
        """Return a prior repair only when its retained request meaning still matches."""
        result = receipt.result
        if (
            not compare_digest(receipt.fingerprint.value, fingerprint.value)
            or receipt.identity != identity
            or receipt.expected_identity_id != command.expected_identity_id
            or (
                result.installation_id,
                result.organization_id,
                result.project_id,
                result.recipient_id,
                result.operation_id,
            )
            != (
                facts.installation_id,
                facts.recipient.organization_id,
                command.project_id,
                facts.recipient.id,
                command.operation_id,
            )
        ):
            raise ProjectMetadataMaintenanceError(ProjectMetadataMaintenanceErrorCode.KEY_REUSED)
        if result.access_revision != receipt.before_revision + 1:
            raise RuntimeError("The original repair result has inconsistent revisions.")
        return result
