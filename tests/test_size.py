"""
Test size mechanics.
"""

from testutils import run_tests
from rendercanvas._size import SizeInfo
from rendercanvas.base import BaseRenderCanvas


def test_size_info_basic():
    si = SizeInfo()
    assert si["physical_size"] == (1, 1)
    assert si["logical_size"] == (1.0, 1.0)
    assert si["total_pixel_ratio"] == 1.0
    assert si["need_size_event"] is False

    # Backends setting physical size
    si.set_physical_size(10, 10, 1)

    assert si["physical_size"] == (10, 10)
    assert si["logical_size"] == (10.0, 10.0)
    assert si["total_pixel_ratio"] == 1.0
    assert si["need_size_event"] is True

    # Different pixel ratio
    si.set_physical_size(10, 10, 2.5)

    assert si["physical_size"] == (10, 10)
    assert si["logical_size"] == (4.0, 4.0)
    assert si["total_pixel_ratio"] == 2.5
    assert si["need_size_event"] is True


def test_size_info_logical():
    si = SizeInfo()
    assert si["physical_size"] == (1, 1)
    assert si["logical_size"] == (1.0, 1.0)
    assert si["total_pixel_ratio"] == 1.0
    assert si["need_size_event"] is False

    # Base class setting logical size
    si.set_logical_size(100, 100)

    assert si["physical_size"] == (1, 1)  # don't touch!
    assert si["logical_size"] == (100.0, 100.0)
    assert si["total_pixel_ratio"] == 0.01
    assert si["need_size_event"] is True

    # Again
    si.set_logical_size(640, 480)

    assert si["physical_size"] == (1, 1)  # don't touch!
    assert si["logical_size"] == (640.0, 480.0)
    assert si["total_pixel_ratio"] == 1 / 640

    # Now backend adjusts its actual size
    si.set_physical_size(1280, 960, 2.0)

    assert si["physical_size"] == (1280, 960)
    assert si["logical_size"] == (640.0, 480.0)
    assert si["total_pixel_ratio"] == 2.0

    # Base class sets logical size again
    si.set_logical_size(100.2, 100.2)

    assert si["physical_size"] == (1280, 960)  # don't touch!
    assert si["logical_size"] == (100.0, 100.0)  # took ratio into account
    assert si["total_pixel_ratio"] == 1280 / 100

    # And again
    si.set_logical_size(101.8, 101.8)

    assert si["physical_size"] == (1280, 960)  # don't touch!
    assert si["logical_size"] == (102.0, 102.0)  # took ratio into account
    assert si["total_pixel_ratio"] == 1280 / 102

    # And backend adjusts its actual size
    si.set_physical_size(204, 204, 2.0)

    assert si["physical_size"] == (204, 204)
    assert si["logical_size"] == (102, 102.0)
    assert si["total_pixel_ratio"] == 2.0


def test_size_info_zoom():
    si = SizeInfo()
    si.set_physical_size(1200, 1200, 2.0)

    assert si["physical_size"] == (1200, 1200)
    assert si["logical_size"] == (600.0, 600.0)
    assert si["total_pixel_ratio"] == 2.0

    # Adjust zoom
    si.set_zoom(3)

    assert si["physical_size"] == (1200, 1200)
    assert si["logical_size"] == (200.0, 200.0)
    assert si["native_pixel_ratio"] == 2.0
    assert si["total_pixel_ratio"] == 6.0

    # Backend updates its size, zoom is maintained
    si.set_physical_size(1800, 1800, 2.0)

    assert si["physical_size"] == (1800, 1800)
    assert si["logical_size"] == (300.0, 300.0)
    assert si["native_pixel_ratio"] == 2.0
    assert si["total_pixel_ratio"] == 6.0

    # Backend updates its physical size
    si.set_physical_size(600, 600, 1.0)

    assert si["physical_size"] == (600, 600)
    assert si["logical_size"] == (200.0, 200.0)
    assert si["native_pixel_ratio"] == 1.0
    assert si["total_pixel_ratio"] == 3.0

    # Adjust zoom last time
    si.set_zoom(2)

    assert si["physical_size"] == (600, 600)
    assert si["logical_size"] == (300.0, 300.0)
    assert si["native_pixel_ratio"] == 1.0
    assert si["total_pixel_ratio"] == 2.0


class MyRenderCanvas(BaseRenderCanvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._requested_size = None
        self._final_canvas_init()

    def _rc_set_logical_size(self, w, h):
        self._requested_size = w, h

    def apply_size(self):
        if self._requested_size:
            self._size_info.set_physical_size(*self._requested_size, 1)
            self._requested_size = None


def test_canvas_sizing():
    c = MyRenderCanvas(size=None)

    assert c.get_logical_size() == (1.0, 1.0)

    c = MyRenderCanvas()

    assert c.get_logical_size() == (640.0, 480.0)
    assert c.get_physical_size() == (1, 1)
    assert c.get_pixel_ratio() == 1 / 640

    c.apply_size()

    assert c.get_logical_size() == (640.0, 480.0)
    assert c.get_physical_size() == (640, 480)
    assert c.get_pixel_ratio() == 1.0


if __name__ == "__main__":
    run_tests(globals())
