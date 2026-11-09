import asyncio
from datetime import UTC
from hmac import compare_digest
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_facts_reader import (
    StrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_writer import (
    StrandedAuthorityRepairWriter,
)
from inframeld_backend.access.application.protocols.stranded_authority_repairer import (
    StrandedAuthorityRepairer,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.stranded_authority_fingerprint_service import (
    StrandedAuthorityFingerprintService,
)
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.policies.stranded_authority_repair_policy import (
    StrandedAuthorityRepairPolicy,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class StrandedAuthorityRepairService(StrandedAuthorityRepairer):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        repair_facts_reader: StrandedAuthorityRepairFactsReader,
        repair_writer: StrandedAuthorityRepairWriter,
        repair_fingerprint_service: StrandedAuthorityFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._repair_facts_reader = repair_facts_reader
        self._repair_writer = repair_writer
        self._repair_fingerprint_service = repair_fingerprint_service

    @override
    async def repair(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairResultDTO:
        binding = access.authentication_evidence
        code = StrandedAuthorityMaintenanceErrorCode
        if not isinstance(binding, HumanOAuthCredentialBindingDTO):
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF)
        try:
            identity_id = UUID(binding.identity.subject.value)
        except ValueError:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        if identity_id != command.expected_identity_id:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if binding.installation_id != command.expected_installation_id:
            raise StrandedAuthorityMaintenanceError(code.INSTALLATION_MISMATCH)
        fingerprint = self._repair_fingerprint_service.for_repair(command, binding.identity)
        try:
            async with asyncio.timeout(5):
                async with self._transaction_manager.begin():
                    return await self._repair(access, command, binding.identity, fingerprint)
        except TimeoutError:
            raise StrandedAuthorityMaintenanceError(code.DEPENDENCY_UNAVAILABLE) from None

    async def _repair(
        self,
        access: AccessContextDTO,
        command: RepairStrandedAuthorityCommand,
        identity: VerifiedHumanIdentityDTO,
        fingerprint: RequestFingerprint,
    ) -> StrandedAuthorityRepairResultDTO:
        """Check the host request against current target facts before recording an authority repair."""
        code = StrandedAuthorityMaintenanceErrorCode
        facts = await self._repair_facts_reader.read(access=access, command=command)
        if facts is None:
            raise StrandedAuthorityMaintenanceError(code.IDENTITY_INELIGIBLE)
        if facts.installation_id != command.expected_installation_id:
            raise StrandedAuthorityMaintenanceError(code.INSTALLATION_MISMATCH)
        if (
            facts.responsibility != command.responsibility
            or facts.recipient.id != access.actor_principal_id
        ):
            raise RuntimeError("Repair facts changed the verified recipient or responsibility.")
        requires_project = not (
            isinstance(command.responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(command.responsibility.target, OrganizationGrantTargetDTO)
        )
        if (
            not requires_project
            and isinstance(command.responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(command.responsibility.target, OrganizationGrantTargetDTO)
            and command.responsibility.target.organization_id != facts.recipient.organization_id
        ):
            raise RuntimeError("Repair facts changed the target Organization.")
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.recipient,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if (
            not HumanAuthenticationPolicy.may_authenticate(eligibility)
            or not facts.target_exists
            or (
                requires_project
                and (
                    facts.project_status is None
                    or not ProjectVisibilityPolicy.may_view_project(
                        principal_status=facts.recipient.status,
                        project_status=facts.project_status,
                        is_project_member=facts.is_project_member,
                    )
                )
            )
        ):
            raise StrandedAuthorityMaintenanceError(code.IDENTITY_INELIGIBLE)

        recorded = await self._repair_facts_reader.receipt(
            installation_id=facts.installation_id, operation_id=command.operation_id
        )
        if recorded is not None:
            return self._replay(recorded, facts, command, identity, fingerprint)
        if facts.access_revision != command.expected_access_revision:
            raise StrandedAuthorityMaintenanceError(code.STALE_REVISION)
        if facts.eligible_grantor_exists is None:
            raise StrandedAuthorityMaintenanceError(code.DEPENDENCY_UNAVAILABLE)
        if not StrandedAuthorityRepairPolicy.may_assign(
            recipient_access=eligibility,
            requires_project=requires_project,
            is_project_member=facts.is_project_member,
            project_status=facts.project_status,
            eligible_grantor_exists=facts.eligible_grantor_exists,
        ):
            raise StrandedAuthorityMaintenanceError(code.NOT_STRANDED)
        if facts.observed_at.tzinfo is None:
            raise RuntimeError("Repair authorization requires aware database time.")

        if facts.access_revision == RevisionValidation.MAX_VALUE:
            raise StrandedAuthorityMaintenanceError(code.REVISION_EXHAUSTED)

        result = StrandedAuthorityRepairResultDTO(
            operation_id=command.operation_id,
            installation_id=facts.installation_id,
            organization_id=facts.recipient.organization_id,
            responsibility=facts.responsibility,
            recipient_id=facts.recipient.id,
            access_revision=facts.access_revision + 1,
        )
        receipt = StrandedAuthorityRepairReceiptDTO(
            fingerprint=fingerprint,
            identity=identity,
            expected_identity_id=command.expected_identity_id,
            operator_label=command.operator_label,
            reason=command.reason,
            before_revision=facts.access_revision,
            authorized_at=facts.observed_at.astimezone(UTC),
            result=result,
        )
        if not await self._repair_writer.record(receipt):
            winner = await self._repair_facts_reader.receipt(
                installation_id=facts.installation_id, operation_id=command.operation_id
            )
            if winner is None:
                raise RuntimeError("The winning repair receipt is unavailable.")
            return self._replay(winner, facts, command, identity, fingerprint)
        await self._repair_writer.assign(facts=facts, receipt=receipt)
        return result

    @staticmethod
    def _replay(
        receipt: StrandedAuthorityRepairReceiptDTO,
        facts: StrandedAuthorityRepairFactsDTO,
        command: RepairStrandedAuthorityCommand,
        identity: VerifiedHumanIdentityDTO,
        fingerprint: RequestFingerprint,
    ) -> StrandedAuthorityRepairResultDTO:
        """Return a prior repair only when its retained request meaning still matches."""
        result = receipt.result
        if (
            not compare_digest(receipt.fingerprint.value, fingerprint.value)
            or receipt.identity != identity
            or receipt.expected_identity_id != command.expected_identity_id
            or (
                result.installation_id,
                result.organization_id,
                result.responsibility,
                result.recipient_id,
                result.operation_id,
            )
            != (
                facts.installation_id,
                facts.recipient.organization_id,
                command.responsibility,
                facts.recipient.id,
                command.operation_id,
            )
        ):
            raise StrandedAuthorityMaintenanceError(
                StrandedAuthorityMaintenanceErrorCode.KEY_REUSED
            )
        if result.access_revision != receipt.before_revision + 1:
            raise RuntimeError("The original repair result has inconsistent revisions.")
        return result
