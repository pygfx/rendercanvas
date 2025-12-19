"""
Tests specific to wx

Only runs when explicitly targeted, because running multiple GUI
frameworks in the same process never works.
"""

import sys

import pytest
from testutils import run_tests


# Only run when running directly (through Python or pytest)
if not (__name__ == "__main__" or any(__name__ in a for a in sys.argv)):
    pytest.skip("Skipping tests that need wx", allow_module_level=True)


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


def test_canvas_sizing():
    canvas = RenderCanvas(size=(640, 480))
    canvas._rc_gui_poll()

    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == (640, 480)

    canvas.set_logical_size(700, 600)
    canvas._rc_gui_poll()

    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == (700, 600)

    assert len(canvas.get_physical_size()) == 2
    assert isinstance(canvas.get_pixel_ratio(), float)

    # Close
    assert not canvas.get_closed()
    canvas.close()
    canvas._rc_gui_poll()
    assert canvas.get_closed()


if __name__ == "__main__":
    run_tests(globals())
