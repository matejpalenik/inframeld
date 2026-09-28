"""Carry typed correlation metadata for an explicitly invoked application command."""

from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId


@dataclass(frozen=True, slots=True)
class CommandContextDTO:
    """Carry trusted request and operation identities into command diagnostics."""

    request_id: RequestId
    operation_id: OperationId
    command_name: str
