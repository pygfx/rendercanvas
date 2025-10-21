"""
Some tests for the base loop and asyncio loop.
"""

# ruff: noqa: N803

import time
import signal
import asyncio
import threading

from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop
from rendercanvas.utils.asyncs import sleep as async_sleep
from testutils import run_tests
import trio

import pytest


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
        if not self.refuse_close:
            self.is_closed = True

    def get_closed(self):
        return self.is_closed

    def manually_close(self):
        self.is_closed = True


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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_run_loop_and_close_bc_no_canvases(SomeLoop):
    # Run the loop without canvas; closes immediately
    loop = SomeLoop()
    loop.call_later(0.1, print, "hi from loop!")
    loop.run()


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_run_loop_without_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    loop = SomeLoop()
    group = CanvasGroup(loop)

    # The loop is in its stopped state, but it fires up briefly to do one tick

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < 0.15

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
    assert 0.0 <= et < 0.15

    # Now its in its stopped state again

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < 0.15


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_run_loop_and_close_canvases(SomeLoop):
    # After all canvases are closed, it can take one tick before its detected.

    loop = SomeLoop()
    group = CanvasGroup(loop)

    canvas1 = FakeCanvas()
    canvas2 = FakeCanvas()
    group._register_canvas(canvas1, fake_task)
    group._register_canvas(canvas2, fake_task)

    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.1, canvas1.manually_close)
    loop.call_later(0.3, canvas2.manually_close)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.45

    assert canvas1._events.is_closed
    assert canvas2._events.is_closed


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
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


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_run_loop_and_interrupt_harder(SomeLoop):
    # In the next tick after the second interupt, it stops the loop without closing the canvases

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

    # Now the close event is not send!
    assert not canvas1._events.is_closed
    assert not canvas2._events.is_closed


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_loop_threaded(SomeLoop):
    t = threading.Thread(target=test_run_loop_and_close_by_loop_stop, args=(SomeLoop,))
    t.start()
    t.join()


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


if __name__ == "__main__":
    run_tests(globals())
