"""
Test basics of rendercanvas.utils.asyncs.
"""

# ruff: noqa: N803

import asyncio
import os
import queue
import time

import pytest
from testutils import run_tests

from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.raw import RawLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.utils import asyncs

loop_classes = [RawLoop, AsyncioLoop, TrioLoop]


class FooCanvasGroup(BaseCanvasGroup):
    pass


class FooCanvas(BaseRenderCanvas):
    _rc_canvas_group = FooCanvasGroup(None)

    def __init__(self):
        super().__init__()
        self._final_canvas_init()


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
    FooCanvas.select_loop(loop)
    _canvas = FooCanvas()
    loop.add_task(coro)
    loop.run()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.08 + leeway
    assert 0.09 < sleep_time2 < 0.13 + leeway


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
    FooCanvas.select_loop(loop)
    _canvas = FooCanvas()
    loop.add_task(coro1)
    loop.add_task(coro2)
    loop.run()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.08 + leeway
    assert 0.09 < sleep_time2 < 0.13 + leeway


class PumpableRawLoop(RawLoop):
    """The raw loop, but with a manual pump.
    We use this to emulate IPython pumping Qt's loop.
    """

    def pump(self):
        try:
            callback = self._queue.get(False, None)
        except queue.Empty:
            return
        try:
            callback()
        except Exception as err:
            print(f"Error in RawLoop callback: {err}")


def test_with_pumped_loop_via_asyncio():
    # Regression test for https://github.com/pygfx/rendercanvas/issues/211

    # Create loop objects
    asyncio_loop = asyncio.new_event_loop()
    loop = PumpableRawLoop()

    result = []
    ref_result = ["rendercanvas.utils.asyncadapter", "done"]

    async def the_task():
        # The rc task that we will be running
        result.append(asyncs.detect_current_async_lib())
        await asyncs.sleep(0.1)
        result.append("done")

    def pump_the_loop1():
        # Pump the loop synchronously
        for i in range(20):
            time.sleep(0.01)
            loop.pump()

    async def pump_the_loop2():
        # Another function to pump the loop, but as an asyncio coro
        for i in range(20):
            await asyncio.sleep(0.01)
            loop.pump()

    # Synchronous pumping
    result.clear()
    loop.add_task(the_task)
    pump_the_loop1()
    assert result == ref_result, result

    # Synchronous pumping, again, to show we can repeat it
    result.clear()
    loop.add_task(the_task)
    pump_the_loop1()
    assert result == ref_result, result

    # Now pump it via asyncio
    result.clear()
    loop.add_task(the_task)
    asyncio_loop.run_until_complete(pump_the_loop2())
    assert result == ref_result, result


if __name__ == "__main__":
    run_tests(globals())
