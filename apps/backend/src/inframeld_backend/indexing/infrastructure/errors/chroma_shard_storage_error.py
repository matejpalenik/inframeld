class ChromaShardStorageError(Exception):
    """A bounded storage failure with the original write's uncertainty."""

    def __init__(self, message: str, *, write_outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.write_outcome_unknown = write_outcome_unknown
