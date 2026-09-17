import json
from pathlib import Path

from inframeld_backend.main import create_app

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1" / "inframeld-v1.json"
)


def export_openapi() -> None:
    """Generate the versioned OpenAPI contract from the FastAPI application."""

    contract = create_app().openapi()

    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)

    CONTRACT_PATH.write_text(
        json.dumps(
            contract,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Generated {CONTRACT_PATH}")


if __name__ == "__main__":
    export_openapi()
