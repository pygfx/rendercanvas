"""
Test basics of rendercanvas.utils.asyncs.
"""

# ruff: noqa: N803

import time

from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop

from rendercanvas.utils import asyncs
from testutils import run_tests

import pytest


loop_classes = [RawLoop, AsyncioLoop, TrioLoop]


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_sleep(SomeLoop):
    times = []

    async def coro():
        times.append(time.perf_counter())
        await asyncs.sleep(0.05)
        times.append(time.perf_counter())

    loop = SomeLoop()
    loop.add_task(coro)
    loop.run()

    sleep_time1 = times[1] - times[0]
    assert 0.04 < sleep_time1 < 0.15


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_precise_sleep(SomeLoop):
    # This test uses the threaded timer on all os's
    prev_use_threaded_timer = asyncs.USE_THREADED_TIMER
    asyncs.USE_THREADED_TIMER = True

    try:
        times = []

        async def coro():
            times.append(time.perf_counter())
            await asyncs.precise_sleep(0.05)
            times.append(time.perf_counter())

        loop = SomeLoop()
        loop.add_task(coro)
        loop.run()

        sleep_time1 = times[1] - times[0]
        assert 0.04 < sleep_time1 < 0.15

    finally:
        asyncs.USE_THREADED_TIMER = prev_use_threaded_timer


def test_event(SomeLoop):
    event1 = asyncs.Event()

    times = []

    async def coro1():
        await asyncs.sleep(0.05)
        event1.set()

    async def coro2():
        times.append(time.perf_counter())
        await event1.wait()
        times.append(time.perf_counter())

    loop = SomeLoop()
    loop.add_task(coro1)
    loop.add_task(coro2)
    loop.run()

    sleep_time1 = times[1] - times[0]
    assert 0.04 < sleep_time1 < 0.15


if __name__ == "__main__":
    run_tests(globals())
