import asyncio
from collections.abc import AsyncGenerator, AsyncIterable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import override

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactReservationError
from inframeld_backend.shared.application.protocols.artifact_preparation_io import (
    ArtifactPreparationIO,
)
from inframeld_backend.shared.application.protocols.artifact_staging import ArtifactStaging
from inframeld_backend.shared.application.services.artifact_verification_service import (
    ArtifactVerificationService,
)
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore


class PrivateArtifactPreparation(ArtifactPreparationIO):
    """Own a separate PUT client inside the permanent local attempt lock."""

    def __init__(
        self, staging: ArtifactStaging, store_factory: Callable[[], S3ArtifactStore]
    ) -> None:
        self._staging, self._store_factory = staging, store_factory
        self._store: S3ArtifactStore | None = None
        self._handles = AsyncExitStack()

    @override
    @asynccontextmanager
    async def hold(self, allocation: ArtifactAllocationDTO) -> AsyncGenerator[None]:
        if self._store is not None:
            raise ArtifactReservationError("The private preparation resource is already active.")
        async with self._staging.hold(allocation.reservation.attempt_id):
            self._store = self._store_factory()
            errors: list[BaseException] = []
            try:
                yield
            except BaseException as error:
                errors.append(error)
            finally:
                # One close task retains native ownership despite cancellation of a waiter.
                closing = asyncio.create_task(self._store.close())
                interrupted = False
                while not closing.done():
                    try:
                        await asyncio.shield(closing)
                    except asyncio.CancelledError as error:
                        if not interrupted:
                            errors.append(error)
                            interrupted = True
                    except BaseException:
                        break
                try:
                    closing.result()
                except BaseException as error:
                    errors.append(error)
                try:
                    await self._handles.aclose()
                except BaseException as error:
                    errors.append(error)
                finally:
                    self._store = None
                    self._handles = AsyncExitStack()
            if len(errors) == 1:
                raise errors[0]
            if errors:
                raise BaseExceptionGroup(
                    "Artifact preparation and resource closure failed.", errors
                ) from None

    @override
    async def stage(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> ArtifactAttemptDTO:
        original = allocation.reservation
        return await self._staging.stage(
            original.reservation_id,
            artifact_id=original.artifact_id,
            attempt_id=original.attempt_id,
            scope=original.scope,
            chunks=chunks,
        )

    @override
    async def verify(self, attempt: ArtifactAttemptDTO, *, upload: bool) -> VerifiedArtifactDTO:
        store = self._store
        if store is None:
            raise ArtifactReservationError("Private preparation requires its owned lifetime.")
        if upload:
            content = await self._handles.enter_async_context(self._staging.open(attempt))
            await store.put(attempt, content)
        return await ArtifactVerificationService(store).verify(attempt)
