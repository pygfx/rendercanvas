import numpy as np
from rendercanvas.utils.bitmappresentadapter import BitmapPresentAdapter
from rendercanvas.utils.bitmaprenderingcontext import BitmapRenderingContext
from rendercanvas.offscreen import ManualOffscreenRenderCanvas

from testutils import run_tests
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


hook_call_count = 0


def rendercanvas_context_hook(canvas, present_methods):
    global hook_call_count
    hook_call_count += 1
    return SpecialAdapterNoop(canvas, present_methods)


class SpecialAdapterNoop:
    def __init__(self, canvas, present_methods):
        self.canvas = canvas

    def present(self):
        return {"method": "skip"}


class SpecialAdapterFail1:
    def __init__(self, canvas, present_methods):
        1 / 0  # noqa


class SpecialAdapterFail2:
    # does not have a present method
    def __init__(self, canvas, present_methods):
        self.canvas = canvas


class SpecialContextWithWgpuAdapter:
    """This looks a lot like the BitmapPresentAdapter,
    except it will *always* use the adapter, so that we can touch that code path.
    """

    def __init__(self, canvas, present_methods):
        self.adapter = BitmapPresentAdapter(canvas, present_methods)
        self.canvas = canvas

    def set_bitmap(self, bitmap):
        self.bitmap = bitmap

    def present(self):
        return self.adapter.present_bitmap(self.bitmap)


# %%


def test_context_selection11():
    # Select our builtin bitmap context

    canvas = ManualOffscreenRenderCanvas()

    context = canvas.get_context("bitmap")
    assert isinstance(context, BitmapRenderingContext)

    # Cannot select another context now
    with pytest.raises(RuntimeError):
        canvas.get_context("wgpu")

    # But can select the same one
    context2 = canvas.get_context("bitmap")
    assert context2 is context


def test_context_selection12():
    # Select bitmap context using full module name

    canvas = ManualOffscreenRenderCanvas()

    context = canvas.get_context("rendercanvas.utils.bitmaprenderingcontext")
    assert isinstance(context, BitmapRenderingContext)

    # Same thing
    context2 = canvas.get_context("bitmap")
    assert context2 is context


def test_context_selection13():
    # Select bitmap context using full path to class.
    canvas = ManualOffscreenRenderCanvas()

    context = canvas.get_context(
        "rendercanvas.utils.bitmaprenderingcontext:BitmapRenderingContext"
    )
    assert isinstance(context, BitmapRenderingContext)

    # Same thing ... but get_context cannot know
    with pytest.raises(RuntimeError):
        canvas.get_context("bitmap")


def test_context_selection22():
    # Select bitmap context using full module name, and the hook

    canvas = ManualOffscreenRenderCanvas()

    count = hook_call_count
    context = canvas.get_context(__name__)
    assert hook_call_count == count + 1  # hook is called

    assert isinstance(context, SpecialAdapterNoop)


def test_context_selection23():
    # Select bitmap context using full path to class.
    canvas = ManualOffscreenRenderCanvas()

    count = hook_call_count
    context = canvas.get_context(__name__ + ":SpecialAdapterNoop")
    assert hook_call_count == count  # hook is not called

    assert isinstance(context, SpecialAdapterNoop)


def test_context_selection_fails():
    canvas = ManualOffscreenRenderCanvas()

    # Must provide a context type arg
    with pytest.raises(TypeError) as err:
        canvas.get_context()
    assert "context_type" in str(err)

    # Must be a string
    with pytest.raises(TypeError) as err:
        canvas.get_context(BitmapRenderingContext)
    assert "must be str" in str(err)

    # Must be a valid module
    with pytest.raises(ValueError) as err:
        canvas.get_context("thisisnotavalidmodule")
    assert "no module named" in str(err).lower()

    # Must be a valid module
    with pytest.raises(ValueError) as err:
        canvas.get_context("thisisnot.avalidmodule.either")
    assert "no module named" in str(err).lower()

    # The module must have a hook
    with pytest.raises(ValueError) as err:
        canvas.get_context("rendercanvas._coreutils")
    assert "could not find" in str(err)

    # Error on instantiation
    with pytest.raises(ZeroDivisionError):
        canvas.get_context(__name__ + ":SpecialAdapterFail1")

    # Class does not look like a context
    with pytest.raises(RuntimeError) as err:
        canvas.get_context(__name__ + ":SpecialAdapterFail2")
    assert "does not have a present method." in str(err)


def test_bitmap_context():
    # Create canvas, and select the rendering context
    canvas = ManualOffscreenRenderCanvas()
    context = canvas.get_context("bitmap")
    assert isinstance(context, BitmapRenderingContext)

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


def test_bitmap_to_screen_adapter():
    # Create canvas and attach our special adapter canvas
    canvas = ManualOffscreenRenderCanvas()
    context = canvas.get_context(__name__ + ":SpecialContextWithWgpuAdapter")

    # Create and set bitmap
    bitmap = get_test_bitmap(*canvas.get_physical_size())
    context.set_bitmap(bitmap)

    # Draw! This will call SpecialContextWithWgpuAdapter.present(), which will
    # invoke the adapter to render the bitmap to a texture. The GpuCanvasContext.present()
    # method will also be called, which will download the texture to a bitmap,
    # and that's what we receive as the result.
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
