import os
from uuid import uuid4

import pytest
from tests.support.artifact_scenarios import seed_artifact_scope

from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.releases.infrastructure.readers.postgres_deployment_association_reader import (
    PostgresDeploymentAssociationReader,
)
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_a_missing_pipeline_cannot_prove_deployment_absence(database: Database) -> None:
    scope = await seed_artifact_scope(database)

    async with database.session() as session, session.begin():
        reader = PostgresDeploymentAssociationReader(session)
        with pytest.raises(ResourceNotFoundError):
            await reader.require_absent(scope=scope, pipeline_id=PipelineId(uuid4()))
