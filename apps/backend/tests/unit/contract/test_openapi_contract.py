import json
from pathlib import Path
from typing import Any, cast

from inframeld_backend.main import create_app

CONTRACT_PATH = (
    Path(__file__).resolve().parents[5] / "contracts" / "openapi" / "v1" / "inframeld-v1.json"
)


def test_openapi_contract_matches_application() -> None:
    assert CONTRACT_PATH.exists(), (
        "The OpenAPI contract is missing. Run `pnpm openapi` to generate it."
    )

    committed_contract = cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))

    generated_contract = create_app().openapi()

    assert committed_contract == generated_contract, (
        "The OpenAPI contract is stale. Run `pnpm openapi` to regenerate it."
    )
