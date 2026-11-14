from enum import StrEnum


class ModelConnectionAction(StrEnum):
    VIEW_CONFIGURATION = "view-model-connection-configuration"
    USE = "use-model-connection"
    MANAGE = "manage-model-connection"
    DELETE = "delete-model-connection"
