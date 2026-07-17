"""
Tests for the trio loop. We use the offscreem canvas to test it with.
"""

from rendercanvas.base import BaseCanvasGroup
from rendercanvas.trio import loop
from rendercanvas.offscreen import RenderCanvas

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper


# ----- A fresh canvas class and loop, for use in these tests


class TrioLoop(loop.__class__):
    pass


loop = TrioLoop()


class CanvasGroup(BaseCanvasGroup):
    pass


class TrioCanvas(RenderCanvas):
    _rc_canvas_group = CanvasGroup(loop)


# -----


class TrioHelper(NativeHelper):
    def close_canvas(self, canvas):
        canvas.close()


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_trio(func):
    func(TrioCanvas, loop, TrioHelper())


if __name__ == "__main__":
    run_tests(globals())
