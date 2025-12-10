"""
Test the behaviour of our asyncadapter w.r.t. sniffio.

We want to make sure that it reports the running lib and loop correctly,
so that other code can use sniffio to get our loop and e.g.
call_soon_threadsafe, without actually knowing about rendercanvas, other
than that it's API is very similar to asyncio.
"""


# ruff: noqa: N803

import sys
import asyncio

from testutils import run_tests
import rendercanvas
from rendercanvas.base import BaseCanvasGroup, BaseRenderCanvas
from rendercanvas.asyncio import loop as asyncio_loop

from rendercanvas.asyncio import AsyncioLoop
from rendercanvas.trio import TrioLoop
from rendercanvas.raw import RawLoop

import sniffio
import pytest


class CanvasGroup(BaseCanvasGroup):
    pass


class RealRenderCanvas(BaseRenderCanvas):
    _rc_canvas_group = CanvasGroup(asyncio_loop)
    _is_closed = False

    def _rc_close(self):
        self._is_closed = True
        self.submit_event({"event_type": "close"})

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_request_draw(self):
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._draw_frame_and_present)


def get_sniffio_name():
    try:
        return sniffio.current_async_library()
    except sniffio.AsyncLibraryNotFoundError:
        return None


def test_no_loop_running():
    assert get_sniffio_name() is None

    with pytest.raises(RuntimeError):
        rendercanvas.utils.asyncadapter.get_running_loop()


@pytest.mark.parametrize("SomeLoop", [RawLoop, AsyncioLoop])
def test_sniffio_on_loop(SomeLoop):
    loop = SomeLoop()

    RealRenderCanvas.select_loop(loop)

    c = RealRenderCanvas()

    names = []
    funcs = []

    @c.request_draw
    def draw():
        name = get_sniffio_name()
        names.append(("draw", name))

        # Downstream code like wgpu-py can use this with sniffio
        mod = sys.modules[name]
        running_loop = mod.get_running_loop()
        funcs.append(running_loop.call_soon_threadsafe)

    @c.add_event_handler("*")
    def on_event(event):
        names.append((event["event_type"], get_sniffio_name()))

    loop.call_later(0.3, c.close)
    # loop.call_later(1.3, loop.stop)  # failsafe

    loop.run()

    refname = "nope"
    if SomeLoop is RawLoop:
        refname = "rendercanvas.utils.asyncadapter"
    elif SomeLoop is AsyncioLoop:
        refname = "asyncio"
    elif SomeLoop is TrioLoop:
        refname = "trio"

    for key, val in names:
        assert val == refname

    assert len(funcs) == 1
    for func in funcs:
        assert callable(func)


def test_asyncio():
    # Just make sure that in a call_soon/call_later the get_running_loop stil works

    loop = asyncio.new_event_loop()

    running_loops = []

    def set_current_loop(name):
        running_loops.append((name, asyncio.get_running_loop()))

    loop.call_soon(set_current_loop, "call_soon")
    loop.call_later(0.1, set_current_loop, "call_soon")
    loop.call_soon(loop.call_soon_threadsafe, set_current_loop, "call_soon_threadsafe")
    loop.call_later(0.2, loop.stop)
    loop.run_forever()

    print(running_loops)
    assert len(running_loops) == 3
    for name, running_loop in running_loops:
        assert running_loop is loop


if __name__ == "__main__":
    run_tests(globals())
