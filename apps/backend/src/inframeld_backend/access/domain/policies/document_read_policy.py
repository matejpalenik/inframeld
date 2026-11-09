from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class DocumentReadPolicy:
    """Evaluate a complete current audience, never an action or manager grant."""

    @staticmethod
    def may_read(
        *,
        requested_project_id: ProjectId,
        document_project_id: ProjectId,
        source_is_live: bool,
        document_is_live: bool,
        audience: frozenset[AccessGroupId],
        valid_group_ids: frozenset[AccessGroupId],
        member_group_ids: frozenset[AccessGroupId],
    ) -> bool:
        return (
            requested_project_id == document_project_id
            and source_is_live
            and document_is_live
            and bool(audience)
            and audience.issubset(valid_group_ids)
            and not audience.isdisjoint(member_group_ids)
        )
