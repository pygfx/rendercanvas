"""
Test scheduling mechanics, by implementing a minimal canvas class to
implement drawing. This tests the basic scheduling mechanics, as well
as the behavior of the different update modes.
"""

import os
import time

from testutils import run_tests
from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.offscreen import StubLoop


class MyCanvasGroup(BaseCanvasGroup):
    pass


class MyLoop(StubLoop):
    pass

    # Note: run() is non-blocking and simply does one iteration to process pending tasks.


class StubContext:
    def _rc_present(self, force_sync=False):
        return {"method": "skip"}


class MyCanvas(BaseRenderCanvas):
    _rc_canvas_group = MyCanvasGroup(MyLoop())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._closed = False
        self.draw_count = 0
        self.events_count = 0
        self._gui_draw_requested = False
        self._present_to_screen = False
        self._canvas_context = StubContext()

    def _rc_close(self):
        self._closed = True

    def _rc_get_closed(self):
        return self._closed

    def _process_events(self):
        self.events_count += 1
        return super()._process_events()

    def _draw_and_present(self, *, force_sync):
        super()._draw_and_present(force_sync=force_sync)
        self.draw_count += 1

    def active_sleep(self, delay):
        loop = self._rc_canvas_group.get_loop()  # <----
        etime = time.perf_counter() + delay
        while time.perf_counter() < etime:
            time.sleep(0.001)
            loop.run()


def test_scheduling_manual():
    canvas = MyCanvas(min_fps=0.000001, max_fps=100, update_mode="manual")

    # Booting ...
    canvas.active_sleep(0.001)
    assert canvas.draw_count == 0
    assert canvas.events_count == 0

    # No draws, even after the 0.1 init time
    canvas.active_sleep(0.11)
    assert canvas.draw_count == 0
    assert canvas.events_count in range(1, 10)

    # Requesting a draw ... has no effect
    canvas.request_draw()
    canvas.active_sleep(0.11)
    assert canvas.draw_count == 0
    assert canvas.events_count in range(1, 30)

    # Only when we force one
    canvas.force_draw()
    assert canvas.draw_count == 1


def test_scheduling_ondemand():
    canvas = MyCanvas(min_fps=0.000001, max_fps=100, update_mode="ondemand")

    # There's a small startup time, so no activity at first
    canvas.active_sleep(0.001)
    assert canvas.draw_count == 0
    assert canvas.events_count == 0

    # The first draw is scheduled for 0.1 s after initialization
    canvas.active_sleep(0.11)
    assert canvas.draw_count == 1
    assert canvas.events_count in range(1, 10)

    # No next draw is scheduled until we request one
    canvas.active_sleep(0.1)
    assert canvas.draw_count == 1
    assert canvas.events_count in range(10, 20)

    # Requesting a draw ... has effect after a few loop ticks
    canvas.request_draw()
    assert canvas.draw_count == 1
    canvas.active_sleep(0.011)
    assert canvas.draw_count == 2

    # Forcing a draw has direct effect
    canvas.draw_count = canvas.events_count = 0
    canvas.force_draw()
    assert canvas.draw_count == 1
    assert canvas.events_count == 0


def test_scheduling_ondemand_always_request_draw():
    # Test that using ondemand mode with a request_draw() in the
    # draw function, is equivalent to continuous mode.

    canvas = MyCanvas(max_fps=10, update_mode="ondemand")

    @canvas.request_draw
    def draw_func():
        canvas.request_draw()

    _test_scheduling_continuous(canvas)


def test_scheduling_continuous():
    canvas = MyCanvas(max_fps=10, update_mode="continuous")
    _test_scheduling_continuous(canvas)


def _test_scheduling_continuous(canvas):
    # There's a small startup time, so no activity at first
    canvas.active_sleep(0.001)
    assert canvas.draw_count == 0
    assert canvas.events_count == 0

    # The first draw is scheduled for 0.1 s after initialization
    canvas.active_sleep(0.11)
    assert canvas.draw_count == 1
    assert canvas.events_count == 1

    # And a second one after 0.1s, with 10 fps.
    canvas.active_sleep(0.1)
    assert canvas.draw_count == 2
    assert canvas.events_count == 2

    # And after one second, about 10 more
    canvas.draw_count = canvas.events_count = 0
    canvas.active_sleep(1)
    assert canvas.draw_count in range(9, 11)
    assert canvas.events_count in range(9, 11)

    # Forcing a draw has direct effect
    canvas.draw_count = canvas.events_count = 0
    canvas.force_draw()
    assert canvas.draw_count == 1
    assert canvas.events_count == 0


def test_scheduling_fastest():
    canvas = MyCanvas(max_fps=10, update_mode="fastest")

    # There's a small startup time, so no activity at first
    canvas.active_sleep(0.001)
    assert canvas.draw_count == 0
    assert canvas.events_count == 0

    # The first draw is scheduled for 0.1 s after initialization
    canvas.active_sleep(0.11)
    assert canvas.draw_count > 1
    assert canvas.events_count == canvas.draw_count

    # And after 0.1 s we have a lot more draws. max_fps is ignored
    canvas.draw_count = canvas.events_count = 0
    canvas.active_sleep(0.1)
    assert canvas.draw_count > (5 if os.getenv("CI") else 15)
    assert canvas.events_count == canvas.draw_count

    # Forcing a draw has direct effect
    canvas.draw_count = canvas.events_count = 0
    canvas.force_draw()
    assert canvas.draw_count == 1
    assert canvas.events_count == 0


if __name__ == "__main__":
    run_tests(globals())
