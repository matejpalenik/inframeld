from enum import StrEnum


class PipelineAction(StrEnum):
    """Identify exact Pipeline actions used by fixed creator assignments."""

    QUERY = "query"
    INSPECT_QUERY_TRACES = "inspect-query-traces"
    BUILD = "build-pipeline"
    VIEW_CONFIGURATION = "view-pipeline-configuration"
    EDIT_CONFIGURATION = "edit-pipeline-configuration"
    DELETE = "delete-pipeline"
    GENERATE_EVALUATION_CASES = "generate-evaluation-cases"
    VIEW_EVALUATION_CASES = "view-evaluation-cases"
    EDIT_EVALUATION_CASES = "edit-evaluation-cases"
    REVIEW_EVALUATION_CASES = "review-evaluation-cases"
    RUN_EVALUATION = "run-evaluation"
    INSPECT_EVALUATION_RESULTS = "inspect-evaluation-results"
    MANAGE_EVALUATION_CASE_AUDIENCES = "manage-evaluation-case-audiences"
