class InvalidPdfUploadError(ValueError):
    """The owned input cannot be admitted as a PDF."""


class PdfUploadTooLargeError(InvalidPdfUploadError):
    """The application received more than the bounded PDF allowance."""
