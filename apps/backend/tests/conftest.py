import os
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
test_env_file = backend_root / ".env.test"

if not test_env_file.is_file():
    raise RuntimeError(
        f"Missing test configuration file: {test_env_file}. "
        "Create apps/backend/.env.test before running tests."
    )

os.environ["INFRAMELD_ENVIRONMENT"] = "test"
os.environ["INFRAMELD_TEST_ENV_FILE"] = str(test_env_file)
