"""
Tests for the trio loop. We use the glfw canvas to test it with.
"""

from rendercanvas.trio import loop
from rendercanvas.glfw import GlfwRenderCanvas

import pytest
from testutils import run_tests, can_use_glfw
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper


if not can_use_glfw:
    pytest.skip("Skipping tests that needs glfw", allow_module_level=True)


import glfw


class TrioRenderCanvas(GlfwRenderCanvas):
    pass


TrioRenderCanvas.select_loop(loop)


class TrioHelper(NativeHelper):
    def close_canvas(self, canvas):
        glfw.set_window_should_close(canvas._window, 1)


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_trio(func):
    func(TrioRenderCanvas, loop, TrioHelper())


if __name__ == "__main__":
    run_tests(globals())
