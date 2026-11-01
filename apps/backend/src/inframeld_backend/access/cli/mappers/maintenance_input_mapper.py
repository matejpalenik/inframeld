import json

from pydantic import TypeAdapter

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate maintenance field.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("Invalid JSON constant.")


class MaintenanceInputMapper:
    """Decode one bounded strict JSON object without retaining proof material."""

    @staticmethod
    def read(payload: bytes) -> dict[str, object]:
        if len(payload) > 65_536:
            raise ValueError("Oversize maintenance request.")
        data: object = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        return TypeAdapter(dict[str, object]).validate_python(data, strict=True)

    @staticmethod
    def correlation(values: dict[str, object]) -> OperationId | None:
        value = values.get("operationId")
        if isinstance(value, str) and value.strip() and len(value) <= 128 and "\x00" not in value:
            try:
                value.encode("utf-8")
                return OperationId(value)
            except (ValueError, UnicodeError):
                return None
        return None
