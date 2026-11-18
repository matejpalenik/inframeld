class PdfParseError(RuntimeError):
    """Report safe failure and whether this attempt's cleanup was established."""

    def __init__(self, message: str, *, cleanup_confirmed: bool = False) -> None:
        super().__init__(message)
        self.cleanup_confirmed = cleanup_confirmed
