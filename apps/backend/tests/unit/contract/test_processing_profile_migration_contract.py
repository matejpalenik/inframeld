from alembic.config import Config
from alembic.script import ScriptDirectory

from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH


def test_processing_profiles_follow_the_provider_credentials_revision() -> None:
    revisions = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG_PATH)))
    profile_revision = revisions.get_revision("0037_processing_profiles")
    assert profile_revision is not None
    assert profile_revision.down_revision == "0036_provider_credentials"
