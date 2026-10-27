from typing import Protocol

from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectCommand(Protocol):
    """Require a project target on Commands that request project-scoped changes.

    Concrete Commands declare their own field. Static checking rejects an
    incomplete implementation when it is instantiated. This interface performs
    no runtime validation of project existence or permission. Its field does
    not express read-only access, although concrete Commands remain frozen.

    Attributes:
        project_id: Requested target, to be checked by authorization before use.
    """

    __slots__ = ()

    project_id: ProjectId
