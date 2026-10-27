"""Expose generated HTTPX results and keep driver defects visibly separate."""

import asyncio
import json
import sys

import httpx
import inframeld_sdk
import inframeld_sdk_fixtures
from inframeld_sdk.exceptions import ApiException
from inframeld_sdk.sync_helper import run_sync as production_sync
from inframeld_sdk_fixtures.exceptions import ApiException as FixtureApiException
from inframeld_sdk_fixtures.sync_helper import run_sync as fixture_sync
from observations import failure, success
from operations import BINDINGS, Clients
from protocol import DriverFailure, DriverRequest, Observation, Observations
from pydantic import ValidationError


async def execute(request: DriverRequest) -> Observations | DriverFailure:
    clients = Clients(
        inframeld_sdk.ApiClient(
            inframeld_sdk.Configuration(host=str(request.base_url).rstrip("/"))
        ),
        inframeld_sdk_fixtures.ApiClient(
            inframeld_sdk_fixtures.Configuration(host=str(request.base_url).rstrip("/"))
        ),
    )
    observations: list[Observation] = []
    failures: list[str] = []
    try:
        for call in request.calls:
            binding = BINDINGS[call.operation]
            try:
                response = (
                    binding.sync(clients, call)
                    if request.profile == "python-sync"
                    else await binding.asynchronous(clients, call)
                )
            except (ApiException, FixtureApiException) as error:
                # These attributes come from the native exception. Conversion below
                # is outside SDK exception handling so defects remain driver failures.
                observations.append(
                    failure(
                        call.id,
                        error,
                        status=error.status,
                        response_headers=error.headers,
                        data=error.data,
                        raw=error.raw_data if error.raw_data is not None else error.body,
                    )
                )
            except (httpx.HTTPError, ValidationError) as error:
                observations.append(failure(call.id, error))
            else:
                observations.append(success(call.id, response, binding.has_body))
    except Exception as error:
        failures.append(f"Execution: {type(error).__name__}: {error}")
    finally:
        # Attempt both owned clients, even if execution or the first close fails.
        for close in [clients.production.close, clients.fixtures.close]:
            try:
                if request.profile == "python-sync":
                    bridge = production_sync if close == clients.production.close else fixture_sync
                    await asyncio.wait_for(asyncio.to_thread(bridge, close()), timeout=5)
                else:
                    await asyncio.wait_for(close(), timeout=5)
            except Exception as error:
                failures.append(f"Cleanup: {type(error).__name__}: {error}")
    if failures:
        return DriverFailure(
            version=2,
            kind="driver-error",
            profile=request.profile,
            caseId=request.case_id,
            error="\n".join(failures),
        )
    return Observations(
        version=2,
        kind="observations",
        profile=request.profile,
        caseId=request.case_id,
        observations=observations,
    )


def main() -> None:
    if sys.argv[1:] == ["--bindings"]:
        print(json.dumps(list(BINDINGS)))
        return
    try:
        request = DriverRequest.model_validate_json(sys.stdin.buffer.read())
    except ValidationError as error:
        print(f"Invalid driver protocol: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    result = asyncio.run(execute(request))
    print(result.model_dump_json(by_alias=True, exclude_unset=True))


if __name__ == "__main__":
    main()
