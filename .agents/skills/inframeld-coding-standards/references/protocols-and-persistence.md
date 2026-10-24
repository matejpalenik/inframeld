# Implement capabilities and typed persistence

Alice tests a workflow using a fake facts reader. The fake should implement the same declared capability as the PostgreSQL reader. Matching a method name by coincidence does not express that intent or prove that the workflow checks permissions before disclosure.

## Contents

- [Protocol implementations](#protocol-implementations)
- [Typed database access](#typed-database-access)
- [Worked example: add a capability and its test double](#worked-example-add-a-capability-and-its-test-double)
- [Worked example: map a typed row](#worked-example-map-a-typed-row)
- [Worked example: read a typed projection](#worked-example-read-a-typed-projection)
- [Exact raw-statement exception](#exact-raw-statement-exception)
- [Ownership and failure](#ownership-and-failure)
- [Sources](#sources)

## Protocol implementations

Every concrete class, adapter, fake or test double intended to implement a Python protocol explicitly names that protocol as a base. For example, `MockProjectActionFactsReader` explicitly inherits `ProjectActionFactsReader`. Implement every required member with a compatible signature.

Mark required protocol methods with `@abstractmethod`. Otherwise an IDE can treat a method as an inherited default instead of identifying a missing implementation. Mark overridden members with `@override`, including test doubles. Preserve strict Pyright with `reportImplicitOverride` enabled.

Protocols normally define behavioral capabilities. The narrow field-interface exceptions are explained in [Values and records](values-and-records.md). Do not add empty marker interfaces or classification frameworks.

Put the shared behavioral contract on the protocol and its public methods. Implementations document additional useful details without repeating the contract. A type checker verifies signatures. Behavioral tests must verify meaningful ordering, such as authorization before protected disclosure or mutation.

For Access authorization families, read the [owning authorization workflow](../../inframeld-access-models/references/authorization.md). Shared type conformance cannot establish current permission, checked scope or replay eligibility.

## Typed database access

An object-relational mapper (ORM) maps Python records to database rows. Generated application and test database access uses SQLAlchemy typed ORM mappings and expression APIs. Never use raw SQL strings or `text()` queries for application record access.

Use `MappedAsDataclass` with keyword-only typed constructors. Exclude database-generated fields from initialization and preserve database defaults. Use Alembic operations for schema changes.

Read scalars, ORM records or typed tuples and immediately convert them to named domain/application results. Do not use string-keyed SQL result mappings. Shared technology-prefixed static mappers convert database values without I/O or authorization. Keep ORM and vendor types out of domain/application contracts.

## Worked example: add a capability and its test double

**Situation.** Authentication must ask whether a verified identity is blocked by recovery. Application code should not know how PostgreSQL stores that answer, and tests need to control it without opening sessions.

**Decision and placement.** Declare the behavior in Access application protocols. The shared contract explains trusted inputs, independent short sessions and failures, which a matching method signature cannot prove:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/protocols/identity_recovery_block_reader.py](../../../../apps/backend/src/inframeld_backend/access/application/protocols/identity_recovery_block_reader.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class IdentityRecoveryBlockReader(Protocol):
    """Read recovery blocks independently of local account admission."""

    @abstractmethod
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        """Return whether this installation has an unreleased block for the identity.

        Use the exact authority and subject supplied by a trusted verifier.
        A block remains active until explicitly released, including when both
        provider outcomes are confirmed. A local principal does not need to exist.

        Each call owns a short, independent read session and supports concurrent
        callers. Do not cache results, create accounts, or change cleanup state.
        Missing installation metadata and recognized database availability
        failures raise DependencyUnavailableError. Unexpected failures propagate.
        """
        ...
```

The existing test-support implementation explicitly inherits that capability and marks its method as an override:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/tests/support/mock_identity_recovery_block_reader.py](../../../../apps/backend/tests/support/mock_identity_recovery_block_reader.py). This is existing code for explanation, not replacement or insertion instructions.

```python
"""Supply recovery outcomes without opening database sessions."""

import asyncio
from typing import override

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_block_reader import (
    IdentityRecoveryBlockReader,
)


class MockIdentityRecoveryBlockReader(IdentityRecoveryBlockReader):
    """Control current block state, failures, and overdue reads in unit tests."""

    def __init__(self) -> None:
        self.result = False
        self.failure: Exception | None = None
        self.stall = False
        self.return_after_cancellation = False
        self.identities: list[VerifiedHumanIdentityDTO] = []

    @override
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        self.identities.append(identity)
        if self.failure is not None:
            raise self.failure

        if self.stall:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not self.return_after_cancellation:
                    raise

        return self.result
```

**Walkthrough.** `@abstractmethod` identifies behavior an implementation must supply. Explicit inheritance states which contract it implements, and `@override` plus strict Pyright catches incompatible changes. The fake records calls and allows scenario-specific results, failures and late responses. These controls exist to test product behavior, not to assert the class hierarchy.

**Failures and alternatives.** Type conformance does not establish that callers check blocks or current permission at the right time. Exercise that behavior. Keep capability contracts on protocols and adapter details on implementations. Do not introduce a protocol for a hypothetical component or an empty record label.

## Worked example: map a typed row

**Situation.** A persistence adapter needs membership data and its database-generated assignment time.

**Decision and placement.** Keep ORM records in infrastructure rows. The row inherits keyword-only typed construction from its base. The existing base class and complete row module are shown separately so that their relationship is visible:

**Inspected teaching excerpt:** the complete base class with its imports from [apps/backend/src/inframeld_backend/access/infrastructure/rows/access_persistence_base.py](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/access_persistence_base.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class AccessPersistenceBase(MappedAsDataclass, DeclarativeBase, kw_only=True, eq=False):
    """Base for Access database row mappings."""
```

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/infrastructure/rows/project_membership_row.py](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/project_membership_row.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import PRINCIPAL_KIND_TYPE


class ProjectMembershipRow(AccessPersistenceBase):
    """Map a principal's membership in a project."""

    __tablename__ = "project_memberships"

    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE, nullable=False)
    application_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
    )
```

**Walkthrough.** `Mapped[UUID]` keeps storage values as UUIDs. The infrastructure enum type performs real conversion for `PrincipalKind`. The adapter constructs application IDs at its boundary. `assigned_at` has `init=False` and a database default, so callers do not manufacture a timestamp required to belong to the database.

**Failure and limits.** An annotation alone does not validate an external UUID or migrate a database. Alembic owns schema changes, and these partial ORM read mappings are not a competing schema or autogeneration source. Preserve existing defaults and stored meanings. The [aggregate repository example](aggregates-and-repositories.md) explains transaction-bound persistence.

## Worked example: read a typed projection

**Situation.** A credential workflow needs one current projection. It does not need a mutable aggregate or a save method.

**Decision and placement.** The infrastructure reader executes a typed query and immediately passes its typed tuple to the shared mapper. This complete module uses an independent session because its specific capability requires one:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_human_credential_state_reader.py](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_human_credential_state_reader.py). This is existing code for explanation, not replacement or insertion instructions.

```python
import asyncio
from typing import override

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_credential_state_reader import (
    HumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


class PostgresHumanCredentialStateReader(HumanCredentialStateReader):
    """Read one committed projection in an independent session with a five-second deadline."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def read(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        try:
            async with asyncio.timeout(5.0), self._database.session() as session:
                result = await session.execute(HumanCredentialStateQueries.for_identity(identity))
                return PostgresHumanCredentialStateMapper.to_state(
                    identity, result.tuples().one_or_none()
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
```

**Walkthrough.** The query helper supplies typed expressions. `result.tuples().one_or_none()` carries a typed tuple rather than a string-keyed mapping. The [static persistence mapper](static-utilities-and-mappers.md#worked-example-share-stored-value-conversion) returns the named DTO. The five-second deadline belongs to this inspected reader, not a universal timeout for all adapters.

**Failure and alternatives.** Recognized timeout and database availability failures become `DependencyUnavailableError`. Missing installation metadata is also unavailable, not a default empty result. Unexpected failures propagate. A transaction-bound authorization reader instead uses its caller's session. Never generalize this independent-read lifetime to the membership repository or share its session across requests.

## Exact raw-statement exception

The only approved raw-statement exception is isolated test database provisioning in `apps/backend/tests/support/postgres.py`. Compose CREATE DATABASE/DROP DATABASE with `psycopg.sql.Identifier` and autocommit.

That exception permits no raw record queries, startup probes, advisory-lock strings or application SQL. Use inspection, typed expressions and Alembic operations for those. If another limitation prevents the typed approach, explain it and request a specific exception. Do not infer an exception from convenience.

## Ownership and failure

Persistence adapters perform their specific I/O and boundary conversions. Their session, transaction and repository lifetime come from the owning application workflow. A typed row does not authorize a read or permit an adapter to commit, cache authority or retry a failed transaction.

Use an application-owned port when application/domain independence from an external adapter requires it. Otherwise a concrete infrastructure type is sufficient. Do not introduce interfaces solely because a future service might exist.

## Sources

- [Application conventions](../../../../docs/development/application-structure.md#component-conventions), [typed authorization](../../../../docs/development/application-structure.md#typed-authorization) and [service ownership](../../inframeld-application-contracts/references/components-and-services.md).
- Inspected capability: [ProjectActionFactsReader](../../../../apps/backend/src/inframeld_backend/access/application/protocols/project_action_facts_reader.py). [ADR-0067](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) explains the Access family contracts.
