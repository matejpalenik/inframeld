from dataclasses import dataclass

from inframeld_backend.shared.http.types.problem_code import ProblemCode


@dataclass(frozen=True, slots=True)
class ProblemDefinition:
    """Define one stable public problem representation."""

    type_uri: str
    code: ProblemCode
    title: str
    status: int
    detail: str
