"""
Provide a simple context class to support ``canvas.get_context('bitmap')``.
"""

import weakref


def rendercanvas_context_hook(canvas, present_methods):
    """Hook so this context can be picked up by ``canvas.get_context()``"""
    return BitmapRenderingContext(canvas, present_methods)


class BitmapRenderingContext:
    """A context that supports rendering by generating grayscale or rgba images.

    This is inspired by JS ``get_context('bitmaprenderer')`` which returns a ``ImageBitmapRenderingContext``.
    It is a relatively simple context to implement, and provides a easy entry to using ``rendercanvas``.
    """

    def __init__(self, canvas, present_methods):
        self._canvas_ref = weakref.ref(canvas)
        self._present_methods = present_methods
        assert "screen" in present_methods or "bitmap" in present_methods
        self._present_method = "bitmap" if "bitmap" in present_methods else "screen"
        if self._present_method == "screen":
            from rendercanvas.utils.bitmappresentadapter import BitmapPresentAdapter

            self._screen_adapter = BitmapPresentAdapter(canvas, present_methods)

        self._bitmap_and_format = None

    @property
    def canvas(self):
        """The associated canvas object."""
        return self._canvas_ref()

    def set_bitmap(self, bitmap):
        """Set the rendered bitmap image.

        Call this in the draw event. The bitmap must be an object that can be
        conveted to a memoryview, like a numpy array. It must represent a 2D
        image in either grayscale or rgba format, with uint8 values
        """

        m = memoryview(bitmap)

        # Check dtype
        if m.format == "B":
            dtype = "u8"
        else:
            raise ValueError(
                "Unsupported bitmap dtype/format '{m.format}', expecting unsigned bytes ('B')."
            )

        # Get color format
        color_format = None
        if len(m.shape) == 2:
            color_format = "i"
        elif len(m.shape) == 3:
            if m.shape[2] == 1:
                color_format = "i"
            elif m.shape[2] == 4:
                color_format = "rgba"
        if not color_format:
            raise ValueError(
                f"Unsupported bitmap shape {m.shape}, expecting a 2D grayscale or rgba image."
            )

        # We should now have one of two formats
        format = f"{color_format}-{dtype}"
        assert format in ("rgba-u8", "i-u8")

        self._bitmap_and_format = m, format

    def present(self):
        """Allow RenderCanvas to present the bitmap. Don't call this yourself."""
        if self._bitmap_and_format is None:
            return {"method": "skip"}
        elif self._present_method == "bitmap":
            bitmap, format = self._bitmap_and_format
            if format not in self._present_methods["bitmap"]["formats"]:
                # Convert from i-u8 -> rgba-u8. This surely hurts performance.
                assert format == "i-u8"
                flat_bitmap = bitmap.cast("B", (bitmap.nbytes,))
                new_bitmap = memoryview(bytearray(bitmap.nbytes * 4)).cast("B")
                new_bitmap[::4] = flat_bitmap
                new_bitmap[1::4] = flat_bitmap
                new_bitmap[2::4] = flat_bitmap
                new_bitmap[3::4] = b"\xff" * flat_bitmap.nbytes
                bitmap = new_bitmap.cast("B", (*bitmap.shape, 4))
                format = "rgba-u8"
            return {
                "method": "bitmap",
                "data": bitmap,
                "format": format,
            }
        elif self._present_method == "screen":
            self._screen_adapter.present_bitmap(self._bitmap_and_format[0])
            return {"method": "screen"}
        else:
            return {"method": "fail", "message": "wut?"}
