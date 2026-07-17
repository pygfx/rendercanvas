"""
Tests for the terminal backend.
"""

import io
import sys

import rendercanvas
from rendercanvas.terminal import RenderCanvas, loop

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper


def setup_module():
    rendercanvas.terminal.term_stream = io.StringIO()


def teardown_module():
    rendercanvas.terminal.term_stream = sys.__stdout__


class TerminalHelper(NativeHelper):
    def close_canvas(self, canvas):
        canvas.close()


EXCLUDES = ["backend_sizing"]


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_terminal(func):
    if func.__name__ in EXCLUDES:
        pytest.skip()
    func(RenderCanvas, loop, TerminalHelper())


if __name__ == "__main__":
    setup_module()
    run_tests(globals())
    teardown_module()
