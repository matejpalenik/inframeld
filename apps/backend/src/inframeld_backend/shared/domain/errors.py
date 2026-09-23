"""Define business-neutral exception bases for deliberate domain rejections.

Feature-specific rules and exception classes stay in the owning domain. These
classes have no transport, persistence, logging, or request-context dependency.
"""

from typing import ClassVar


class DomainError(Exception):
    """Describe a deliberate rejection by a domain rule.

    This base does not imply any HTTP status or public response. The calling
    use case determines whether the rejection is an expected outcome for its
    caller or evidence of an internal inconsistency.

    Attributes:
        code: Stable diagnostic category. It is not an HTTP problem definition.
        message: Developer-authored explanation. It must not include secrets,
            source content, or untrusted input and is not automatically public.
    """

    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str) -> None:
        """Initialize the failure without logging or serializing it.

        Args:
            message: Controlled explanation for the domain caller. Transport
                adapters select public wording separately.
        """
        self.message = message
        super().__init__(message)


class InvalidStateTransitionError(DomainError):
    """Reject an action that the current domain state does not permit.

    The constructor and message rules are inherited from DomainError. A use
    case may translate a supported caller-initiated rejection into a conflict.
    Do not globally map this class to a client status: an invalid transition
    during internal reconstruction can indicate a defect instead.

    Define a more specific exception in the owning domain when the distinction
    matters to its callers. Do not use this class for empty query results,
    missing infrastructure, malformed HTTP bodies, or programming assertions.
    """

    code: ClassVar[str] = "invalid_state_transition"
