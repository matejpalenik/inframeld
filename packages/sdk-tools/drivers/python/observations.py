"""Project available native SDK facts into JSON without judging conformance."""

import base64
from typing import Protocol, runtime_checkable

import httpx
from protocol import Header, Observation, WireValue
from pydantic import JsonValue, TypeAdapter

_JSON = TypeAdapter(JsonValue)


@runtime_checkable
class NativeModel(Protocol):
    def to_json(self) -> str: ...


class NativeResponse(Protocol):
    @property
    def status_code(self) -> int: ...
    @property
    def data(self) -> object: ...
    @property
    def headers(self) -> httpx.Headers | None: ...
    @property
    def raw_data(self) -> bytes: ...


def wire(value: str | bytes) -> WireValue:
    if isinstance(value, str):
        return WireValue(encoding="utf8", value=value)
    try:
        return WireValue(encoding="utf8", value=value.decode("utf-8"))
    except UnicodeDecodeError:
        return WireValue(encoding="base64", value=base64.b64encode(value).decode("ascii"))


def headers(value: httpx.Headers | None) -> list[Header]:
    if value is None:
        return []
    return [
        Header(
            name=name.decode("ascii"),
            encoding=(encoded := wire(content)).encoding,
            value=encoded.value,
        )
        for name, content in value.raw
    ]


def json_value(value: object) -> JsonValue:
    if isinstance(value, NativeModel):
        return _JSON.validate_json(value.to_json())
    return _JSON.validate_python(value)


def success(call_id: str, response: NativeResponse, has_body: bool) -> Observation:
    has_body = has_body and not (response.data is None and response.raw_data == b"")
    result = Observation(
        kind="success",
        callId=call_id,
        status=response.status_code,
        validation="generated-model" if has_body else "none",
        headers=headers(response.headers),
        raw=wire(response.raw_data),
    )
    if has_body:
        result.body = json_value(response.data)
    return result


def failure(
    call_id: str,
    error: Exception,
    *,
    status: int | None = None,
    response_headers: httpx.Headers | None = None,
    data: object = None,
    raw: str | bytes | None = None,
) -> Observation:
    result = Observation(
        kind="sdk-error",
        callId=call_id,
        validation="generated-model" if isinstance(data, NativeModel) else "none",
        headers=headers(response_headers),
        error=f"{type(error).__name__}: {error}",
    )
    if status is not None:
        result.status = status
    if data is not None:
        result.body = json_value(data)
    if raw is not None:
        result.raw = wire(raw)
    if error.__cause__ is not None:
        result.cause = str(error.__cause__)
    return result
