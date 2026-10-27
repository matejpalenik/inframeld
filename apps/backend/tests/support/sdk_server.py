"""Export native fixture OpenAPI or bind SDK conformance to ephemeral loopback."""

import argparse
import json
import socket
from pathlib import Path

import uvicorn

from tests.support.openapi_schema_fixture import create_schema_fixture_app
from tests.support.sdk_conformance_app import create_sdk_conformance_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "serve"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--browser-origin")
    arguments = parser.parse_args()
    output: Path = arguments.output

    if arguments.action == "export":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(create_schema_fixture_app().openapi(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return

    # Hold the socket across readiness publication and Uvicorn startup.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        output.write_text(f"http://127.0.0.1:{listener.getsockname()[1]}", encoding="utf-8")
        server = uvicorn.Server(
            uvicorn.Config(
                create_sdk_conformance_app(browser_origin=arguments.browser_origin),
                access_log=False,
                log_level="critical",
            )
        )
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
