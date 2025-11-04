"""
Provide a simple context class to support ``canvas.get_context('bitmap')``.
"""

import sys

from .basecontext import BaseContext


class BitmapContext(BaseContext):
    """A context that supports rendering by generating grayscale or rgba images.

    This is inspired by JS ``get_context('bitmaprenderer')`` which returns a ``ImageBitmapRenderingContext``.
    It is a relatively simple context to implement, and provides a easy entry to using ``rendercanvas``.
    """

    def __new__(cls, canvas: object, present_info: dict):
        present_method = present_info["method"]
        if present_method == "bitmap":
            return super().__new__(BitmapToBitmapContext)
        elif present_method == "wgpu":
            return super().__new__(BitmapToWgpuContext)
        else:
            raise TypeError("Unexpected present_method {present_method!r}")

    def __init__(self, canvas, present_info):
        super().__init__(canvas, present_info)
        self._bitmap_and_format = None

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


class BitmapToBitmapContext(BitmapContext):
    """A BitmapContext that presents a bitmap to the canvas."""

    def __init__(self, canvas, present_info):
        super().__init__(canvas, present_info)
        assert self._present_info["method"] == "bitmap"
        self._bitmap_and_format = None

    def _rc_present(self):
        if self._bitmap_and_format is None:
            return {"method": "skip"}

        bitmap, format = self._bitmap_and_format
        if format not in self._present_info["formats"]:
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


class BitmapToWgpuContext(BitmapContext):
    """A BitmapContext that presents via a wgpu.GPUCanvasContext.

    This adapter can be used by context objects that want to present a bitmap, when the
    canvas only supports presenting to screen.
    """

    def __init__(self, canvas, present_info):
        super().__init__(canvas, present_info)
        assert self._present_info["method"] == "wgpu"

        # Init wgpu
        import wgpu
        from ._fullscreen import FullscreenTexture

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        device = self._device = adapter.request_device_sync(required_limits={})

        self._texture_helper = FullscreenTexture(device)

        # Create sub context, support both the old and new wgpu-py API
        backend_module = wgpu.gpu.__module__
        CanvasContext = sys.modules[backend_module].GPUCanvasContext  # noqa: N806

        if hasattr(CanvasContext, "set_physical_size"):
            self._sub_context_is_new_style = True
            self._sub_context = CanvasContext(present_info)
        else:
            self._sub_context_is_new_style = False
            self._sub_context = CanvasContext(canvas, {"screen": present_info})
        self._sub_context_is_configured = False

    def _rc_set_physical_size(self, width: int, height: int) -> None:
        super()._rc_set_physical_size(width, height)
        if self._sub_context_is_new_style:
            self._sub_context.set_physical_size(width, height)

    def _rc_present(self):
        if self._bitmap_and_format is None:
            return {"method": "skip"}

        # Supported formats are "rgba-u8" and "i-u8" (grayscale).
        # Returns the present-result dict produced by ``GPUCanvasContext.present()``.

        bitmap = self._bitmap_and_format[0]
        self._texture_helper.set_texture_data(bitmap)

        if not self._sub_context_is_configured:
            format = self._sub_context.get_preferred_format(self._device.adapter)
            # We don't want an srgb texture, because we assume the input bitmap is already srgb.
            # AFAIK contexts always support both the regular and the srgb texture format variants
            if format.endswith("-srgb"):
                format = format[:-5]
            self._sub_context.configure(device=self._device, format=format)

        target = self._sub_context.get_current_texture().create_view()
        command_encoder = self._device.create_command_encoder()
        self._texture_helper.draw(command_encoder, target)
        self._device.queue.submit([command_encoder.finish()])

        self._sub_context.present()
        return {"method": "delegated"}
