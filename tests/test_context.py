import numpy as np
from rendercanvas.contexts import (
    BaseContext,
    BitmapContext,
    WgpuContext,
    BitmapContextToScreen,
    WgpuContextToBitmap,
)
from rendercanvas.offscreen import OffscreenRenderCanvas as ManualOffscreenRenderCanvas

from testutils import can_use_wgpu_lib, run_tests
import pytest


def get_test_bitmap(width, height):
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (0, 0, 0, 255),
        (50, 50, 50, 255),
        (127, 127, 127, 255),
        (205, 205, 205, 255),
        (255, 255, 255, 255),
    ]
    w = width // len(colors)
    bitmap = np.zeros((height, width, 4), np.uint8)
    for i, color in enumerate(colors):
        bitmap[:, i * w : (i + 1) * w, :] = color
    return bitmap


class WgpuContextToBitmapLookLikeWgpuPy(WgpuContextToBitmap):
    """A WgpuContextToBitmap with an API like (the new) wgpu.GPUCanvasContext.

    The API's look close enough that we can mimic it with this. This allows
    testing a workflow that goes from bitmap -> wgpu -> wgpu -> bitmap
    """

    def set_physical_size(self, w, h):
        size_info = {
            "physical_size": (w, h),
            "native_pixel_ratio": 1.0,
            "total_pixel_ratio": 1.0,
            "logical_size": (float(w), float(h)),
        }
        self._rc_set_size_info(size_info)

    def present(self):
        return self._rc_present()

    def close(self):
        self._rc_close()


class BitmapContextToWgpuAndBackToBimap(BitmapContextToScreen):
    """A bitmap context that takes a detour via wgpu :)"""

    def _create_wgpu_py_context(self):
        self._wgpu_context = WgpuContextToBitmapLookLikeWgpuPy(self._present_info)


# %%


def test_context_selection_bitmap():
    # Select our builtin bitmap context

    canvas = ManualOffscreenRenderCanvas()

    context = canvas.get_context("bitmap")
    assert isinstance(context, BitmapContext)
    assert isinstance(context, BaseContext)

    # Cannot select another context now
    with pytest.raises(RuntimeError):
        canvas.get_context("wgpu")

    # But can select the same one
    context2 = canvas.get_context("bitmap")
    assert context2 is context

    # And this also works
    context2 = canvas.get_bitmap_context()
    assert context2 is context


@pytest.mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")
def test_context_selection_wgpu():
    # Select our builtin bitmap context

    canvas = ManualOffscreenRenderCanvas()

    context = canvas.get_context("wgpu")
    assert isinstance(context, WgpuContext)
    assert isinstance(context, BaseContext)

    # Cannot select another context now
    with pytest.raises(RuntimeError):
        canvas.get_context("bitmap")

    # But can select the same one
    context2 = canvas.get_context("wgpu")
    assert context2 is context

    # And this also works
    context2 = canvas.get_wgpu_context()
    assert context2 is context


def test_context_selection_fails():
    canvas = ManualOffscreenRenderCanvas()

    # Must provide a context type arg
    with pytest.raises(TypeError) as err:
        canvas.get_context()
    assert "context_type" in str(err)

    # Must be a string
    with pytest.raises(TypeError) as err:
        canvas.get_context(BitmapContext)
    assert "must be str" in str(err)

    # Must be a valid string
    with pytest.raises(TypeError) as err:
        canvas.get_context("notacontexttype")
    assert "context type is invalid" in str(err)


def test_bitmap_context():
    # Create canvas, and select the rendering context
    canvas = ManualOffscreenRenderCanvas()
    context = canvas.get_context("bitmap")
    assert isinstance(context, BitmapContext)

    # Create and set bitmap
    bitmap = get_test_bitmap(*canvas.get_physical_size())
    context.set_bitmap(bitmap)

    # Draw! This is not *that* interesting, it just passes the bitmap around
    result = canvas.draw()

    assert isinstance(result, memoryview)
    result = np.asarray(result)
    assert np.all(result == bitmap)

    # pssst ... it's actually the same data!
    bitmap.fill(42)
    assert np.all(result == bitmap)

    # Now we change the size

    bitmap = get_test_bitmap(50, 50)
    context.set_bitmap(bitmap)

    result = np.asarray(canvas.draw())

    assert result.shape == bitmap.shape
    assert np.all(result == bitmap)


@pytest.mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")
def test_wgpu_context():
    # Create canvas and attach our special adapter canvas
    canvas = ManualOffscreenRenderCanvas()
    context = BitmapContextToWgpuAndBackToBimap(
        {"method": "bitmap", "formats": ["rgba-u8"]}
    )
    canvas._canvas_context = context
    assert isinstance(context, BitmapContext)

    # Create and set bitmap
    bitmap = get_test_bitmap(*canvas.get_physical_size())
    context.set_bitmap(bitmap)

    # Draw! The primary context will upload the bitmap to a wgpu texture,
    # and the wrapped context will then download it to a bitmap again.
    # So this little line here touches quite a lot of code. In the end, the bitmap
    # should be unchanged, because the adapter assumes that the incoming bitmap
    # is in the sRGB colorspace.
    result = canvas.draw()

    assert isinstance(result, memoryview)
    result = np.asarray(result)
    assert np.all(result == bitmap)

    # Now we change the size

    bitmap = get_test_bitmap(50, 50)
    context.set_bitmap(bitmap)

    result = np.asarray(canvas.draw())
    assert result.shape != bitmap.shape
    assert result.shape[1] == canvas.get_physical_size()[0]
    assert result.shape[0] == canvas.get_physical_size()[1]


if __name__ == "__main__":
    run_tests(globals())
