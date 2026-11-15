import asyncio
import hashlib
import os
import stat
import time
from collections.abc import AsyncGenerator, AsyncIterable, Callable, Generator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from pathlib import Path
from typing import BinaryIO, override

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_staging import ArtifactStaging
from inframeld_backend.shared.application.protocols.artifact_staging_reservation_reader import (
    ArtifactStagingReservationReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.infrastructure.resources.artifact_attempt_ownership import (
    ArtifactAttemptOwnership,
)


class PrivateArtifactStaging(ArtifactStaging):
    """Keep reserved partial bytes private until their owner confirms cleanup.

    Paths use server identities and directory-relative no-follow operations.
    Disk calls and complete-file hashing run off-loop. Interruption drains the
    current native call before releasing its handles and never seals late bytes.
    The reservation's remaining authoritative allowance fixes one deadline.
    """

    def __init__(
        self, root: Path, staging_reservation_reader: ArtifactStagingReservationReader
    ) -> None:
        if not root.is_absolute():
            raise ValueError("Private staging requires an absolute operator-owned root.")
        self._root = root
        self._staging_reservation_reader = staging_reservation_reader
        self._attempt_ownership = ArtifactAttemptOwnership(root)

    async def startup(self) -> None:
        await self._attempt_ownership.startup()

    @override
    def hold(self, attempt_id: ArtifactAttemptId) -> AbstractAsyncContextManager[None]:
        return self._attempt_ownership.hold(attempt_id)

    @override
    async def stage(
        self,
        reservation_id: ArtifactStagingReservationId,
        *,
        artifact_id: ArtifactId,
        attempt_id: ArtifactAttemptId,
        scope: ArtifactScopeDTO,
        chunks: AsyncIterable[bytes],
    ) -> ArtifactAttemptDTO:
        async with self.hold(attempt_id):
            started = time.monotonic()
            facts = await self._staging_reservation_reader.read(reservation_id)
            if facts is None or (
                facts.reservation_id != reservation_id
                or facts.artifact_id != artifact_id
                or facts.attempt_id != attempt_id
                or facts.scope != scope
                or facts.released
                or facts.retired
                or type(facts.limit_bytes) is not int
                or not 0 < facts.limit_bytes <= 256 * 1024 * 1024
                or facts.expires_at.tzinfo is None
                or facts.observed_at.tzinfo is None
                or facts.expires_at <= facts.observed_at
            ):
                raise ArtifactReservationError(
                    "The original staging reservation is unavailable or changed."
                )
            remaining = (facts.expires_at - facts.observed_at).total_seconds()
            if remaining > 7200:
                raise ArtifactReservationError(
                    "The original transfer deadline exceeds its supported bound."
                )
            deadline = started + remaining
            self._require_deadline(deadline)
            digest = hashlib.sha256()
            length = 0
            transfer_timeout = asyncio.timeout(deadline - time.monotonic())
            try:
                async with transfer_timeout:
                    content = await self._run_io(
                        lambda: self._create_file(scope, attempt_id, deadline),
                        on_cancel=lambda opened: opened.close(),
                    )
                    original: BaseException | None = None
                    try:
                        async for chunk in chunks:
                            self._require_deadline(deadline)
                            if type(chunk) is not bytes:
                                raise ArtifactIntegrityError(
                                    "A staging stream must provide immutable bytes."
                                )
                            if len(chunk) > facts.limit_bytes - length:
                                raise ArtifactCapacityError(
                                    "The stream exceeds its reserved staging allowance."
                                )

                            def append(part: bytes = chunk) -> None:
                                self._require_deadline(deadline)
                                content.write(part)
                                digest.update(part)

                            await self._run_io(append)
                            length += len(chunk)
                        await self._run_io(lambda: self._seal_file(content, scope, deadline))
                    except BaseException as error:
                        original = error
                        raise
                    finally:
                        try:
                            await self._run_io(content.close)
                        except BaseException as cleanup:
                            if original is not None:
                                raise BaseExceptionGroup(
                                    "Staging stream and handle closure failed.", [original, cleanup]
                                ) from None
                            raise
            except TimeoutError:
                if not transfer_timeout.expired():
                    raise
                raise ArtifactReservationError(
                    "The original staging transfer deadline expired."
                ) from None
            self._require_deadline(deadline)
            return ArtifactAttemptDTO(
                artifact_id, attempt_id, scope, length, ArtifactContentDigest(digest.digest())
            )

    @override
    @asynccontextmanager
    async def open(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[BinaryIO]:
        async with self.hold(attempt.attempt_id):
            facts = await self._staging_reservation_reader.read_attempt(attempt.attempt_id)
            if (
                facts is None
                or facts.retired
                or facts.released
                or (facts.artifact_id, facts.scope, facts.length, facts.digest)
                != (attempt.artifact_id, attempt.scope, attempt.length, attempt.digest)
            ):
                raise ArtifactReservationError(
                    "The sealed local original is unavailable or retired."
                )
            content = await self._run_io(
                lambda: self._open_verified(attempt), on_cancel=lambda opened: opened.close()
            )
            original: BaseException | None = None
            try:
                yield content
            except BaseException as error:
                original = error
                raise
            finally:
                try:
                    await self._run_io(content.close)
                except BaseException as cleanup:
                    if original is not None:
                        raise BaseExceptionGroup(
                            "Artifact use and handle closure failed.", [original, cleanup]
                        ) from None
                    raise

    @override
    async def remove(self, target: ArtifactCleanupTargetDTO) -> None:
        async with self.hold(target.attempt_id):
            facts = await self._staging_reservation_reader.read_attempt(target.attempt_id)
            if (
                facts is None
                or not facts.retired
                or facts.published
                or (facts.artifact_id, facts.scope, facts.length, facts.digest)
                != (target.artifact_id, target.scope, target.length, target.digest)
            ):
                raise ArtifactReservationError(
                    "The exact retired local target cannot be confirmed."
                )
            await self._run_io(lambda: self._remove_file(target))

    def _create_file(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId, deadline: float
    ) -> BinaryIO:
        with self._directory(scope, create=True) as directory:
            assert directory is not None
            self._require_deadline(deadline)
            try:
                descriptor = os.open(
                    attempt_id.value.hex,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
            except FileExistsError:
                raise ArtifactIntegrityError(
                    "The original attempt already owns staging bytes."
                ) from None
            try:
                return os.fdopen(descriptor, "wb")
            except BaseException:
                os.close(descriptor)
                raise

    def _seal_file(self, content: BinaryIO, scope: ArtifactScopeDTO, deadline: float) -> None:
        self._require_deadline(deadline)
        content.flush()
        os.fsync(content.fileno())
        with self._directory(scope, create=False) as directory:
            if directory is None:
                raise ArtifactIntegrityError("The original staging directory is missing.")
            os.fsync(directory)
        self._require_deadline(deadline)

    def _open_verified(self, attempt: ArtifactAttemptDTO) -> BinaryIO:
        with self._directory(attempt.scope, create=False) as directory:
            if directory is None:
                raise ArtifactIntegrityError("The original staging bytes are missing.")
            try:
                descriptor = os.open(
                    attempt.attempt_id.value.hex, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
                )
            except FileNotFoundError:
                raise ArtifactIntegrityError("The original staging bytes are missing.") from None
            content = os.fdopen(descriptor, "rb")
            try:
                self._require_private_file(os.fstat(content.fileno()))
                digest = hashlib.sha256()
                length = 0
                while chunk := content.read(65536):
                    length += len(chunk)
                    if length > attempt.length:
                        raise ArtifactIntegrityError(
                            "Private staging exceeds its sealed expectation."
                        )
                    digest.update(chunk)
                if length != attempt.length or digest.digest() != attempt.digest.value:
                    raise ArtifactIntegrityError(
                        "Private staging differs from its sealed expectation."
                    )
                content.seek(0)
                return content
            except BaseException:
                content.close()
                raise

    def _remove_file(self, attempt: ArtifactCleanupTargetDTO) -> None:
        with self._directory(attempt.scope, create=False) as directory:
            if directory is None:
                return
            name = attempt.attempt_id.value.hex
            try:
                observed = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                os.fsync(directory)
                return
            self._require_private_file(observed)
            os.unlink(name, dir_fd=directory)
            os.fsync(directory)

    @staticmethod
    def _require_deadline(deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise ArtifactReservationError("The original staging transfer deadline expired.")

    @staticmethod
    async def _run_io[T](
        action: Callable[[], T], *, on_cancel: Callable[[T], None] | None = None
    ) -> T:
        return await ArtifactAttemptOwnership.run_io(action, on_cancel=on_cancel)

    @staticmethod
    def _require_private_file(observed: os.stat_result) -> None:
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_mode & 0o077
            or observed.st_uid != os.geteuid()
            or observed.st_nlink != 1
        ):
            raise ArtifactIntegrityError("Private staging ownership or file type has changed.")

    @contextmanager
    def _directory(self, scope: ArtifactScopeDTO, *, create: bool) -> Generator[int | None]:
        directory: int | None = None
        try:
            try:
                directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except FileNotFoundError:
                raise ArtifactIntegrityError("The existing staging root is unavailable.") from None
            for component in (
                scope.installation_id.value.hex,
                scope.organization_id.value.hex,
                scope.project_id.value.hex,
            ):
                self._require_private_directory(directory)
                if create:
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=directory)
                        os.fsync(directory)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(
                        component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                    )
                except FileNotFoundError:
                    os.fsync(directory)
                    yield None
                    return
                os.close(directory)
                directory = child
            self._require_private_directory(directory)
            yield directory
        except OSError:
            raise ArtifactIntegrityError(
                "Private staging could not confirm exact owned filesystem state."
            ) from None
        finally:
            if directory is not None:
                os.close(directory)

    @staticmethod
    def _require_private_directory(directory: int) -> None:
        observed = os.fstat(directory)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_mode & 0o077
            or observed.st_uid != os.geteuid()
        ):
            raise ArtifactIntegrityError("The private staging directory is not exclusively owned.")
