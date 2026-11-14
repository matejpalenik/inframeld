from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator


class _ModelDecimalParser:
    @staticmethod
    def parse(value: object) -> Decimal:
        if not isinstance(value, str):
            raise ValueError("A model decimal requires an exact decimal string.")
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValueError("A model decimal requires an exact decimal string.") from None
        if not result.is_finite():
            raise ValueError("A model decimal string must be finite.")
        return result


type ModelDecimal = Annotated[
    Decimal,
    BeforeValidator(_ModelDecimalParser.parse, json_schema_input_type=str),
]
