import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.support.recovery_worker_process import recovery_worker_process


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt_exit", [False, True])
async def test_worker_is_reaped_even_when_exit_is_cancelled(
    monkeypatch: pytest.MonkeyPatch, interrupt_exit: bool
) -> None:
    process = MagicMock(spec=asyncio.subprocess.Process)
    process.returncode = None
    output = asyncio.StreamReader()
    output.feed_data(b'{"event":"recovery_worker_ready"}\n')
    process.stdout = output
    stopping = asyncio.Event()
    allow_exit = asyncio.Event()
    process.terminate.side_effect = stopping.set

    async def wait() -> int:
        await allow_exit.wait()
        process.returncode = 0
        output.feed_eof()
        return 0

    process.wait = AsyncMock(side_effect=wait)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))

    async def scenario() -> None:
        async with recovery_worker_process():
            pass

    task = asyncio.create_task(scenario())
    try:
        async with asyncio.timeout(5):
            await stopping.wait()
            if interrupt_exit:
                task.cancel()
            allow_exit.set()
            if interrupt_exit:
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
        assert process.returncode == 0
        process.wait.assert_awaited_once()
        process.terminate.assert_called_once()
        process.kill.assert_not_called()
    finally:
        allow_exit.set()
        output.feed_eof()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
