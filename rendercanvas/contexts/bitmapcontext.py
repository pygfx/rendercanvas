from .basecontext import BaseContext

__all__ = ["BitmapContext", "BitmapContextToBitmap", "BitmapContextToScreen"]


class BitmapContext(BaseContext):
    """A context that exposes an API that takes a (grayscale or rgba) images bitmap.

    This is loosely inspired by JS' ``ImageBitmapRenderingContext``. Rendering
    bitmaps is a simple way to use ``rendercanvas``, but usually not as
    performant as a wgpu context. Use ``canvas.get_bitmap_context()`` to create
    a ``BitmapContext``.
    """

    # Note:  instantiating this class creates an instance of a sub-class, dedicated to the present method of the canvas.

    present_methods = ["bitmap", "screen"]

    def __new__(cls, present_info: dict):
        # Instantiating this class actually produces a subclass
        present_method = present_info["method"]
        if cls is not BitmapContext:
            return super().__new__(cls)  # Use canvas that is explicitly instantiated
        elif present_method == "bitmap":
            return super().__new__(BitmapContextToBitmap)
        elif present_method == "screen":
            return super().__new__(BitmapContextToScreen)
        else:
            raise TypeError("Unexpected present_method {present_method!r}")

    def __init__(self, present_info):
        super().__init__(present_info)
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


class BitmapContextToBitmap(BitmapContext):
    """A BitmapContext that just presents the bitmap to the canvas."""

    present_methods = ["bitmap"]

    def __init__(self, present_info):
        super().__init__(present_info)
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

    def _rc_close(self):
        self._bitmap_and_format = None


class BitmapContextToScreen(BitmapContext):
    """A BitmapContext that uploads to a texture and present that to a ``wgpu.GPUCanvasContext``.

    This is uses for canvases that do not support presenting a bitmap.
    """

    present_methods = ["screen"]

    def __init__(self, present_info):
        super().__init__(present_info)

        # Init wgpu
        import wgpu
        from ._fullscreen import FullscreenTexture

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        device = self._device = adapter.request_device_sync(required_limits={})

        self._texture_helper = FullscreenTexture(device)

        self._create_wgpu_py_context()  # sets self._wgpu_context
        self._wgpu_context_is_configured = False

    def _rc_present(self):
        if self._bitmap_and_format is None:
            return {"method": "skip"}

        # Supported formats are "rgba-u8" and "i-u8" (grayscale).
        # Returns the present-result dict produced by ``GPUCanvasContext.present()``.

        bitmap = self._bitmap_and_format[0]
        self._texture_helper.set_texture_data(bitmap)

        if not self._wgpu_context_is_configured:
            format = self._wgpu_context.get_preferred_format(self._device.adapter)
            # We don't want an srgb texture, because we assume the input bitmap is already srgb.
            # AFAIK contexts always support both the regular and the srgb texture format variants
            if format.endswith("-srgb"):
                format = format[:-5]
            self._wgpu_context.configure(device=self._device, format=format)

        target = self._wgpu_context.get_current_texture().create_view()
        command_encoder = self._device.create_command_encoder()
        self._texture_helper.draw(command_encoder, target)
        self._device.queue.submit([command_encoder.finish()])

        present_feedback = self._wgpu_context.present()

        # We actually allow the _wgpu_context to return present_feedback, because we have a test in which
        # we mimick a GPUCanvasContext with a WgpuContextToBitmap to cover a full round-trip to wgpu.
        if present_feedback is None:
            present_feedback = {"method": "screen"}

        return present_feedback

    def _rc_close(self):
        self._bitmap_and_format = None
        if self._wgpu_context is not None:
            self._wgpu_context.unconfigure()
