"""
Some tests for the base loop and asyncio loop.

Testing the loop of GUI frameworks like Qt and wx is a bit tricky,
because importing more than one in the same process always causes problems.

Therefore, tests for these GUI framework need to be explicitly run:
* Run "pytest -k PySide6Loop"  etc.
* Run "python tests/test_loop.py WxLoop"  etc.

"""

# ruff: noqa: N803

import gc
import sys
import time
import signal
import asyncio
import threading

from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop
from rendercanvas import get_running_loop


from rendercanvas.utils.asyncs import sleep as async_sleep
from testutils import run_tests
import trio

import pytest


default_loop_classes = [RawLoop, AsyncioLoop, TrioLoop]
async_loop_classes = [AsyncioLoop, TrioLoop]
loop_classes = []


# Determine what loops to test
if "RawLoop" in sys.argv:
    loop_classes.append(RawLoop)
elif "AsyncioLoop" in sys.argv:
    loop_classes.append(AsyncioLoop)
elif "TrioLoop" in sys.argv:
    loop_classes.append(TrioLoop)
elif "QtLoop" in sys.argv:
    from rendercanvas.pyside6 import QtLoop

    loop_classes.append(QtLoop)
elif "PySide6Loop" in sys.argv:
    from rendercanvas.pyside6 import QtLoop

    class PySide6Loop(QtLoop):
        pass

    loop_classes.append(PySide6Loop)
elif "PyQt6Loop" in sys.argv:
    from rendercanvas.pyqt6 import QtLoop

    class PyQt6Loop(QtLoop):
        pass

    loop_classes.append(PyQt6Loop)
elif "PyQt5Loop" in sys.argv:
    from rendercanvas.pyqt5 import QtLoop

    class PyQt5Loop(QtLoop):
        pass

    loop_classes.append(PyQt5Loop)
elif "PySide2Loop" in sys.argv:
    from rendercanvas.pyside2 import QtLoop

    class PySide2Loop(QtLoop):
        pass

    loop_classes.append(PySide2Loop)
elif "WxLoop" in sys.argv:
    # NOTE: because for wx we have to do a few things differently, the
    # tests in this module do not pass for it. Also, installing wxPython
    # on CI tries to build wx from scratch, so we don't run wx tests
    # on CI anyway.
    from rendercanvas.wx import WxLoop

    loop_classes.append(WxLoop)
else:
    loop_classes[:] = default_loop_classes

    # When Pyside6 is installed, run the tests with a QtLoop.
    try:
        from rendercanvas.pyside6 import QtLoop
    except Exception:
        pass
    else:
        loop_classes.append(QtLoop)


async def fake_task():
    pass


class CanvasGroup(BaseCanvasGroup):
    pass


class FakeEventEmitter:
    is_closed = False

    def close(self):
        self.is_closed = True


class FakeCanvas:
    def __init__(self, refuse_close=False):
        self.refuse_close = refuse_close
        self.is_closed = False
        self._events = FakeEventEmitter()

    def _rc_gui_poll(self):
        pass

    def close(self):
        # Called by the loop to close a canvas
        self._events.close()  # Mimic BaseRenderCanvas
        if not self.refuse_close:
            self.is_closed = True

    def get_closed(self):
        return self.is_closed

    def manually_close(self):
        self.is_closed = True

    def __del__(self):
        # Mimic BaseRenderCanvas
        try:
            self.close()
        except Exception:
            pass


real_loop = AsyncioLoop()


class RealRenderCanvas(BaseRenderCanvas):
    _rc_canvas_group = CanvasGroup(real_loop)
    _is_closed = False

    def _rc_close(self):
        self._is_closed = True

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_request_draw(self):
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._draw_frame_and_present)


# %%%%% running and closing


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_close_bc_no_canvases(SomeLoop):
    # Run the loop without canvas; closes immediately

    loop = SomeLoop()
    loop.call_later(1.0, loop.stop)  # failsafe

    t0 = time.perf_counter()
    loop.run()
    t1 = time.perf_counter()

    assert (t1 - t0) < 0.2


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_detects_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    loop = SomeLoop()

    group1 = CanvasGroup(loop)
    group2 = CanvasGroup(loop)

    assert len(loop._BaseLoop__canvas_groups) == 0

    canvas1 = FakeCanvas()
    group1._register_canvas(canvas1, fake_task)

    assert len(loop._BaseLoop__canvas_groups) == 1
    assert len(loop.get_canvases()) == 1

    canvas2 = FakeCanvas()
    group1._register_canvas(canvas2, fake_task)

    canvas3 = FakeCanvas()
    group2._register_canvas(canvas3, fake_task)

    assert len(loop._BaseLoop__canvas_groups) == 2
    assert len(loop.get_canvases()) == 3

    # Call stop explicitly. Because we created some canvases, but never ran the
    # loops, they are in a 'ready' state, ready to move to the running state
    # when the loop-task starts running. For raw/asyncio/trio this is fine,
    # because cleanup will cancel all tasks. But for the QtLoop, the QTimer has
    # a reference to the callback, which refs asyncadapter.Task, which refs the
    # coroutine which refs the loop object. So there will not be any cleanup and
    # *this* loop will start running at the next test func.
    loop.stop()
    loop.stop()
    assert loop._BaseLoop__state == "off"


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_without_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    timeout = 0.15
    if "Qt" in SomeLoop.__name__ or "PySide" in SomeLoop.__name__:
        # Qt needs a bit more time
        timeout = 0.30

    loop = SomeLoop()
    group = CanvasGroup(loop)

    # The loop is in its stopped state, but it fires up briefly to do one tick

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < timeout

    # Create a canvas and close it right away

    canvas1 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    assert len(loop.get_canvases()) == 1
    canvas1.manually_close()
    assert len(loop.get_canvases()) == 0

    # This time the loop is in its ready state, so it will actually
    # run for one tick for it to notice that all canvases are gone.

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < timeout

    # Now its in its stopped state again

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < timeout


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_close_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    current_loops = []

    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas()
    canvas2 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    loop.call_later(
        0.1, lambda: current_loops.append(get_running_loop().__class__.__name__)
    )
    loop.call_later(0.1, canvas1.manually_close)
    loop.call_later(0.3, canvas2.manually_close)

    t0 = time.time()
    current_loops.append(get_running_loop().__class__.__name__)
    loop.run()
    current_loops.append(get_running_loop().__class__.__name__)
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.45

    assert canvas1._events.is_closed
    assert canvas2._events.is_closed

    assert current_loops == ["NoneType", SomeLoop.__name__, "NoneType"], current_loops


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_close_by_loop_stop(SomeLoop):
    # Close, then wait at most one tick to close canvases, and another to confirm close.
    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas()
    canvas2 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.3, loop.stop)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55

    assert canvas1._events.is_closed
    assert canvas2._events.is_closed


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_close_by_loop_stop_via_async(SomeLoop):
    # Close using a coro
    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas()
    canvas2 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    async def stopper():
        await async_sleep(0.3)
        loop.stop()

    loop.add_task(stopper)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55

    assert canvas1._events.is_closed
    assert canvas2._events.is_closed


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_close_by_deletion(SomeLoop):
    # Make the canvases be deleted by the gc.

    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvases = [FakeCanvas() for _ in range(2)]
    events1 = canvases[0]._events
    events2 = canvases[1]._events
    for canvas in canvases:
        group._register_canvas(canvas, fake_task)
        del canvas

    loop.call_later(0.3, canvases.clear)
    loop.call_later(1.3, loop.stop)  # failsafe
    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55

    assert events1.is_closed
    assert events2.is_closed


def test_run_loop_and_close_by_deletion_real():
    # Stop by deleting canvases, with a real canvas.
    # This tests that e.g. scheduler task does not hold onto the canvas.
    loop = real_loop

    canvases = [RealRenderCanvas() for _ in range(2)]

    loop.call_later(0.3, canvases.clear)
    loop.call_later(1.3, loop.stop)  # failsafe

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_interrupt(SomeLoop):
    # Interrupt, calls close, can take one tick to close canvases, and anoter to conform close.

    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas()
    canvas2 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    loop.call_later(0.1, print, "hi from loop!")

    def interrupt_soon():
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    t = threading.Thread(target=interrupt_soon)
    t.start()

    t0 = time.time()
    loop.run()
    et = time.time() - t0
    t.join()

    print(et)
    assert 0.25 < et < 0.55

    assert canvas1._events.is_closed
    assert canvas2._events.is_closed


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_run_loop_and_interrupt_harder(SomeLoop):
    # In the first tick it attempts to close the canvas, clearing some
    # stuff of the BaseRenderCanvase, like the events, but the native canvas
    # won't close, so in the second try, the loop is closed regardless.
    # after the second interupt, it stops the loop and closes the canvases

    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas(refuse_close=True)
    canvas2 = FakeCanvas(refuse_close=True)
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    loop.call_later(0.1, print, "hi from loop!")

    def interrupt_soon():
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    t = threading.Thread(target=interrupt_soon)
    t.start()

    t0 = time.time()
    loop.run()
    et = time.time() - t0
    t.join()

    print(et)
    assert 0.6 < et < 0.75

    # The events are closed
    assert canvas1._events.is_closed
    assert canvas2._events.is_closed

    # But the canvases themselves are still marked not-closed
    assert not canvas1.is_closed
    assert not canvas2.is_closed


# %%%%% lifetime


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_lifetime_normal(SomeLoop):
    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()
    log_state(loop)

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    loop.run()
    log_state(loop)

    assert states == ["off", "running", "off"]

    # Again

    states.clear()
    log_state(loop)

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    loop.run()
    log_state(loop)

    assert states == ["off", "running", "off"]


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_lifetime_with_ready(SomeLoop):
    # Creating a canvas, or addding a task puts the loop in its ready state

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    async def noop():
        pass

    loop = SomeLoop()
    log_state(loop)

    loop.add_task(noop)
    log_state(loop)

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    loop.run()
    log_state(loop)

    assert states == ["off", "ready", "running", "off"]

    # Again

    states.clear()
    log_state(loop)

    loop.add_task(noop)
    log_state(loop)

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    loop.run()
    log_state(loop)

    assert states == ["off", "ready", "running", "off"]


@pytest.mark.parametrize("SomeLoop", async_loop_classes)
def test_loop_lifetime_async(SomeLoop):
    # Run using loop.run_async

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = SomeLoop()
    log_state(loop)

    loop.call_later(0.01, log_state, loop)

    if SomeLoop is AsyncioLoop:
        asyncio.run(loop.run_async())
    elif SomeLoop is TrioLoop:
        trio.run(loop.run_async)
    else:
        raise NotImplementedError()

    log_state(loop)

    assert states == ["off", "active", "off"]


def test_loop_lifetime_running_outside():
    # Run using asyncio.run.
    # Note how the rendercanvas loop is stopped earlier than the asyncio loop.
    # Note that we use asyncio.run() here which has the logic to
    # clean up tasks. When using asyncio.new_event_loop().run_xx() then
    # it does *not* work, the user is expected to cancel tasks then.
    # Or ... just exit Python when done *shrug*.

    states = []
    log_state = lambda loop: states.append(loop._BaseLoop__state)

    loop = AsyncioLoop()
    log_state(loop)

    loop.call_later(0.01, log_state, loop)
    loop.call_later(0.1, loop.stop)

    async def main():
        lop = asyncio.get_running_loop()
        task = lop.create_task(loop.run_async())
        lop.call_later(0.15, log_state, loop)  # by this time rc has stopped
        await asyncio.sleep(0.25)
        del task  # for ruff and good practice, we kept a ref to task

    asyncio.run(main())

    log_state(loop)

    assert states == ["off", "active", "off", "off"]


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


# %%%%% tasks


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_loop_task_order(SomeLoop):
    # Test that added tasks are started in their original order,
    # and that the loop task always goes first.

    flag = []

    class MyLoop(SomeLoop):
        async def _loop_task(self):
            flag.append("loop-task")
            return await super()._loop_task()

    async def user_task(id):
        flag.append(f"user-task{id}")

    loop = MyLoop()

    loop.add_task(user_task, 1)
    loop.add_task(user_task, 2)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["loop-task", "user-task1", "user-task2"], flag

    # Again

    flag.clear()

    loop.add_task(user_task, 1)
    loop.add_task(user_task, 2)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["loop-task", "user-task1", "user-task2"], flag


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


# %%%%% Misc


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
    time.sleep(0.02)

    assert not thread.is_alive()


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop, TrioLoop])
def test_loop_threaded(SomeLoop):
    # Does not work for QtLoop

    error = None

    def wrapper():
        nonlocal error
        try:
            test_run_loop_and_close_by_loop_stop(SomeLoop)
        except Exception as err:
            error = err

    t = threading.Thread(target=wrapper)
    t.start()
    t.join()

    if error is not None:
        raise error


def test_async_loops_check_lib():
    # Cannot run asyncio loop on trio

    asyncio_loop = AsyncioLoop()
    group = CanvasGroup(asyncio_loop)
    canvas1 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    canvas1.manually_close()

    with pytest.raises(TypeError):
        trio.run(asyncio_loop.run_async)

    asyncio.run(asyncio_loop.run_async())

    # Cannot run trio loop on asyncio

    trio_loop = TrioLoop()
    group = CanvasGroup(trio_loop)
    canvas1 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    canvas1.manually_close()

    with pytest.raises(TypeError):
        asyncio.run(trio_loop.run_async())

    trio.run(trio_loop.run_async)


# %%%%% async generator cleanup


async def a_generator(flag, *, await_in_finalizer=False):
    flag.append("started")
    try:
        for i in range(4):
            await async_sleep(0.01)  # yield back to the loop
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
    loop.add_task(tester_coroutine)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == [], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup1(SomeLoop):
    # Run the generator to completion.
    # Just works, because code of generator is done.

    async def tester_coroutine():
        g = a_generator(flag)
        async for i in g:
            pass

    flag = []
    loop = SomeLoop()
    loop.add_task(tester_coroutine)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["started", "finished", "closed"], flag


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
    loop.add_task(tester_coroutine)
    loop.call_later(0.2, loop.stop)
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
    loop.add_task(tester_coroutine)
    loop.call_later(0.2, loop.stop)
    loop.run()

    assert flag == ["started", "except GeneratorExit", "closed"], flag


@pytest.mark.parametrize("SomeLoop", loop_classes)
def test_async_gens_cleanup_bad_agen(SomeLoop):
    # Same as last but not with a bad-behaving finalizer.

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
    loop.add_task(tester_coroutine)
    loop.call_later(0.2, loop.stop)
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
    # from rendercanvas.wx import WxLoop
    # loop_classes[:] = [WxLoop]
    run_tests(globals())
