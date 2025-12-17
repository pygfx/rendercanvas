"""
Test the canvas, and parts of the rendering that involves a canvas,
like the canvas context and surface texture.
"""

import time
import pytest
from testutils import run_tests

try:
    import wx
    from rendercanvas.wx import RenderCanvas, loop
except ImportError as e:
    print(f"Import failed: {e}")
    wx = None
    RenderCanvas = None
    loop = None


if wx is None:
    pytest.skip("Skipping tests that need wx", allow_module_level=True)


def setup_module():
    # Ensure app exists
    app = wx.App.GetInstance()
    if app is None:
        app = wx.App()
        wx.App.SetInstance(app)


def teardown_module():
    # We don't really need to tear down the app, as it might be used by other tests?
    # But we can process events one last time.
    loop.process_wx_events()


def test_wx_canvas_sizing():
    """Ensures resizing a wx.RenderCanvas correctly sets the size of the renderable area."""

    canvas = RenderCanvas()
    original_size = canvas.get_logical_size()
    new_size = (original_size[0] * 2, original_size[1] * 2)

    canvas.set_logical_size(*new_size)
    loop.process_wx_events()
    
    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == new_size

    assert len(canvas.get_physical_size()) == 2
    assert isinstance(canvas.get_pixel_ratio(), float)

    # Close
    assert not canvas.get_closed()
    canvas.close()
    loop.process_wx_events()
    assert canvas.get_closed()


if __name__ == "__main__":
    setup_module()
    run_tests(globals())
    teardown_module()
