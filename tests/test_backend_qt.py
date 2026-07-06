"""
Tests specific for qt.

Only runs when explicitly targeted, because running multiple GUI
frameworks in the same process never works.
"""

# ruff: noqa: E402

import sys
import importlib

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS


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
from rendercanvas.qt import RenderCanvas, RenderWidget
from rendercanvas.qt import QRenderWidget, QRenderCanvas


def test_is_canvas_classes():
    assert QRenderCanvas is RenderCanvas
    assert QRenderWidget is RenderWidget

    assert issubclass(RenderWidget, BaseRenderCanvas)
    assert issubclass(RenderCanvas, BaseRenderCanvas)
    assert issubclass(RenderCanvas, WrapperRenderCanvas)

    assert issubclass(RenderWidget, QtWidgets.QWidget)
    assert issubclass(RenderCanvas, QtWidgets.QWidget)  # toplevel


def qt_close(canvas):
    QtWidgets.QWidget.close(canvas)


@pytest.mark.parametrize("backend", [backend_name])
@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_generic(func, backend):
    func(backend, close_func=qt_close)


if __name__ == "__main__":
    run_tests(globals())
