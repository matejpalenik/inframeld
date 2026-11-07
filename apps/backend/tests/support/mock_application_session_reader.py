from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.protocols.application_session_reader import (
    ApplicationSessionReader,
)


class MockApplicationSessionReader(ApplicationSessionReader):
    def __init__(self, result: CurrentApplicationSessionDTO) -> None:
        self.result = result
        self.failure: Exception | None = None
        self.calls = 0

    @override
    async def read(self, *, access: AccessContextDTO) -> CurrentApplicationSessionDTO:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.result
