"""
Tests specific to wx

Only runs when explicitly targeted, because running multiple GUI
frameworks in the same process never works.
"""

import sys

import pytest
from testutils import run_tests
from testutils_backends import BACKEND_TEST_FUNCS


# Only run when running directly (through Python or pytest)
if not (__name__ == "__main__" or any(__name__ in a for a in sys.argv)):
    pytest.skip(f"Skipping backend specific tests {__name__}", allow_module_level=True)


import wx
from rendercanvas.base import BaseRenderCanvas, WrapperRenderCanvas
from rendercanvas.wx import RenderCanvas, RenderWidget
from rendercanvas.wx import WxRenderWidget, WxRenderCanvas


def test_is_canvas_classes():
    assert WxRenderCanvas is RenderCanvas
    assert WxRenderWidget is RenderWidget

    assert issubclass(RenderWidget, BaseRenderCanvas)
    assert issubclass(RenderCanvas, BaseRenderCanvas)
    assert issubclass(RenderCanvas, WrapperRenderCanvas)

    assert issubclass(RenderWidget, wx.Window)
    assert issubclass(RenderCanvas, wx.Frame)


@pytest.mark.parametrize("backend", ["wx"])
@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_generic(func, backend):
    func(backend)


if __name__ == "__main__":
    run_tests(globals())
