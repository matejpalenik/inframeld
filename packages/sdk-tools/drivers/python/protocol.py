"""Strict records for the native driver's private JSON boundary, not HTTP models."""

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue

Operation: TypeAlias = Literal[
    "getProtectedResourceMetadata",
    "getProtectedResourceMetadataForPath",
    "getHealth",
    "getCurrentSession",
    "inspectHumanOAuthConsent",
    "decideHumanOAuthConsent",
    "assignProjectUseOnlyGrant",
    "contractFixturePayload",
    "contractFixturePage",
    "contractFixtureUpload",
    "contractFixtureNullable",
    "contractFixtureEmpty",
    "contractFixtureVariants",
    "contractFixtureMedia",
    "contractFixtureFallback",
]
Profile: TypeAlias = Literal["python-sync", "python-async"]
Validation: TypeAlias = Literal["generated-model", "generated-schema", "parsed-json", "none"]


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
    encoding: Literal["utf8", "base64"]
    value: str


class Header(WireValue):
    name: str


class Observation(Record):
    kind: Literal["success", "sdk-error"]
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
    kind: Literal["observations"] = "observations"
    observations: list[Observation]


class DriverFailure(Record):
    version: Literal[2] = 2
    profile: Profile
    case_id: str = Field(alias="caseId")
    kind: Literal["driver-error"] = "driver-error"
    error: str
