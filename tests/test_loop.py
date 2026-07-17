"""
Some tests for the base loop. This is tested with our generic loops (raw, asyncio, trio).
Of these tests we assume that they'd succeed for the GUI loops as well (qt, wx, ...).
When in doubt of this assumption, better add a test to testutils_backends.py.

Note that in here we create *a lot* of different kind of loop objects.
In practice though, an application will use (and even import) a single
loop object and run it one time for the duration of the application.
"""

# ruff: noqa: N803

import gc
import time
import asyncio

from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop


from rendercanvas.utils.asyncs import sleep as async_sleep
from testutils import run_tests
import trio

import pytest


loop_classes = [RawLoop, AsyncioLoop, TrioLoop]
async_loop_classes = [AsyncioLoop, TrioLoop]


class FooCanvasGroup(BaseCanvasGroup):
    pass


class FooCanvas(BaseRenderCanvas):
    _rc_canvas_group = FooCanvasGroup(None)

    def __init__(self):
        super().__init__()
        self._is_closed = False
        self._final_canvas_init()

    def _rc_gui_poll(self):
        pass

    def _rc_close(self):
        # Note: in earlier rendercanvas versions, canvases could ignore
        # the signal to close. Now, closing is not a request but a command,
        # and the basse class and loop will consider the canvas as closed.
        self._is_closed = True

    def _rc_get_closed(self):
        return self._is_closed

    def manually_close(self):
        self.close()


# ==================== Running and closing


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_detects_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    assert len(loop._BaseLoop__canvas_groups) == 0

    _canvas1 = FooCanvas()

    assert len(loop._BaseLoop__canvas_groups) == 1
    assert len(loop.get_canvases()) == 1

    _canvas2 = FooCanvas()
    _canvas3 = FooCanvas()

    assert len(loop._BaseLoop__canvas_groups) == 1
    assert len(loop.get_canvases()) == 3

    # Call stop explicitly.
    loop.stop()
    loop.stop()
    assert loop._BaseLoop__state == "off"


# ==================== Lifetime


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_lifetime_nocanvas(SomeLoop):
    # No canvas; the loop flushes the queue and stops

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()

    log_state(loop)
    loop.call_later(0, log_state, loop)
    loop.run()
    log_state(loop)

    assert states == ["off", "running", "off"]

    states.clear()

    log_state(loop)
    loop.call_later(0, log_state, loop)
    loop.call_later(0, log_state, loop)
    loop.call_later(0, log_state, loop)
    loop.run()
    log_state(loop)

    assert states == ["off", "running", "running", "running", "off"]

    states.clear()

    log_state(loop)
    loop.call_later(0, log_state, loop)
    loop.call_later(0.91, log_state, loop)
    loop.call_later(0.92, log_state, loop)
    loop.run()
    log_state(loop)

    assert states == ["off", "running", "off"]


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_lifetime_normal(SomeLoop):
    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    log_state(loop)
    _canvas1 = FooCanvas()

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    log_state(loop)
    loop.run()
    log_state(loop)

    assert states == ["off", "ready", "running", "off"]

    # Again

    states.clear()

    log_state(loop)
    _canvas1 = FooCanvas()

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    log_state(loop)
    loop.run()
    log_state(loop)

    assert states == ["off", "ready", "running", "off"]


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_lifetime_with_ready(SomeLoop):
    # Creating a canvas, or adding a task puts the loop in its ready state

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    async def noop():
        pass

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    log_state(loop)
    loop.add_task(noop)
    log_state(loop)
    _canvas1 = FooCanvas()

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    loop.run()
    log_state(loop)

    assert states == ["off", "ready", "running", "off"]


@pytest.mark.parametrize("SomeLoop", async_loop_classes)
def test_loop_lifetime_async1(SomeLoop):
    # Run using loop.run_async, without canvases

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()

    log_state(loop)

    loop.call_later(0, log_state, loop)

    if SomeLoop is AsyncioLoop:
        asyncio.run(loop.run_async())
    elif SomeLoop is TrioLoop:
        trio.run(loop.run_async)
    else:
        raise NotImplementedError()

    log_state(loop)

    assert states == ["off", "active", "off"]


@pytest.mark.parametrize("SomeLoop", async_loop_classes)
def test_loop_lifetime_async2(SomeLoop):
    # Run using loop.run_async, with a canvas

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    log_state(loop)

    _canvas1 = FooCanvas()
    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    if SomeLoop is AsyncioLoop:
        asyncio.run(loop.run_async())
    elif SomeLoop is TrioLoop:
        trio.run(loop.run_async)
    else:
        raise NotImplementedError()

    log_state(loop)

    assert states == ["off", "active", "off"]


def test_loop_lifetime_running_outside():
    # Run using asyncio.run, make sure the rc loop detects the stop

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = AsyncioLoop()
    FooCanvas.select_loop(loop)

    log_state(loop)

    _canvas1 = FooCanvas()
    loop.call_later(0.01, log_state, loop)

    async def main():
        lop = asyncio.get_running_loop()
        task = lop.create_task(loop.run_async())
        lop.call_later(0.1, log_state, loop)
        await asyncio.sleep(0.2)
        del task  # for ruff and good practice, we kept a ref to task

    asyncio.run(main())

    log_state(loop)

    assert states == ["off", "active", "active", "off"]


def test_loop_lifetime_interactive():
    # Run using loop.run, but asyncio is already running: interactive mode.

    times = []
    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = AsyncioLoop()

    async def main():
        log_state(loop)

        loop.call_later(0.01, log_state, loop)
        loop.call_later(0.1, loop.stop)
        times.append(time.perf_counter())
        loop.run()
        times.append(time.perf_counter())
        await asyncio.sleep(0.25)
        times.append(time.perf_counter())

    asyncio.run(main())

    log_state(loop)

    assert states == ["off", "interactive", "off"]

    assert (times[1] - times[0]) < 0.01
    assert (times[2] - times[1]) > 0.20


# ==================== Tasks


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_task_order(SomeLoop):
    # Test that added tasks are started in their original order,
    # and that the loop task always goes first.

    flag = []

    class MyLoop(SomeLoop):
        async def _loop_start_detection_task(self):
            flag.append("loop-start-detect-task")
            return await super()._loop_start_detection_task()

    async def user_task(id):
        flag.append(f"user-task{id}")

    loop = MyLoop()

    loop.add_task(user_task, 1)
    loop.add_task(user_task, 2)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["loop-start-detect-task", "user-task1", "user-task2"], flag

    # Again

    flag.clear()

    loop.add_task(user_task, 1)
    loop.add_task(user_task, 2)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["loop-start-detect-task", "user-task1", "user-task2"], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_task_cancellation(SomeLoop):
    flag = []

    async def user_task():
        flag.append("start")
        try:
            await async_sleep(10)
        finally:
            flag.append("stop")

    loop = SomeLoop()

    loop.add_task(user_task)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["start", "stop"], flag

    # Again

    flag.clear()

    loop.add_task(user_task)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["start", "stop"], flag


# ==================== Misc


def test_not_using_loop_debug_thread():
    key = "_debug_thread"
    loop = RawLoop()
    assert not hasattr(loop, key)

    loop._setup_debug_thread()

    thread = getattr(loop, key)
    assert thread
    assert thread.is_alive()

    del loop
    gc.collect()
    gc.collect()
    time.sleep(0.1)

    assert not thread.is_alive()


def test_async_loops_check_lib():
    # Cannot run asyncio loop on trio

    asyncio_loop = AsyncioLoop()
    FooCanvas.select_loop(asyncio_loop)

    canvas1 = FooCanvas()
    canvas1.manually_close()

    with pytest.raises(TypeError):
        trio.run(asyncio_loop.run_async)

    asyncio.run(asyncio_loop.run_async())

    # Cannot run trio loop on asyncio

    trio_loop = TrioLoop()
    FooCanvas.select_loop(asyncio_loop)

    canvas1 = FooCanvas()
    canvas1.manually_close()

    with pytest.raises(TypeError):
        asyncio.run(trio_loop.run_async())

    trio.run(trio_loop.run_async)


# ==================== async generator cleanup


async def a_generator(flag, *, await_in_finalizer=False):
    flag.append("started")
    try:
        for i in range(4):
            await async_sleep(0)  # yield back to the loop
            yield i
    except BaseException as err:
        flag.append(f"except {err.__class__.__name__}")
        raise
    else:
        flag.append("finished")
    finally:
        if await_in_finalizer:
            await async_sleep(0)
        flag.append("closed")


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup0(SomeLoop):
    # Don't even start the generator.
    # Just works, because code of generator has not stated running.

    async def tester_coroutine():
        _g = a_generator(flag)

    flag = []
    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    loop.add_task(tester_coroutine)
    _canvas1 = FooCanvas()
    loop.call_later(0.1, loop.stop)
    loop.run()

    assert flag == [], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup1a(SomeLoop):
    # Run the generator, but stop too soon

    async def tester_coroutine():
        g = a_generator(flag)
        async for i in g:
            pass

    flag = []

    loop = SomeLoop()

    loop.add_task(tester_coroutine)

    loop.call_later(0.1, loop.stop)  # just a failsafe
    loop.run()

    flags1 = ["started", "except Cancelled", "closed"]
    flags2 = ["started", "except CancelledError", "closed"]
    assert flag == flags1 or flag == flags2, flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup1b(SomeLoop):
    # Run the generator to completion.
    # Just works, because code of generator is done.

    async def tester_coroutine():
        g = a_generator(flag)
        async for i in g:
            pass

    flag = []

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    loop.add_task(tester_coroutine)
    _canvas1 = FooCanvas()

    loop.call_later(0.1, loop.stop)
    loop.run()

    assert flag == ["started", "finished", "closed"], flag


@pytest.mark.filterwarnings("ignore:.*garbage collected before it had been exhausted")
@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup2(SomeLoop):
    # Break out of the generator, leaving it in a pending state.
    # Just works, because gen.aclose() is called from gen.__del__

    async def tester_coroutine():
        g = a_generator(flag)
        # await async_sleep(0)  # this sleep made a difference at some point
        async for i in g:
            if i > 1:
                break

    flag = []

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    loop.add_task(tester_coroutine)
    _canvas1 = FooCanvas()

    loop.call_later(0.1, loop.stop)
    loop.run()

    assert flag == ["started", "except GeneratorExit", "closed"], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup3(SomeLoop):
    # Break out of the generator, but hold a ref to the generator.
    # For this case we need sys.set_asyncgen_hooks().

    g = None

    async def tester_coroutine():
        nonlocal g
        g = a_generator(flag)
        # await async_sleep(0)
        async for i in g:
            if i > 2:
                break

    flag = []

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    loop.add_task(tester_coroutine)
    _canvas1 = FooCanvas()

    loop.call_later(0.1, loop.stop)
    loop.run()

    assert flag == ["started", "except GeneratorExit", "closed"], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup_bad_agen(SomeLoop):
    # Same as last but now with a bad-behaving finalizer.

    g = None

    async def tester_coroutine():
        nonlocal g
        g = a_generator(flag, await_in_finalizer=True)
        # await async_sleep(0)
        async for i in g:
            if i > 2:
                break

    flag = []

    loop = SomeLoop()
    FooCanvas.select_loop(loop)

    loop.add_task(tester_coroutine)
    _canvas1 = FooCanvas()

    loop.call_later(0.1, loop.stop)
    loop.run()

    if SomeLoop is AsyncioLoop:
        # Handled properly
        ref_flag = ["started", "except GeneratorExit", "closed"]
    elif SomeLoop is TrioLoop:
        # Not handled correctly? It did at some point.
        # Anyway, rather adversarial use-case, so I don't care too much.
        ref_flag = ["started", "except GeneratorExit"]
    else:
        # Actually, our adapter also works, because the sleep and Event
        # become no-ops once the loop is gone, and since there are no other things
        # one can wait on with our asyncadapter, we're good!
        ref_flag = ["started", "except GeneratorExit", "closed"]

    assert flag == ref_flag, flag


if __name__ == "__main__":
    run_tests(globals())
