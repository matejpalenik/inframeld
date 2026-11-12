import asyncio
import os
from typing import override
from unittest.mock import patch

import pytest

from inframeld_backend.access.application.protocols.human_suspension_cleanup_executor import (
    HumanSuspensionCleanupExecutor,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_executor import (
    IdentityRecoveryCleanupExecutor,
)
from inframeld_backend.bootstrap.recovery_worker import execute_cleanup_pass, main


class CleanupExecutor(IdentityRecoveryCleanupExecutor, HumanSuspensionCleanupExecutor):
    def __init__(self, name: str, calls: list[str], *, advanced: bool) -> None:
        self.name = name
        self.calls = calls
        self.advanced = advanced

    @override
    async def execute_once(self) -> bool:
        self.calls.append(self.name)
        return self.advanced


@pytest.mark.asyncio
async def test_each_pass_tries_the_preferred_family_then_falls_back_only_when_idle() -> None:
    calls: list[str] = []
    stopped = asyncio.Event()
    routine = CleanupExecutor("routine", calls, advanced=True)
    suspension = CleanupExecutor("suspension", calls, advanced=True)

    assert await execute_cleanup_pass(routine, suspension, routine_first=True, stopped=stopped)
    assert await execute_cleanup_pass(routine, suspension, routine_first=False, stopped=stopped)
    suspension.advanced = False
    assert await execute_cleanup_pass(routine, suspension, routine_first=False, stopped=stopped)
    assert await execute_cleanup_pass(routine, None, routine_first=False, stopped=stopped)
    assert calls == ["routine", "suspension", "suspension", "routine", "routine"]

    stopped.set()
    assert not await execute_cleanup_pass(routine, suspension, routine_first=True, stopped=stopped)
    assert calls == ["routine", "suspension", "suspension", "routine", "routine"]


def test_invalid_worker_configuration_fails_before_io_without_disclosing_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No complete database or authority configuration is supplied.
    with patch.dict(os.environ, {"INFRAMELD_DATABASE__PASSWORD": "private-value"}, clear=True):
        assert main() == 2
    assert capsys.readouterr().out.strip() == '{"code":"invalid_configuration"}'
