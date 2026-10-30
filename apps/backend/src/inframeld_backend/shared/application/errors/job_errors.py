from inframeld_backend.shared.application.errors.application_errors import ConflictError


class JobQueueFullError(ConflictError):
    pass


class UnsupportedJobPayloadError(ConflictError):
    pass


class JobFenceLostError(ConflictError):
    pass


class JobStoppedError(Exception):
    pass


class SafeJobRetryError(Exception):
    """The handler established that its unfinished work is safe to repeat."""
