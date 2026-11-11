"""Direct native operation calls, with one explicit sync/async binding inventory."""

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import inframeld_sdk
import inframeld_sdk_fixtures
from inframeld_sdk.api.access_api import AccessApi
from inframeld_sdk.api.discovery_api import DiscoveryApi
from inframeld_sdk.api.health_api import HealthApi
from inframeld_sdk.api.operations_api import OperationsApi
from inframeld_sdk.models.access_group_action_grant_request import AccessGroupActionGrantRequest
from inframeld_sdk.models.access_group_creation_request import AccessGroupCreationRequest
from inframeld_sdk.models.access_group_manager_request import AccessGroupManagerRequest
from inframeld_sdk.models.access_group_membership_request import AccessGroupMembershipRequest
from inframeld_sdk.models.application_account_action_grant_request import (
    ApplicationAccountActionGrantRequest,
)
from inframeld_sdk.models.application_account_creation_request import (
    ApplicationAccountCreationRequest,
)
from inframeld_sdk.models.application_key_issue_request import ApplicationKeyIssueRequest
from inframeld_sdk.models.application_key_revocation_request import ApplicationKeyRevocationRequest
from inframeld_sdk.models.grant_target_kind import GrantTargetKind
from inframeld_sdk.models.human_admission_request import HumanAdmissionRequest
from inframeld_sdk.models.human_o_auth_consent_request import HumanOAuthConsentRequest
from inframeld_sdk.models.invitation_activation_request import InvitationActivationRequest
from inframeld_sdk.models.invitation_issue_request import InvitationIssueRequest
from inframeld_sdk.models.invitation_preview_request import InvitationPreviewRequest
from inframeld_sdk.models.invitation_revocation_request import InvitationRevocationRequest
from inframeld_sdk.models.organization_action_grant_request import OrganizationActionGrantRequest
from inframeld_sdk.models.original_operation_lookup_request import OriginalOperationLookupRequest
from inframeld_sdk.models.project_action_grant_request import ProjectActionGrantRequest
from inframeld_sdk.models.project_creation_request import ProjectCreationRequest
from inframeld_sdk.models.project_membership_request import ProjectMembershipRequest
from inframeld_sdk.models.project_metadata_update_request import ProjectMetadataUpdateRequest
from inframeld_sdk.models.project_upload_default_request import ProjectUploadDefaultRequest
from inframeld_sdk_fixtures.api.default_api import DefaultApi
from inframeld_sdk_fixtures.models.contract_fixture_payload import ContractFixturePayload
from observations import NativeResponse
from protocol import Call, Operation


@dataclass(frozen=True)
class Clients:
    production: inframeld_sdk.ApiClient
    fixtures: inframeld_sdk_fixtures.ApiClient


def string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a string in the driver call")
    return value


def list_organization_action_grants_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_organization_action_grants_sync_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_organization_action_grants_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_organization_action_grants_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def set_organization_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).set_organization_action_grant_sync_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        organization_action_grant_request=OrganizationActionGrantRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def set_organization_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).set_organization_action_grant_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        organization_action_grant_request=OrganizationActionGrantRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_organization_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_organization_action_grant_sync_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_organization_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_organization_action_grant_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def list_access_group_action_grants_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_access_group_action_grants_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_access_group_action_grants_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_access_group_action_grants_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def set_access_group_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).set_access_group_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_action_grant_request=AccessGroupActionGrantRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def set_access_group_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).set_access_group_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_action_grant_request=AccessGroupActionGrantRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_access_group_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_access_group_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_access_group_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_access_group_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def list_application_account_action_grants_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_application_account_action_grants_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_application_account_action_grants_async(
    clients: Clients, call: Call
) -> NativeResponse:
    return await AccessApi(
        clients.production
    ).list_application_account_action_grants_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def set_application_account_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).set_application_account_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        application_account_action_grant_request=ApplicationAccountActionGrantRequest.model_validate(
            call.body
        ),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def set_application_account_action_grant_async(
    clients: Clients, call: Call
) -> NativeResponse:
    return await AccessApi(clients.production).set_application_account_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        application_account_action_grant_request=ApplicationAccountActionGrantRequest.model_validate(
            call.body
        ),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_application_account_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(
        clients.production
    ).remove_application_account_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_application_account_action_grant_async(
    clients: Clients, call: Call
) -> NativeResponse:
    return await AccessApi(
        clients.production
    ).remove_application_account_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def project_grant_recipients_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_project_grant_recipients_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        target_kind=GrantTargetKind(string(call.query["targetKind"])),
        target_id=UUID(string(call.query["targetId"])),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def project_grant_recipients_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_project_grant_recipients_with_http_info(
        project_id=UUID(call.path["project_id"]),
        target_kind=GrantTargetKind(string(call.query["targetKind"])),
        target_id=UUID(string(call.query["targetId"])),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def my_project_access_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_my_project_access_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def my_project_access_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_my_project_access_with_http_info(
        project_id=UUID(call.path["project_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def set_project_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).set_project_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        project_action_grant_request=project_grant_body(call),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def set_project_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).set_project_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        idempotency_key=call.headers["Idempotency-Key"],
        project_action_grant_request=project_grant_body(call),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_project_action_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_project_action_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_project_action_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_project_action_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        recipient_principal_id=UUID(call.path["recipient_principal_id"]),
        action_id=call.path["action_id"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Expected an integer in the driver call")
    return value


def project_grant_body(call: Call) -> ProjectActionGrantRequest:
    if not call.unchecked_model:
        return ProjectActionGrantRequest.model_validate(call.body)
    if call.body is None:
        raise ValueError("Missing body for unchecked server-validation case")
    return ProjectActionGrantRequest.model_construct(
        can_grant=call.body["canGrant"],
        expected_access_revision=integer(call.body["expectedAccessRevision"]),
    )


def payload_body(call: Call) -> ContractFixturePayload:
    value = ContractFixturePayload.from_dict(call.body)
    if value is None:
        raise ValueError("Payload requires a body")
    return value


def discovery_sync(clients: Clients, call: Call) -> NativeResponse:
    return DiscoveryApi(clients.production).get_protected_resource_metadata_sync_with_http_info(
        _headers=call.headers, _request_timeout=call.timeout / 1000
    )


async def discovery_async(clients: Clients, call: Call) -> NativeResponse:
    return await DiscoveryApi(clients.production).get_protected_resource_metadata_with_http_info(
        _headers=call.headers, _request_timeout=call.timeout / 1000
    )


def discovery_path_sync(clients: Clients, call: Call) -> NativeResponse:
    assert call.path is not None
    return DiscoveryApi(
        clients.production
    ).get_protected_resource_metadata_for_path_sync_with_http_info(
        var_resource_path=call.path["resource_path"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def discovery_path_async(clients: Clients, call: Call) -> NativeResponse:
    assert call.path is not None
    return await DiscoveryApi(
        clients.production
    ).get_protected_resource_metadata_for_path_with_http_info(
        var_resource_path=call.path["resource_path"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def health_sync(clients: Clients, call: Call) -> NativeResponse:
    return HealthApi(clients.production).get_health_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def health_async(clients: Clients, call: Call) -> NativeResponse:
    return await HealthApi(clients.production).get_health_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def session_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_current_session_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def session_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_current_session_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def application_session_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_current_application_session_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def application_session_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_current_application_session_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def inspect_consent_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).inspect_human_o_auth_consent_sync_with_http_info(
        consent_challenge=string(call.query["consent_challenge"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def inspect_consent_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).inspect_human_o_auth_consent_with_http_info(
        consent_challenge=string(call.query["consent_challenge"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def decide_consent_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).decide_human_o_auth_consent_sync_with_http_info(
        human_o_auth_consent_request=HumanOAuthConsentRequest.model_validate(call.body),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def decide_consent_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).decide_human_o_auth_consent_with_http_info(
        human_o_auth_consent_request=HumanOAuthConsentRequest.model_validate(call.body),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def organization_access_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_my_organization_access_sync_with_http_info(
        _headers=call.headers, _request_timeout=call.timeout / 1000
    )


async def organization_access_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_my_organization_access_with_http_info(
        _headers=call.headers, _request_timeout=call.timeout / 1000
    )


def human_admission_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).admit_human_sync_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        human_admission_request=HumanAdmissionRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def human_admission_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).admit_human_with_http_info(
        organization_id=UUID(call.path["organization_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        human_admission_request=HumanAdmissionRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def create_application_account_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).create_application_account_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_account_creation_request=ApplicationAccountCreationRequest.model_validate(
            call.body
        ),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def create_application_account_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).create_application_account_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_account_creation_request=ApplicationAccountCreationRequest.model_validate(
            call.body
        ),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def delete_application_account_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).delete_application_account_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def delete_application_account_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).delete_application_account_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def get_application_account_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_application_account_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def get_application_account_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_application_account_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def resolve_application_account_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).resolve_application_account_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        name=string(call.query["name"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def resolve_application_account_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).resolve_application_account_with_http_info(
        project_id=UUID(call.path["project_id"]),
        name=string(call.query["name"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def list_application_keys_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_application_keys_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_application_keys_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_application_keys_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def get_application_key_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_application_key_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        key_id=UUID(call.path["key_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def get_application_key_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_application_key_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        key_id=UUID(call.path["key_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def create_project_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).create_project_sync_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        project_creation_request=ProjectCreationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def create_project_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).create_project_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        project_creation_request=ProjectCreationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def project_member_add_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).add_project_member_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_membership_request=ProjectMembershipRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def project_member_add_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).add_project_member_with_http_info(
        project_id=UUID(call.path["project_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_membership_request=ProjectMembershipRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def project_member_remove_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_project_member_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        principal_id=UUID(call.path["principal_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def project_member_remove_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_project_member_with_http_info(
        project_id=UUID(call.path["project_id"]),
        principal_id=UUID(call.path["principal_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def project_members_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_project_members_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def project_members_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_project_members_with_http_info(
        project_id=UUID(call.path["project_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def project_action_grants_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_project_action_grants_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def project_action_grants_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_project_action_grants_with_http_info(
        project_id=UUID(call.path["project_id"]),
        action_id=string(call.query["actionId"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def metadata_read_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_project_metadata_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def metadata_read_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_project_metadata_with_http_info(
        project_id=UUID(call.path["project_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def metadata_resolve_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).resolve_project_name_sync_with_http_info(
        name=call.path["name"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def metadata_resolve_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).resolve_project_name_with_http_info(
        name=call.path["name"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def metadata_change_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).update_project_metadata_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_metadata_update_request=ProjectMetadataUpdateRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def metadata_change_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).update_project_metadata_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_metadata_update_request=ProjectMetadataUpdateRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def lookup_sync(clients: Clients, call: Call) -> NativeResponse:
    return OperationsApi(clients.production).lookup_original_operation_sync_with_http_info(
        original_operation_lookup_request=OriginalOperationLookupRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def lookup_async(clients: Clients, call: Call) -> NativeResponse:
    return await OperationsApi(clients.production).lookup_original_operation_with_http_info(
        original_operation_lookup_request=OriginalOperationLookupRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def deletion_status_sync(clients: Clients, call: Call) -> NativeResponse:
    return OperationsApi(clients.production).get_deletion_status_sync_with_http_info(
        operation_id=string(call.query["operationId"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def deletion_status_async(clients: Clients, call: Call) -> NativeResponse:
    return await OperationsApi(clients.production).get_deletion_status_with_http_info(
        operation_id=string(call.query["operationId"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def payload_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_payload_sync_with_http_info(
        contract_fixture_payload=payload_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def payload_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_payload_with_http_info(
        contract_fixture_payload=payload_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def page_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_page_sync_with_http_info(
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def page_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_page_with_http_info(
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def upload_sync(clients: Clients, call: Call) -> NativeResponse:
    source = call.body
    if source is None:
        raise ValueError("Upload requires a body")
    return DefaultApi(clients.fixtures).contract_fixture_upload_sync_with_http_info(
        file=(
            string(source["fileName"]),
            base64.b64decode(string(source["fileBase64"]), validate=True),
        ),
        label=string(source["label"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def upload_async(clients: Clients, call: Call) -> NativeResponse:
    source = call.body
    if source is None:
        raise ValueError("Upload requires a body")
    return await DefaultApi(clients.fixtures).contract_fixture_upload_with_http_info(
        file=(
            string(source["fileName"]),
            base64.b64decode(string(source["fileBase64"]), validate=True),
        ),
        label=string(source["label"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def nullable_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_nullable_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def nullable_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_nullable_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def empty_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_empty_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def empty_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_empty_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


@dataclass(frozen=True)
class Binding:
    sync: Callable[[Clients, Call], NativeResponse]
    asynchronous: Callable[[Clients, Call], Awaitable[NativeResponse]]
    has_body: bool = True


def variants_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_variants_sync_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def variants_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_variants_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def media_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_media_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def media_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_media_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def fallback_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_fallback_sync_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def fallback_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_fallback_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def create_access_group_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).create_access_group_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_creation_request=AccessGroupCreationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def create_access_group_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).create_access_group_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_creation_request=AccessGroupCreationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def get_access_group_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_access_group_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def get_access_group_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_access_group_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def resolve_access_group_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).resolve_access_group_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        name=string(call.query["name"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def resolve_access_group_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).resolve_access_group_with_http_info(
        project_id=UUID(call.path["project_id"]),
        name=string(call.query["name"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def list_access_group_members_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_access_group_members_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_access_group_members_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_access_group_members_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def list_access_group_managers_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).list_access_group_managers_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def list_access_group_managers_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).list_access_group_managers_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def add_access_group_member_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).add_access_group_member_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_membership_request=AccessGroupMembershipRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def add_access_group_member_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).add_access_group_member_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_membership_request=AccessGroupMembershipRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_access_group_member_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_access_group_member_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_access_group_member_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_access_group_member_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def appoint_access_group_manager_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).appoint_access_group_manager_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_manager_request=AccessGroupManagerRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def appoint_access_group_manager_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).appoint_access_group_manager_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        access_group_manager_request=AccessGroupManagerRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def remove_access_group_manager_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).remove_access_group_manager_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def remove_access_group_manager_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).remove_access_group_manager_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        principal_id=UUID(call.path["principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def delete_project_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).delete_project_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def delete_project_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).delete_project_with_http_info(
        project_id=UUID(call.path["project_id"]),
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        idempotency_key=call.headers["Idempotency-Key"],
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def delete_access_group_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).delete_access_group_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def delete_access_group_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).delete_access_group_with_http_info(
        project_id=UUID(call.path["project_id"]),
        access_group_id=UUID(call.path["access_group_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        expected_access_revision=integer(call.query["expectedAccessRevision"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def revoke_application_key_sync(clients: Clients, call: Call) -> NativeResponse:
    body = ApplicationKeyRevocationRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Application-key revocation requires a body")
    return AccessApi(clients.production).revoke_application_key_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        key_id=UUID(call.path["key_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_key_revocation_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def revoke_application_key_async(clients: Clients, call: Call) -> NativeResponse:
    body = ApplicationKeyRevocationRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Application-key revocation requires a body")
    return await AccessApi(clients.production).revoke_application_key_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        key_id=UUID(call.path["key_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_key_revocation_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def issue_application_key_sync(clients: Clients, call: Call) -> NativeResponse:
    body = ApplicationKeyIssueRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Application-key issuance requires a body")
    return AccessApi(clients.production).issue_application_key_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_key_issue_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def issue_application_key_async(clients: Clients, call: Call) -> NativeResponse:
    body = ApplicationKeyIssueRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Application-key issuance requires a body")
    return await AccessApi(clients.production).issue_application_key_with_http_info(
        project_id=UUID(call.path["project_id"]),
        application_principal_id=UUID(call.path["application_principal_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        application_key_issue_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def issue_invitation_sync(clients: Clients, call: Call) -> NativeResponse:
    body = InvitationIssueRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Invitation issuance requires a body")
    return AccessApi(clients.production).issue_invitation_sync_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_issue_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def issue_invitation_async(clients: Clients, call: Call) -> NativeResponse:
    body = InvitationIssueRequest.from_dict(call.body)
    if body is None:
        raise ValueError("Invitation issuance requires a body")
    return await AccessApi(clients.production).issue_invitation_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_issue_request=body,
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def revoke_invitation_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).revoke_invitation_sync_with_http_info(
        invitation_id=UUID(call.path["invitation_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_revocation_request=InvitationRevocationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def revoke_invitation_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).revoke_invitation_with_http_info(
        invitation_id=UUID(call.path["invitation_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_revocation_request=InvitationRevocationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def preview_invitation_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).preview_invitation_sync_with_http_info(
        invitation_preview_request=InvitationPreviewRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def preview_invitation_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).preview_invitation_with_http_info(
        invitation_preview_request=InvitationPreviewRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def activate_invitation_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).activate_invitation_sync_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_activation_request=InvitationActivationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def activate_invitation_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).activate_invitation_with_http_info(
        idempotency_key=call.headers["Idempotency-Key"],
        invitation_activation_request=InvitationActivationRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def get_project_upload_defaults_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_project_upload_defaults_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def get_project_upload_defaults_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_project_upload_defaults_with_http_info(
        project_id=UUID(call.path["project_id"]),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


def set_project_upload_defaults_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).set_project_upload_defaults_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_upload_default_request=ProjectUploadDefaultRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


async def set_project_upload_defaults_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).set_project_upload_defaults_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_upload_default_request=ProjectUploadDefaultRequest.model_validate(call.body),
        _headers=call.headers,
        _request_timeout=call.timeout / 1000,
    )


BINDINGS: dict[Operation, Binding] = {
    Operation.GET_PROJECT_UPLOAD_DEFAULTS: Binding(
        get_project_upload_defaults_sync, get_project_upload_defaults_async
    ),
    Operation.SET_PROJECT_UPLOAD_DEFAULTS: Binding(
        set_project_upload_defaults_sync, set_project_upload_defaults_async
    ),
    Operation.REVOKE_APPLICATION_KEY: Binding(
        revoke_application_key_sync, revoke_application_key_async
    ),
    Operation.ISSUE_APPLICATION_KEY: Binding(
        issue_application_key_sync, issue_application_key_async
    ),
    Operation.ISSUE_INVITATION: Binding(issue_invitation_sync, issue_invitation_async),
    Operation.REVOKE_INVITATION: Binding(revoke_invitation_sync, revoke_invitation_async),
    Operation.PREVIEW_INVITATION: Binding(preview_invitation_sync, preview_invitation_async),
    Operation.ACTIVATE_INVITATION: Binding(activate_invitation_sync, activate_invitation_async),
    Operation.LIST_ORGANIZATION_ACTION_GRANTS: Binding(
        list_organization_action_grants_sync, list_organization_action_grants_async
    ),
    Operation.SET_ORGANIZATION_ACTION_GRANT: Binding(
        set_organization_action_grant_sync, set_organization_action_grant_async
    ),
    Operation.REMOVE_ORGANIZATION_ACTION_GRANT: Binding(
        remove_organization_action_grant_sync, remove_organization_action_grant_async
    ),
    Operation.LIST_ACCESS_GROUP_ACTION_GRANTS: Binding(
        list_access_group_action_grants_sync, list_access_group_action_grants_async
    ),
    Operation.SET_ACCESS_GROUP_ACTION_GRANT: Binding(
        set_access_group_action_grant_sync, set_access_group_action_grant_async
    ),
    Operation.REMOVE_ACCESS_GROUP_ACTION_GRANT: Binding(
        remove_access_group_action_grant_sync, remove_access_group_action_grant_async
    ),
    Operation.LIST_APPLICATION_ACCOUNT_ACTION_GRANTS: Binding(
        list_application_account_action_grants_sync, list_application_account_action_grants_async
    ),
    Operation.SET_APPLICATION_ACCOUNT_ACTION_GRANT: Binding(
        set_application_account_action_grant_sync, set_application_account_action_grant_async
    ),
    Operation.REMOVE_APPLICATION_ACCOUNT_ACTION_GRANT: Binding(
        remove_application_account_action_grant_sync, remove_application_account_action_grant_async
    ),
    Operation.LIST_PROJECT_GRANT_RECIPIENTS: Binding(
        project_grant_recipients_sync, project_grant_recipients_async
    ),
    Operation.CREATE_ACCESS_GROUP: Binding(create_access_group_sync, create_access_group_async),
    Operation.GET_ACCESS_GROUP: Binding(get_access_group_sync, get_access_group_async),
    Operation.RESOLVE_ACCESS_GROUP: Binding(resolve_access_group_sync, resolve_access_group_async),
    Operation.LIST_ACCESS_GROUP_MEMBERS: Binding(
        list_access_group_members_sync, list_access_group_members_async
    ),
    Operation.LIST_ACCESS_GROUP_MANAGERS: Binding(
        list_access_group_managers_sync, list_access_group_managers_async
    ),
    Operation.ADD_ACCESS_GROUP_MEMBER: Binding(
        add_access_group_member_sync, add_access_group_member_async
    ),
    Operation.REMOVE_ACCESS_GROUP_MEMBER: Binding(
        remove_access_group_member_sync, remove_access_group_member_async
    ),
    Operation.APPOINT_ACCESS_GROUP_MANAGER: Binding(
        appoint_access_group_manager_sync, appoint_access_group_manager_async
    ),
    Operation.REMOVE_ACCESS_GROUP_MANAGER: Binding(
        remove_access_group_manager_sync, remove_access_group_manager_async
    ),
    Operation.DELETE_PROJECT: Binding(delete_project_sync, delete_project_async),
    Operation.DELETE_ACCESS_GROUP: Binding(delete_access_group_sync, delete_access_group_async),
    Operation.CREATE_APPLICATION_ACCOUNT: Binding(
        create_application_account_sync, create_application_account_async
    ),
    Operation.DELETE_APPLICATION_ACCOUNT: Binding(
        delete_application_account_sync, delete_application_account_async
    ),
    Operation.GET_APPLICATION_ACCOUNT: Binding(
        get_application_account_sync, get_application_account_async
    ),
    Operation.RESOLVE_APPLICATION_ACCOUNT: Binding(
        resolve_application_account_sync, resolve_application_account_async
    ),
    Operation.LIST_APPLICATION_KEYS: Binding(
        list_application_keys_sync, list_application_keys_async
    ),
    Operation.GET_APPLICATION_KEY: Binding(get_application_key_sync, get_application_key_async),
    Operation.ADMIT_HUMAN: Binding(human_admission_sync, human_admission_async),
    Operation.GET_MY_ORGANIZATION_ACCESS: Binding(
        organization_access_sync, organization_access_async
    ),
    Operation.CREATE_PROJECT: Binding(create_project_sync, create_project_async),
    Operation.LIST_PROJECT_MEMBERS: Binding(project_members_sync, project_members_async),
    Operation.LIST_PROJECT_ACTION_GRANTS: Binding(
        project_action_grants_sync, project_action_grants_async
    ),
    Operation.GET_MY_PROJECT_ACCESS: Binding(my_project_access_sync, my_project_access_async),
    Operation.SET_PROJECT_ACTION_GRANT: Binding(
        set_project_action_grant_sync, set_project_action_grant_async
    ),
    Operation.REMOVE_PROJECT_ACTION_GRANT: Binding(
        remove_project_action_grant_sync, remove_project_action_grant_async
    ),
    Operation.ADD_PROJECT_MEMBER: Binding(project_member_add_sync, project_member_add_async),
    Operation.REMOVE_PROJECT_MEMBER: Binding(
        project_member_remove_sync, project_member_remove_async
    ),
    Operation.GET_PROTECTED_RESOURCE_METADATA: Binding(discovery_sync, discovery_async),
    Operation.GET_PROTECTED_RESOURCE_METADATA_FOR_PATH: Binding(
        discovery_path_sync, discovery_path_async
    ),
    Operation.CONTRACT_FIXTURE_VARIANTS: Binding(variants_sync, variants_async),
    Operation.CONTRACT_FIXTURE_FALLBACK: Binding(fallback_sync, fallback_async),
    Operation.CONTRACT_FIXTURE_MEDIA: Binding(media_sync, media_async),
    Operation.GET_HEALTH: Binding(health_sync, health_async),
    Operation.GET_CURRENT_SESSION: Binding(session_sync, session_async),
    Operation.GET_CURRENT_APPLICATION_SESSION: Binding(
        application_session_sync, application_session_async
    ),
    Operation.INSPECT_HUMAN_OAUTH_CONSENT: Binding(inspect_consent_sync, inspect_consent_async),
    Operation.DECIDE_HUMAN_OAUTH_CONSENT: Binding(decide_consent_sync, decide_consent_async),
    Operation.LOOKUP_ORIGINAL_OPERATION: Binding(lookup_sync, lookup_async),
    Operation.GET_DELETION_STATUS: Binding(deletion_status_sync, deletion_status_async),
    Operation.GET_PROJECT_METADATA: Binding(metadata_read_sync, metadata_read_async),
    Operation.RESOLVE_PROJECT_NAME: Binding(metadata_resolve_sync, metadata_resolve_async),
    Operation.UPDATE_PROJECT_METADATA: Binding(metadata_change_sync, metadata_change_async),
    Operation.CONTRACT_FIXTURE_PAYLOAD: Binding(payload_sync, payload_async),
    Operation.CONTRACT_FIXTURE_PAGE: Binding(page_sync, page_async),
    Operation.CONTRACT_FIXTURE_UPLOAD: Binding(upload_sync, upload_async),
    Operation.CONTRACT_FIXTURE_NULLABLE: Binding(nullable_sync, nullable_async),
    Operation.CONTRACT_FIXTURE_EMPTY: Binding(empty_sync, empty_async, has_body=False),
}
