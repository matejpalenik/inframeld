class ArtifactIntegrityError(RuntimeError):
    pass


class ArtifactCapacityError(RuntimeError):
    pass


class ArtifactReservationError(RuntimeError):
    pass


class ArtifactStagingBusyError(ArtifactReservationError):
    pass


class ArtifactStoreUnavailableError(RuntimeError):
    pass


class ArtifactWriteOutcomeUnknownError(RuntimeError):
    """Preserve the original attempt and obligation. An effect may have happened."""
