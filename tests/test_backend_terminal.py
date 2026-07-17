"""
Tests for the terminal backend.
"""

import io
import sys

import rendercanvas
from rendercanvas.base import BaseCanvasGroup

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper


# Only run when running directly (through Python or pytest)
if not (__name__ == "__main__" or any(__name__ in a for a in sys.argv)):
    pytest.skip(f"Skipping backend specific tests {__name__}", allow_module_level=True)

from rendercanvas.terminal import RenderCanvas, loop


def setup_module():
    rendercanvas.terminal.term_stream = io.StringIO()


def teardown_module():
    rendercanvas.terminal.term_stream = sys.__stdout__


# ----- A fresh canvas class and loop, for use in these tests


class TerminalLoop(loop.__class__):
    pass


loop = TerminalLoop()


class CanvasGroup(BaseCanvasGroup):
    pass


class TerminalCanvas(RenderCanvas):
    _rc_canvas_group = CanvasGroup(loop)


# -----


class TerminalHelper(NativeHelper):
    def close_canvas(self, canvas):
        canvas.close()


EXCLUDES = ["backend_sizing"]


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_terminal(func):
    if func.__name__ in EXCLUDES:
        pytest.skip()
    func(TerminalCanvas, loop, TerminalHelper())


if __name__ == "__main__":
    setup_module()
    run_tests(globals())
    teardown_module()
