from dataclasses import dataclass
from typing import NewType

RequestId = NewType("RequestId", str)
OperationId = NewType("OperationId", str)


@dataclass(frozen=True, slots=True)
class CommandContext:
    request_id: RequestId
    operation_id: OperationId
    command_name: str
