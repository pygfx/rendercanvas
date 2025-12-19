"""
Test basics of rendercanvas.utils.asyncs.
"""

# ruff: noqa: N803

import os
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
    leeway = 0.20 if os.getenv("CI") else 0

    times = []

    async def coro():
        times.append(time.perf_counter())
        await asyncs.sleep(0.05)
        times.append(time.perf_counter())
        await asyncs.sleep(0.1)
        times.append(time.perf_counter())
        loop.stop()

    loop = SomeLoop()
    loop._stop_when_no_canvases = False
    loop.add_task(coro)
    loop.run()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.08 + leeway
    assert 0.09 < sleep_time2 < 0.13 + leeway


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_precise_sleep(SomeLoop):
    leeway = 0.20 if os.getenv("CI") else 0

    # This test uses the threaded timer on all os's
    prev_use_threaded_timer = asyncs.USE_THREADED_TIMER
    asyncs.USE_THREADED_TIMER = True

    try:
        times = []

        async def coro():
            times.append(time.perf_counter())
            await asyncs.precise_sleep(0.05)
            times.append(time.perf_counter())
            await asyncs.precise_sleep(0.1)
            times.append(time.perf_counter())
            loop.stop()

        loop = SomeLoop()
        loop._stop_when_no_canvases = False
        loop.add_task(coro)
        loop.run()

        sleep_time1 = times[1] - times[0]
        sleep_time2 = times[2] - times[1]
        assert 0.04 < sleep_time1 < 0.08 + leeway
        assert 0.09 < sleep_time2 < 0.13 + leeway

    finally:
        asyncs.USE_THREADED_TIMER = prev_use_threaded_timer


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_event(SomeLoop):
    leeway = 0.20 if os.getenv("CI") else 0

    event1 = None
    event2 = None

    times = []

    async def coro1():
        await asyncs.sleep(0.05)
        event1.set()
        await asyncs.sleep(0.1)
        event2.set()

    async def coro2():
        nonlocal event1, event2
        event1 = asyncs.Event()
        event2 = asyncs.Event()
        times.append(time.perf_counter())
        await event1.wait()
        times.append(time.perf_counter())
        await event2.wait()
        times.append(time.perf_counter())
        loop.stop()

    loop = SomeLoop()
    loop._stop_when_no_canvases = False
    loop.add_task(coro1)
    loop.add_task(coro2)
    loop.run()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.08 + leeway
    assert 0.09 < sleep_time2 < 0.13 + leeway


if __name__ == "__main__":
    run_tests(globals())
