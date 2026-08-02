"""
Tests specific for qt.

Only runs when explicitly targeted, because running multiple GUI
frameworks in the same process never works.
"""

# ruff: noqa: E402

import sys
import importlib

import gc
import time
import weakref

import pytest
from testutils import run_tests, can_use_wgpu_lib
from testutils_backends import BACKEND_TEST_FUNCS, NativeHelper, _get_draw_function


# Only run when running directly (through Python or pytest)
if not (__name__ == "__main__" or any(__name__ in a for a in sys.argv)):
    pytest.skip(f"Skipping backend specific tests {__name__}", allow_module_level=True)


QtWidgets = None
backend_name = "no-backend"
for lib in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
    if any(lib.lower() == a.lower() for a in sys.argv):
        QtWidgets = importlib.import_module(".QtWidgets", lib)
        backend_name = lib.lower()
        break
if QtWidgets is None:
    for lib in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
        try:
            QtWidgets = importlib.import_module(".QtWidgets", lib)
            backend_name = lib.lower()
            break
        except ModuleNotFoundError:
            pass
if QtWidgets is None:
    raise RuntimeError("No Qt lib found!")


from rendercanvas.base import BaseRenderCanvas, WrapperRenderCanvas
from rendercanvas.contexts.wgpucontext import WgpuContextToScreen
from rendercanvas.qt import RenderCanvas, RenderWidget, loop
from rendercanvas.qt import QRenderWidget, QRenderCanvas


def test_is_canvas_classes():
    assert QRenderCanvas is RenderCanvas
    assert QRenderWidget is RenderWidget

    assert issubclass(RenderWidget, BaseRenderCanvas)
    assert issubclass(RenderCanvas, BaseRenderCanvas)
    assert issubclass(RenderCanvas, WrapperRenderCanvas)

    assert issubclass(RenderWidget, QtWidgets.QWidget)
    assert issubclass(RenderCanvas, QtWidgets.QWidget)  # toplevel


class QtHelper(NativeHelper):
    def close_canvas(self, canvas):
        QtWidgets.QWidget.close(canvas)


@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_qt(func):
    func(RenderCanvas, loop, QtHelper())


def test_backend_qt_present_to_screen():
    # Render with present_method 'screen'. Unlike the default ('bitmap'), this
    # exercises the code to obtain a native surface, and on Wayland the code to
    # get the wl_display that Qt is connected to. See rendercanvas.qt.
    if not can_use_wgpu_lib:
        pytest.skip("Skipping tests that needs the wgpu lib")

    import wgpu

    canvas = RenderCanvas(size=(640, 480), present_method="screen")

    # Confirm that we really present to screen. Otherwise this would silently
    # test the same thing as the bitmap present (i.e. not the screen code path).
    context = canvas.get_context("wgpu")
    assert isinstance(context, WgpuContextToScreen)

    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    canvas.request_draw(_get_draw_function(device, canvas))

    loop.call_later(0.5, canvas.close)
    loop.run()

    assert canvas.get_closed()

    canvas_ref = weakref.ref(canvas)
    del canvas
    gc.collect()
    time.sleep(0.02)
    gc.collect()

    assert canvas_ref() is None
    assert loop._BaseLoop__state == "off"


if __name__ == "__main__":
    run_tests(globals())
