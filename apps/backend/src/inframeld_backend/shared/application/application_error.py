"""Define the transport-neutral base for application operation failures."""

from typing import ClassVar


class ApplicationError(Exception):
    """Represent a deliberate application-layer operation failure.

    This exception is transport-neutral. Only explicitly supported concrete
    subclasses receive public HTTP, MCP, or worker mappings. The message is
    diagnostic and must not be exposed by default.

    Attributes:
        code: Stable semantic category used by diagnostics and mappings.
        message: Developer-authored diagnostic explanation.
    """

    code: ClassVar[str] = "application_error"

    def __init__(self, message: str) -> None:
        """Initialize an application failure without transport side effects.

        Args:
            message: Controlled diagnostic explanation. Public descriptions
                come from the transport adapter's reviewed problem definitions.
        """
        self.message = message
        super().__init__(message)
