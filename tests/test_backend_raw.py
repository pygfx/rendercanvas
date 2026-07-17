"""
Tests for the raw loop. We use the offscreen canvas to test it with.
"""

from rendercanvas.base import BaseCanvasGroup
from rendercanvas.raw import loop
from rendercanvas.offscreen import RenderCanvas

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper


# ----- A fresh canvas class and loop, for use in these tests


class RawLoop(loop.__class__):
    pass


loop = RawLoop()


class CanvasGroup(BaseCanvasGroup):
    pass


class RawCanvas(RenderCanvas):
    _rc_canvas_group = CanvasGroup(loop)


# -----


class RawHelper(NativeHelper):
    def close_canvas(self, canvas):
        canvas.close()


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_raw(func):
    func(RawCanvas, loop, RawHelper())


if __name__ == "__main__":
    run_tests(globals())
