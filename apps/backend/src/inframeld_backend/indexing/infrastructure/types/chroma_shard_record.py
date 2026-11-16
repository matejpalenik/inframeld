from dataclasses import dataclass, field
from math import isfinite
from struct import unpack
from typing import cast, override

CHROMA_BATCH_BYTE_LIMIT = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class ChromaShardRecord:
    """Retain the explicit little-endian float32 vector and scalar metadata for one ID."""

    record_id: str
    vector: bytes = field(repr=False)
    metadata: tuple[tuple[str, str | bool | int | float], ...] = field(repr=False)
    minimum_wire_bytes: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.record_id) is not str or not self.record_id:
            raise ValueError("A Chroma record requires an exact nonempty ID.")
        if (
            type(self.vector) is not bytes
            or len(self.vector) % 4
            or not 4 <= len(self.vector) <= 6144
        ):
            raise ValueError("A Chroma vector requires 1 to 1536 float32 values.")
        if not all(isfinite(value) for value in self.float_values()):
            raise ValueError("A Chroma vector requires finite float32 values.")

        if type(self.metadata) is not tuple:
            raise ValueError("Chroma metadata requires immutable entries.")

        # A metadata field requires key quotes, a colon and at least one value byte.
        minimum = len(self.record_id) + 4 * len(self.metadata)
        if minimum > CHROMA_BATCH_BYTE_LIMIT:
            raise ValueError("The Chroma record exceeds the batch byte limit.")
        for entry in self.metadata:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("Chroma metadata requires immutable key and value pairs.")
            key, value = entry
            if type(key) is not str or not key:
                raise ValueError("Chroma metadata requires nonempty keys.")
            if key.startswith(("chroma:", "#", "$")):
                raise ValueError("Chroma metadata keys must avoid reserved prefixes.")
            if (
                type(value) not in (str, bool, int, float)
                or (type(value) is int and not -(2**63) <= value < 2**63)
                or (type(value) is float and not isfinite(value))
            ):
                raise ValueError("Chroma metadata requires finite scalar values.")
            minimum += len(key) + (len(value) if type(value) is str else 0)
            if minimum > CHROMA_BATCH_BYTE_LIMIT:
                raise ValueError("The Chroma record exceeds the batch byte limit.")

        if len({key for key, _ in self.metadata}) != len(self.metadata):
            raise ValueError("Chroma metadata requires distinct keys.")
        object.__setattr__(
            self, "metadata", tuple(sorted(self.metadata, key=lambda entry: entry[0]))
        )
        object.__setattr__(self, "minimum_wire_bytes", minimum)

    def float_values(self) -> tuple[float, ...]:
        """Convert saved bytes to the explicit numbers required on the wire."""
        return cast(tuple[float, ...], unpack(f"<{len(self.vector) // 4}f", self.vector))

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChromaShardRecord):
            return NotImplemented
        if (
            self.record_id != other.record_id
            or self.vector != other.vector
            or len(self.metadata) != len(other.metadata)
        ):
            return False

        for (key, value), (other_key, other_value) in zip(
            self.metadata, other.metadata, strict=True
        ):
            if key != other_key or type(value) is not type(other_value):
                return False
            if type(value) is float and type(other_value) is float:
                if value.hex() != other_value.hex():
                    return False
            elif value != other_value:
                return False
        return True
