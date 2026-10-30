from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.admitted_work_facts_dto import AdmittedWorkFactsDTO
from inframeld_backend.access.application.protocols.admitted_work_facts_reader import (
    AdmittedWorkFactsReader,
)


class PostgresAdmittedWorkFactsReader(AdmittedWorkFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, authority: AdmittedWorkAuthorityDTO) -> AdmittedWorkFactsDTO | None:
        raise NotImplementedError
