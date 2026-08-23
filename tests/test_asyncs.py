"""
Test basics of rendercanvas.utils.asyncs.
"""

# ruff: noqa: N803

import os
import sys
import time
import asyncio
import threading

from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop

from rendercanvas.utils import asyncs
from testutils import run_tests

import pytest


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
        FooCanvas.select_loop(loop)
        _canvas = FooCanvas()
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
    FooCanvas.select_loop(loop)
    _canvas = FooCanvas()
    loop.add_task(coro1)
    loop.add_task(coro2)
    loop.run()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.08 + leeway
    assert 0.09 < sleep_time2 < 0.13 + leeway


def test_sleep_when_another_loop_owns_the_asyncgen_hooks():
    # Regression test for issue #211.
    #
    # When a native loop is nested inside an async loop, the asyncgen hooks
    # belong to the outer loop, while our tasks are stepped by the inner one.
    # This is the case in IPython with '%gui qt': the Qt loop runs inside
    # asyncio's input-hook. Our sleep() must then still use the asyncadapter,
    # otherwise it awaits an asyncio future that the adapter cannot handle.

    leeway = 0.20 if os.getenv("CI") else 0

    # A (non-running) asyncio loop to steal the asyncgen hooks with
    asyncio_loop = asyncio.new_event_loop()

    libs = []
    funcs = []
    times = []

    async def coro():
        sys.set_asyncgen_hooks(
            firstiter=asyncio_loop._asyncgen_firstiter_hook,
            finalizer=asyncio_loop._asyncgen_finalizer_hook,
        )
        libs.append(asyncs.detect_current_async_lib())
        funcs.append(asyncs.detect_current_call_soon_threadsafe())
        times.append(time.perf_counter())
        await asyncs.sleep(0.05)
        times.append(time.perf_counter())
        loop.stop()

    loop = RawLoop()
    FooCanvas.select_loop(loop)
    _canvas = FooCanvas()
    loop.add_task(coro)

    # Failsafe: without the fix the coro never resumes, so we cannot use
    # loop.call_later() here (it relies on the very sleep that is broken then).
    failsafe = threading.Timer(2.0, loop.call_soon_threadsafe, [loop.stop])
    failsafe.start()

    prev_hooks = sys.get_asyncgen_hooks()
    try:
        loop.run()
    finally:
        failsafe.cancel()
        sys.set_asyncgen_hooks(*prev_hooks)
        asyncio_loop.close()

    # The adapter is stepping us, so it *is* the current async lib
    assert libs == ["rendercanvas.utils.asyncadapter"]
    assert funcs == [loop.call_soon_threadsafe]

    # And the sleep must actually have worked
    assert len(times) == 2
    assert 0.04 < times[1] - times[0] < 0.08 + leeway


if __name__ == "__main__":
    run_tests(globals())
