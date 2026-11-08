"""Strict records for the native driver's private JSON boundary, not HTTP models."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue


class Operation(StrEnum):
    """Identify a generated operation supported by the native driver."""

    GET_PROTECTED_RESOURCE_METADATA = "getProtectedResourceMetadata"
    GET_PROTECTED_RESOURCE_METADATA_FOR_PATH = "getProtectedResourceMetadataForPath"
    GET_HEALTH = "getHealth"
    GET_CURRENT_SESSION = "getCurrentSession"
    GET_CURRENT_APPLICATION_SESSION = "getCurrentApplicationSession"
    GET_MY_ORGANIZATION_ACCESS = "getMyOrganizationAccess"
    ADMIT_HUMAN = "admitHuman"
    ISSUE_INVITATION = "issueInvitation"
    REVOKE_INVITATION = "revokeInvitation"
    PREVIEW_INVITATION = "previewInvitation"
    ACTIVATE_INVITATION = "activateInvitation"
    CREATE_PROJECT = "createProject"
    CREATE_ACCESS_GROUP = "createAccessGroup"
    GET_ACCESS_GROUP = "getAccessGroup"
    RESOLVE_ACCESS_GROUP = "resolveAccessGroup"
    LIST_ACCESS_GROUP_MEMBERS = "listAccessGroupMembers"
    LIST_ACCESS_GROUP_MANAGERS = "listAccessGroupManagers"
    ADD_ACCESS_GROUP_MEMBER = "addAccessGroupMember"
    REMOVE_ACCESS_GROUP_MEMBER = "removeAccessGroupMember"
    APPOINT_ACCESS_GROUP_MANAGER = "appointAccessGroupManager"
    REMOVE_ACCESS_GROUP_MANAGER = "removeAccessGroupManager"
    DELETE_ACCESS_GROUP = "deleteAccessGroup"
    CREATE_APPLICATION_ACCOUNT = "createApplicationAccount"
    GET_APPLICATION_ACCOUNT = "getApplicationAccount"
    RESOLVE_APPLICATION_ACCOUNT = "resolveApplicationAccount"
    LIST_APPLICATION_KEYS = "listApplicationKeys"
    GET_APPLICATION_KEY = "getApplicationKey"
    ISSUE_APPLICATION_KEY = "issueApplicationKey"
    LIST_PROJECT_MEMBERS = "listProjectMembers"
    LIST_PROJECT_ACTION_GRANTS = "listProjectActionGrants"
    LIST_ORGANIZATION_ACTION_GRANTS = "listOrganizationActionGrants"
    SET_ORGANIZATION_ACTION_GRANT = "setOrganizationActionGrant"
    REMOVE_ORGANIZATION_ACTION_GRANT = "removeOrganizationActionGrant"
    LIST_ACCESS_GROUP_ACTION_GRANTS = "listAccessGroupActionGrants"
    SET_ACCESS_GROUP_ACTION_GRANT = "setAccessGroupActionGrant"
    REMOVE_ACCESS_GROUP_ACTION_GRANT = "removeAccessGroupActionGrant"
    LIST_APPLICATION_ACCOUNT_ACTION_GRANTS = "listApplicationAccountActionGrants"
    SET_APPLICATION_ACCOUNT_ACTION_GRANT = "setApplicationAccountActionGrant"
    REMOVE_APPLICATION_ACCOUNT_ACTION_GRANT = "removeApplicationAccountActionGrant"
    LIST_PROJECT_GRANT_RECIPIENTS = "listProjectGrantRecipients"
    GET_MY_PROJECT_ACCESS = "getMyProjectAccess"
    SET_PROJECT_ACTION_GRANT = "setProjectActionGrant"
    REMOVE_PROJECT_ACTION_GRANT = "removeProjectActionGrant"
    ADD_PROJECT_MEMBER = "addProjectMember"
    REMOVE_PROJECT_MEMBER = "removeProjectMember"
    INSPECT_HUMAN_OAUTH_CONSENT = "inspectHumanOAuthConsent"
    DECIDE_HUMAN_OAUTH_CONSENT = "decideHumanOAuthConsent"
    LOOKUP_ORIGINAL_OPERATION = "lookupOriginalOperation"
    GET_DELETION_STATUS = "getDeletionStatus"
    RESOLVE_PROJECT_NAME = "resolveProjectName"
    GET_PROJECT_METADATA = "getProjectMetadata"
    UPDATE_PROJECT_METADATA = "updateProjectMetadata"
    CONTRACT_FIXTURE_PAYLOAD = "contractFixturePayload"
    CONTRACT_FIXTURE_PAGE = "contractFixturePage"
    CONTRACT_FIXTURE_UPLOAD = "contractFixtureUpload"
    CONTRACT_FIXTURE_NULLABLE = "contractFixtureNullable"
    CONTRACT_FIXTURE_EMPTY = "contractFixtureEmpty"
    CONTRACT_FIXTURE_VARIANTS = "contractFixtureVariants"
    CONTRACT_FIXTURE_MEDIA = "contractFixtureMedia"
    CONTRACT_FIXTURE_FALLBACK = "contractFixtureFallback"


class Profile(StrEnum):
    """Select the synchronous or asynchronous generated Python API."""

    PYTHON_SYNC = "python-sync"
    PYTHON_ASYNC = "python-async"


class Validation(StrEnum):
    """State which native decoder or validator established the returned value."""

    GENERATED_MODEL = "generated-model"
    GENERATED_SCHEMA = "generated-schema"
    PARSED_JSON = "parsed-json"
    NONE = "none"


class WireEncoding(StrEnum):
    """Describe how captured bytes are represented in the driver document."""

    UTF8 = "utf8"
    BASE64 = "base64"


class ObservationKind(StrEnum):
    """Separate a successful SDK call from an SDK-reported failure."""

    SUCCESS = "success"
    SDK_ERROR = "sdk-error"


class DriverEnvelopeKind(StrEnum):
    """Separate ordinary call observations from a defect in the driver itself."""

    OBSERVATIONS = "observations"
    DRIVER_ERROR = "driver-error"


class Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)


class Call(Record):
    id: str
    operation: Operation
    headers: dict[str, str]
    timeout: int = Field(gt=0)
    body: dict[str, JsonValue] | None = None
    query: dict[str, str | int] = Field(default_factory=dict)
    path: dict[str, str] = Field(default_factory=dict)
    unchecked_model: bool = Field(default=False, alias="uncheckedModel")


class DriverRequest(Record):
    version: Literal[2]
    profile: Profile
    case_id: str = Field(alias="caseId")
    base_url: HttpUrl = Field(alias="baseUrl")
    calls: list[Call] = Field(min_length=1)


class WireValue(Record):
    encoding: WireEncoding
    value: str


class Header(WireValue):
    name: str


class Observation(Record):
    kind: ObservationKind
    call_id: str = Field(alias="callId")
    validation: Validation
    headers: list[Header]
    status: int | None = None
    body: JsonValue = None
    raw: WireValue | None = None
    error: str | None = None
    cause: str | None = None


class Observations(Record):
    version: Literal[2] = 2
    profile: Profile
    case_id: str = Field(alias="caseId")
    kind: Literal[DriverEnvelopeKind.OBSERVATIONS] = DriverEnvelopeKind.OBSERVATIONS
    observations: list[Observation]


class DriverFailure(Record):
    version: Literal[2] = 2
    profile: Profile
    case_id: str = Field(alias="caseId")
    kind: Literal[DriverEnvelopeKind.DRIVER_ERROR] = DriverEnvelopeKind.DRIVER_ERROR
    error: str
