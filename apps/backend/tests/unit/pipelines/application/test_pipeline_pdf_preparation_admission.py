from unittest.mock import Mock
from uuid import uuid4

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.pipelines.application.services.pipeline_pdf_preparation_admission_service import (
    PipelinePdfPreparationAdmissionService,
)
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@pytest.mark.asyncio
async def test_browser_session_cannot_admit_durable_pdf_preparation() -> None:
    access = AccessContextDTO(
        PrincipalId(uuid4()),
        BrowserSessionAuthenticationDTO(
            VerifiedHumanIdentityDTO(IdentityAuthority("fixture"), IdentitySubject("alice")),
            InstallationId(uuid4()),
            HumanCredentialVersion(1),
        ),
    )

    service = PipelinePdfPreparationAdmissionService(
        transactions=Mock(),
        facts=Mock(),
        authority=Mock(),
        idempotency=Mock(),
        fingerprints=Mock(),
        history=Mock(),
        jobs=Mock(),
        audit=Mock(),
    )

    with pytest.raises(InvalidInputError, match="verified OAuth credential generation"):
        await service.admit(
            access=access,
            project_id=ProjectId(uuid4()),
            pipeline_id=PipelineId(uuid4()),
            configuration_revision=1,
            collection_revision_id=CollectionRevisionId(uuid4()),
            key=IdempotencyKey("prepare-alice"),
            request_id=RequestId(uuid4()),
        )
