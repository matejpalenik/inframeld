import asyncio
import fcntl
import os
import stat
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactReservationError,
    ArtifactStagingBusyError,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId


class ArtifactAttemptOwnership:
    """Exclude cooperating filesystem users through one permanent attempt lock inode."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("Staging requires an absolute private root.")
        self._root = root
        self._task: asyncio.Task[object] | None = None
        self._attempt: ArtifactAttemptId | None = None

    async def startup(self) -> None:
        await self.run_io(self._initialize)

    @asynccontextmanager
    async def hold(self, attempt_id: ArtifactAttemptId) -> AsyncGenerator[None]:
        task = asyncio.current_task()
        if self._task is task and self._attempt == attempt_id:
            yield
            return
        if self._task is not None:
            raise ArtifactReservationError("The staging owner is already in use.")
        self._task, self._attempt = task, attempt_id
        try:
            descriptor = await self.run_io(lambda: self._acquire(attempt_id), on_cancel=os.close)
        except BaseException:
            self._task, self._attempt = None, None
            raise
        original: BaseException | None = None
        try:
            yield
        except BaseException as error:
            original = error
            raise
        finally:
            try:
                await self.run_io(lambda: os.close(descriptor))
            except BaseException as cleanup:
                if original is not None:
                    raise BaseExceptionGroup(
                        "Staging work and ownership closure failed.", [original, cleanup]
                    ) from None
                raise
            finally:
                self._task, self._attempt = None, None

    @staticmethod
    def require_directory(descriptor: int) -> None:
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_mode & 0o077
            or observed.st_uid != os.geteuid()
        ):
            raise ArtifactIntegrityError("The staging directory is not exclusively owned.")

    def _root_descriptor(self) -> int:
        try:
            descriptor = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            raise ArtifactIntegrityError("The existing staging root is unavailable.") from None
        try:
            self.require_directory(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def _initialize(self) -> None:
        root = self._root_descriptor()
        try:
            with suppress(FileExistsError):
                os.mkdir(".locks", 0o700, dir_fd=root)
            locks = os.open(".locks", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                self.require_directory(locks)
                os.fsync(locks)
                os.fsync(root)
            finally:
                os.close(locks)
        finally:
            os.close(root)

    def _acquire(self, attempt_id: ArtifactAttemptId) -> int:
        root = self._root_descriptor()
        descriptor: int | None = None
        try:
            locks = os.open(".locks", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                self.require_directory(locks)
                descriptor = os.open(
                    attempt_id.value.hex,
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=locks,
                )
                observed = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or observed.st_mode & 0o077
                    or observed.st_uid != os.geteuid()
                    or observed.st_nlink != 1
                ):
                    raise ArtifactIntegrityError(
                        "The permanent attempt lock changed ownership or type."
                    )
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise ArtifactStagingBusyError(
                        "An original local holder remains active."
                    ) from error
                os.fsync(locks)
                result, descriptor = descriptor, None
                return result
            finally:
                os.close(locks)
        except OSError:
            raise ArtifactIntegrityError("Exact local ownership cannot be confirmed.") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(root)

    @staticmethod
    async def run_io[T](
        action: Callable[[], T], *, on_cancel: Callable[[T], None] | None = None
    ) -> T:
        """Join the native holder and preserve interruption alongside native/closure failures."""
        task = asyncio.create_task(asyncio.to_thread(action))
        interrupted: asyncio.CancelledError | None = None
        while True:
            try:
                result = await asyncio.shield(task)
                break
            except asyncio.CancelledError as error:
                interrupted = interrupted or error
                if task.cancelled():
                    raise
            except BaseException as error:
                if interrupted is not None:
                    raise BaseExceptionGroup(
                        "Interrupted filesystem work failed.", [interrupted, error]
                    ) from None
                raise
        if interrupted is not None:
            if on_cancel is not None:
                try:
                    await ArtifactAttemptOwnership.run_io(lambda: on_cancel(result))
                except BaseException as error:
                    raise BaseExceptionGroup(
                        "Interrupted filesystem handle closure failed.", [interrupted, error]
                    ) from None
            raise interrupted
        return result
