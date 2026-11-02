from inframeld_backend.access.application.dtos.my_organization_access_dto import (
    MyOrganizationAccessDTO,
)
from inframeld_backend.access.http.responses.my_organization_access_response import (
    MyOrganizationAccessResponse,
)
from inframeld_backend.access.http.responses.own_organization_grant_response import (
    OwnOrganizationGrantResponse,
)


class OrganizationAccessMapper:
    @staticmethod
    def response(result: MyOrganizationAccessDTO) -> MyOrganizationAccessResponse:
        return MyOrganizationAccessResponse(
            organization_id=result.organization_id.value,
            principal_id=result.principal_id.value,
            access_revision=result.access_revision,
            grants=tuple(
                OwnOrganizationGrantResponse.model_validate(
                    {"action_id": grant.action_id.value, "can_grant": grant.can_grant}
                )
                for grant in result.grants
            ),
        )
