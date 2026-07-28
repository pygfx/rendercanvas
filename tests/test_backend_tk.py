"""Tests specific to Tkinter.

Only runs when explicitly targeted, because running multiple GUI frameworks in
the same process is unreliable.
"""

import sys
import tkinter as tk

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS

if not (__name__ == "__main__" or any(__name__ in arg for arg in sys.argv)):
    pytest.skip(f"Skipping backend specific tests {__name__}", allow_module_level=True)

from rendercanvas.base import BaseRenderCanvas, WrapperRenderCanvas
from rendercanvas.tk import RenderCanvas, RenderWidget
from rendercanvas.tk import TkRenderCanvas, TkRenderWidget


def test_is_canvas_classes():
    assert TkRenderCanvas is RenderCanvas
    assert TkRenderWidget is RenderWidget

    assert issubclass(RenderWidget, BaseRenderCanvas)
    assert issubclass(RenderCanvas, BaseRenderCanvas)
    assert issubclass(RenderCanvas, WrapperRenderCanvas)

    assert issubclass(RenderWidget, tk.Canvas)
    assert issubclass(RenderCanvas, tk.Toplevel)

def test_present_bitmap():
    root = tk.Tk()
    root.withdraw()

    try:
        canvas = RenderWidget(root, width=2, height=2)

        rgba = bytearray(
            [
                255, 0, 0, 255,
                0, 255, 0, 128,
                0, 0, 255, 64,
                255, 255, 0, 0,
            ]
        )
        bitmap = memoryview(rgba).cast("B", (2, 2, 4))

        canvas._rc_present_bitmap(data=bitmap, format="rgba-u8")

        assert canvas._photo.width() == 2
        assert canvas._photo.height() == 2
        assert canvas._photo.get(0, 0) == (255, 0, 0)
        assert canvas._photo.get(1, 0) == (0, 255, 0)
        assert canvas._photo.get(0, 1) == (0, 0, 255)
        assert canvas._photo.get(1, 1) == (255, 255, 0)
        assert canvas._image_item is not None
    finally:
        root.destroy()

@pytest.mark.parametrize("backend", ["tk"])
@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_generic(func, backend):
    func(backend)


if __name__ == "__main__":
    run_tests(globals())
