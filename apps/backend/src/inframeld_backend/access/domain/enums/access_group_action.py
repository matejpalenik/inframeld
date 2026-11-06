from enum import StrEnum


class AccessGroupAction(StrEnum):
    """Identify the document actions that can be assigned on an access group."""

    ADD_DOCUMENTS = "add-documents"
    UPDATE_DOCUMENTS = "update-documents"
    DELETE_DOCUMENTS = "delete-documents"
