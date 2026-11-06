from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)


class AccessGroupRelationshipPolicy:
    @staticmethod
    def add_member(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(True, before.manager)

    @staticmethod
    def remove_member(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(False, False)

    @staticmethod
    def appoint_manager(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(True, True)

    @staticmethod
    def remove_manager(before: AccessGroupRelationships) -> AccessGroupRelationships:
        return AccessGroupRelationships(before.member, False)
