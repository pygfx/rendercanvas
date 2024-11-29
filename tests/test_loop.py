"""
Some tests for the base loop and asyncio loop.
"""

import time
import signal
import threading

from rendercanvas.asyncio import AsyncioLoop
from testutils import run_tests


class FakeCanvas:
    def __init__(self, refuse_close):
        self.refuse_close = refuse_close
        self.is_closed = False

    def _rc_gui_poll(self):
        pass

    def _rc_close(self):
        # Called by the loop to close a canvas
        if not self.refuse_close:
            self.is_closed = True


class FakeScheduler:
    def __init__(self, refuse_close=False):
        self._canvas = FakeCanvas(refuse_close)

    def get_canvas(self):
        if self._canvas and not self._canvas.is_closed:
            return self._canvas

    def close_canvas(self):
        self._canvas = None


def test_run_loop_and_close_bc_no_canvases():
    # Run the loop without canvas; closes immediately
    loop = AsyncioLoop()
    loop.call_later(0.1, print, "hi from loop!")
    loop.run()


def test_run_loop_and_close_canvases():
    # After all canvases are closed, it can take one tick before its detected.

    loop = AsyncioLoop()

    scheduler1 = FakeScheduler()
    scheduler2 = FakeScheduler()
    loop._register_scheduler(scheduler1)
    loop._register_scheduler(scheduler2)

    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.1, scheduler1.close_canvas)
    loop.call_later(0.3, scheduler2.close_canvas)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.45


def test_run_loop_and_close_with_method():
    # Close, then wait at most one tick to close canvases, and another to conform close.
    loop = AsyncioLoop()

    scheduler1 = FakeScheduler()
    scheduler2 = FakeScheduler()
    loop._register_scheduler(scheduler1)
    loop._register_scheduler(scheduler2)

    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.3, loop.stop)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55


def test_run_loop_and_interrupt():
    # Interrupt, calls close, can take one tick to close canvases, and anoter to conform close.

    loop = AsyncioLoop()

    scheduler1 = FakeScheduler()
    scheduler2 = FakeScheduler()
    loop._register_scheduler(scheduler1)
    loop._register_scheduler(scheduler2)

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


def test_run_loop_and_interrupt_harder():
    # In the next tick after the second interupt, it stops the loop without closing the canvases

    loop = AsyncioLoop()

    scheduler1 = FakeScheduler(refuse_close=True)
    scheduler2 = FakeScheduler(refuse_close=True)
    loop._register_scheduler(scheduler1)
    loop._register_scheduler(scheduler2)

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


def test_loop_threaded():
    t = threading.Thread(target=test_run_loop_and_close_with_method)
    t.start()
    t.join()


if __name__ == "__main__":
    run_tests(globals())
