# Exact grant target variants

Alice grants an action on Production. The target must name a Deployment, not an arbitrary string or a resource in another Project. A discriminator named kind selects the exact fields allowed for that target.

> **Status:** Accepted target variants, not an implemented generic grant API. The existing maintenance design schema owns its formal target shape.

## Exact alternatives

**Design notation, not production implementation.** This complete block describes the documented target alternatives in this reference. `UUID` represents a UUID value serialized as a JSON string. These types are not new application classes. The existing [maintenance schema target definition](../../../../contracts/design/access/maintenance-v1.schema.json#/$defs/target) provides the corresponding formal shape. The block is a teaching view of that definition, not another schema authority.

```python
from typing import Literal, TypedDict
from uuid import UUID


class OrganizationTarget(TypedDict):
    kind: Literal["organization"]
    organizationId: UUID

class ProjectTarget(TypedDict):
    kind: Literal["project"]
    projectId: UUID

class AccessGroupTarget(TypedDict):
    kind: Literal["access-group"]
    projectId: UUID
    accessGroupId: UUID

class ApplicationAccountTarget(TypedDict):
    kind: Literal["application-account"]
    projectId: UUID
    applicationPrincipalId: UUID

class PipelineTarget(TypedDict):
    kind: Literal["pipeline"]
    pipelineId: UUID

class DeploymentTarget(TypedDict):
    kind: Literal["deployment"]
    deploymentId: UUID

class CollectionTarget(TypedDict):
    kind: Literal["collection"]
    collectionId: UUID

class SourceTarget(TypedDict):
    kind: Literal["source"]
    sourceId: UUID

class ModelConnectionTarget(TypedDict):
    kind: Literal["model-connection"]
    modelConnectionId: UUID

class ProcessingProfileTarget(TypedDict):
    kind: Literal["processing-profile"]
    processingProfileId: UUID

class EmbeddingProfileTarget(TypedDict):
    kind: Literal["embedding-profile"]
    embeddingProfileId: UUID


type GrantTarget = (
    OrganizationTarget |
    ProjectTarget |
    AccessGroupTarget |
    ApplicationAccountTarget |
    PipelineTarget |
    DeploymentTarget |
    CollectionTarget |
    SourceTarget |
    ModelConnectionTarget |
    ProcessingProfileTarget |
    EmbeddingProfileTarget
)
```

## Structural and authority checks

Only the fields of the selected variant are allowed. An `organization` target has `organizationId`, not a Project field. An Access-group or application-account target carries both its Project and its own identity. Preserve valid UUID versions and zero values where existing ID contracts allow them. The generated-key UUIDv4 rule does not apply to all resource IDs.

For example, this identifies one Deployment. The value is illustrative, not a known resource:

```json
{
  "kind": "deployment",
  "deploymentId": "00000000-0000-0000-0000-000000000001"
}
```

Adding `projectId` to that variant is invalid. Supplying a valid UUID still proves neither that the resource exists nor that it belongs to the caller's Project.

The server loads authoritative target kind and parent scope, then checks supported action/target/recipient combinations against [the fixed catalogue](actions-and-initial-grants.md#capability-catalogue). A caller-supplied discriminator never selects arbitrary persistence or authorizes an operation.

## Use the right transport shape

Invitations and maintenance responsibilities contain a typed `target` object. [Target-specific grant routes](grant-contracts.md) instead retain their own path parameters and flat response fields. Do not replace those public/draft shapes with a new nested-target API. The recipient-directory query uses the separate bounded `targetKind`/`targetId` pair defined there.

## Sources and unresolved portions

- [Invitation contracts](invitation-contracts.md) and [maintenance input](host-maintenance.md#maintenance-wire) own their surrounding operations.
- [Identity and grant records](identity-and-grant-records.md) explain relationships. These closed transport alternatives do not create a generic resource registry or editable action language.
- Exact implementation and owning feature delivery remain separate from the accepted shape. No endpoint or migration is created by this reference.
