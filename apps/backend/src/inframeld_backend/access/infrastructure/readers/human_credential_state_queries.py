from uuid import UUID

from sqlalchemy import ColumnElement, Nullable, Select, and_, exists, select
from sqlalchemy.sql.selectable import Exists, ScalarSelect

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class HumanCredentialStateQueries:
    """Compose typed security projections without opening sessions or executing readers."""

    @staticmethod
    def for_identity(
        identity: VerifiedHumanIdentityDTO,
    ) -> Select[tuple[UUID, int | None, bool, bool]]:
        history = (
            exists()
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                IdentityRecoveryAdmissionRow.authority == identity.authority.value,
                IdentityRecoveryAdmissionRow.subject == identity.subject.value,
            )
            .correlate(InstallationIdentityRow)
        )
        pending = (
            exists()
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                IdentityRecoveryAdmissionRow.authority == identity.authority.value,
                IdentityRecoveryAdmissionRow.subject == identity.subject.value,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .correlate(InstallationIdentityRow)
        )
        return (
            select(
                InstallationIdentityRow.installation_id,
                Nullable(HumanCredentialVersionRow.version),
                pending,
                history,
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(
                HumanCredentialVersionRow,
                and_(
                    HumanCredentialVersionRow.installation_id
                    == InstallationIdentityRow.installation_id,
                    HumanCredentialVersionRow.authority == identity.authority.value,
                    HumanCredentialVersionRow.subject == identity.subject.value,
                ),
            )
            .where(InstallationIdentityRow.singleton_key == 1)
        )

    @staticmethod
    def binding_matches_actor(binding: HumanOAuthCredentialBindingDTO) -> Exists:
        """Match the current installation and identity link to the outer principal."""
        return (
            select(InstallationIdentityRow.installation_id)
            .join(HumanIdentityLinkRow, HumanIdentityLinkRow.principal_id == PrincipalRow.id)
            .where(*HumanCredentialStateQueries._actor_binding_conditions(binding))
            .exists()
            .correlate(PrincipalRow)
        )

    @staticmethod
    def version_for_actor(binding: HumanOAuthCredentialBindingDTO) -> ScalarSelect[int]:
        """Select the matching actor binding's version, which may be absent in storage."""
        return (
            select(HumanCredentialVersionRow.version)
            .select_from(HumanCredentialVersionRow)
            .join(
                InstallationIdentityRow,
                InstallationIdentityRow.installation_id
                == HumanCredentialVersionRow.installation_id,
            )
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == HumanCredentialVersionRow.authority,
                    HumanIdentityLinkRow.subject == HumanCredentialVersionRow.subject,
                ),
            )
            .where(*HumanCredentialStateQueries._actor_binding_conditions(binding))
            .correlate(PrincipalRow)
            .scalar_subquery()
        )

    @staticmethod
    def _actor_binding_conditions(
        binding: HumanOAuthCredentialBindingDTO,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            InstallationIdentityRow.singleton_key == 1,
            InstallationIdentityRow.installation_id == binding.installation_id.value,
            HumanIdentityLinkRow.principal_id == PrincipalRow.id,
            HumanIdentityLinkRow.authority == binding.identity.authority.value,
            HumanIdentityLinkRow.subject == binding.identity.subject.value,
        )
