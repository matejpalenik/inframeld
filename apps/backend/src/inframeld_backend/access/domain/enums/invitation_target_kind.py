from enum import StrEnum


class InvitationTargetKind(StrEnum):
    """Identify closed retained intent without claiming that its receiving owner exists."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    ACCESS_GROUP = "access-group"
    APPLICATION_ACCOUNT = "application-account"
    PIPELINE = "pipeline"
    DEPLOYMENT = "deployment"
    COLLECTION = "collection"
    SOURCE = "source"
    MODEL_CONNECTION = "model-connection"
    PROCESSING_PROFILE = "processing-profile"
    EMBEDDING_PROFILE = "embedding-profile"
