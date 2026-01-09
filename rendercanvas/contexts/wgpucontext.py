import time
from typing import Sequence

from .basecontext import BaseContext


__all__ = ["WgpuContext", "WgpuContextToBitmap", "WgpuContextToScreen"]


class WgpuContext(BaseContext):
    """A context that exposes an API that provides a GPU texture to render to.

    This is inspired by JS' ``GPUCanvasContext``, and the more performant
    approach for rendering to a ``rendercanvas``. Use
    ``canvas.get_wgpu_context()`` to create a ``WgpuContext``.
    """

    # Note:  instantiating this class creates an instance of a sub-class, dedicated to the present method of the canvas.

    present_methods = ["screen", "bitmap"]

    def __new__(cls, present_info: dict):
        # Instantiating this class actually produces a subclass
        present_method = present_info["method"]
        if cls is not WgpuContext:
            return super().__new__(cls)  # Use canvas that is explicitly instantiated
        elif present_method == "screen":
            return super().__new__(WgpuContextToScreen)
        elif present_method == "bitmap":
            return super().__new__(WgpuContextToBitmap)
        else:
            raise TypeError("Unexpected present_method {present_method!r}")

    def __init__(self, present_info: dict):
        super().__init__(present_info)
        # Configuration dict from the user, set via self.configure()
        self._config = None

    def get_preferred_format(self, adapter: object) -> str:
        """Get the preferred surface texture format."""
        return self._get_preferred_format(adapter)

    def _get_preferred_format(self, adapter: object) -> str:
        raise NotImplementedError()

    def get_configuration(self) -> dict | None:
        """Get the current configuration (or None if the context is not yet configured)."""
        return self._config

    def configure(
        self,
        *,
        device: object,
        format: str,
        usage: str | int = "RENDER_ATTACHMENT",
        view_formats: Sequence[str] = (),
        # color_space: str = "srgb",  - not yet implemented
        # tone_mapping: str | None = None,  - not yet implemented
        alpha_mode: str = "opaque",
    ) -> None:
        """Configures the presentation context for the associated canvas.
        Destroys any textures produced with a previous configuration.

        Arguments:
            device (WgpuDevice): The GPU device object to create compatible textures for.
            format (wgpu.TextureFormat): The format that textures returned by
                ``get_current_texture()`` will have. Must be one of the supported context
                formats. Can be ``None`` to use the canvas' preferred format.
            usage (wgpu.TextureUsage): Default "RENDER_ATTACHMENT".
            view_formats (list[wgpu.TextureFormat]): The formats that views created
                from textures returned by ``get_current_texture()`` may use.
            alpha_mode (wgpu.CanvasAlphaMode): Determines the effect that alpha values
                will have on the content of textures returned by ``get_current_texture()``
                when read, displayed, or used as an image source. Default "opaque".
        """
        import wgpu

        # Basic checks
        if not isinstance(device, wgpu.GPUDevice):
            raise TypeError("Given device is not a device.")
        if format is None:
            format = self.get_preferred_format(device.adapter)
        if format not in wgpu.TextureFormat:
            raise ValueError(f"Configure: format {format} not in {wgpu.TextureFormat}")
        if isinstance(usage, str):
            usage_bits = usage.replace("|", " ").split()
            usage = 0
            for usage_bit in usage_bits:
                usage |= wgpu.TextureUsage[usage_bit]
        elif not isinstance(usage, int):
            raise TypeError("Texture usage must be str or int")

        # Build config dict
        config = {
            "device": device,
            "format": format,
            "usage": usage,
            "view_formats": view_formats,
            # "color_space": color_space,
            # "tone_mapping": tone_mapping,
            "alpha_mode": alpha_mode,
        }
        # Let subclass finnish the configuration, then store the config
        self._configure(config)
        self._config = config

    def _configure(self, config: dict):
        raise NotImplementedError()

    def unconfigure(self) -> None:
        """Removes the presentation context configuration."""
        self._config = None
        self._unconfigure()

    def _unconfigure(self) -> None:
        raise NotImplementedError()

    def get_current_texture(self) -> object:
        """Get the ``GPUTexture`` that will be composited to the canvas next."""
        if not self._config:
            raise RuntimeError(
                "Canvas context must be configured before calling get_current_texture()."
            )
        return self._get_current_texture()

    def _get_current_texture(self):
        raise NotImplementedError()

    def _rc_present(self) -> None:
        """Hook for the canvas to present the rendered result.

        Present what has been drawn to the current texture, by compositing it to the
        canvas.This is called automatically by the canvas.
        """
        raise NotImplementedError()


class WgpuContextToScreen(WgpuContext):
    """A wgpu context that present directly to a ``wgpu.GPUCanvasContext``.

    In most cases this means the image is rendered to a native OS surface, i.e. rendered to screen.
    When running in Pyodide, it means it renders directly to a ``<canvas>``.
    """

    present_methods = ["screen"]

    draw_must_be_in_animation_frame = True

    def __init__(self, present_info: dict):
        super().__init__(present_info)
        assert self._present_info["method"] == "screen"
        self._create_wgpu_py_context()  # sets self._wgpu_context

    def _get_preferred_format(self, adapter: object) -> str:
        return self._wgpu_context.get_preferred_format(adapter)

    def _configure(self, config):
        self._wgpu_context.configure(**config)

    def _unconfigure(self) -> None:
        self._wgpu_context.unconfigure()

    def _get_current_texture(self) -> object:
        return self._wgpu_context.get_current_texture()

    def _rc_present(self) -> None:
        self._wgpu_context.present()
        return {"method": "screen"}

    def _rc_close(self):
        if self._wgpu_context is not None:
            self._wgpu_context.unconfigure()


class WgpuContextToBitmap(WgpuContext):
    """A wgpu context that downloads the image from the texture, and presents that bitmap to the canvas.

    This is less performant than rendering directly to screen, but once we make the changes such that the
    downloading is be done asynchronously, the difference in performance is not
    actually that big.
    """

    present_methods = ["bitmap"]

    def __init__(self, present_info: dict):
        super().__init__(present_info)

        # Canvas capabilities. Stored the first time it is obtained
        self._capabilities = self._get_capabilities()

        # The current texture to render to. Is replaced when the canvas resizes.
        self._texture = None

        # A ring-buffer to download the rendered images to the CPU/RAM. The
        # image is first copied from the texture to an available copy-buffer.
        # This is very fast (which is why we don't have a ring of textures).
        # Mapping the buffers to RAM takes time, and we want to wait for this
        # asynchronously.
        #
        # It looks like a single buffer is sufficient. Adding more costs memory,
        # and does not necessarily improve the FPS. It can actually strain the
        # GPU more, because it would be busy mapping multiple buffers at the
        # same time. Let's leave the ring-mechanism in-place for now, so we can
        # experiment with it.
        # TODO: refactor to just one downloader, making the code a bit simpler
        self._downloaders = [None]  # Put as many None's as you want buffers

    def _get_capabilities(self):
        """Get dict of capabilities and cache the result."""

        import wgpu

        # Store usage flags now that we have the wgpu namespace
        self._context_texture_usage = wgpu.TextureUsage.COPY_SRC
        self._context_buffer_usage = (
            wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ
        )

        capabilities = {}

        # Query format capabilities from the info provided by the canvas
        formats = []
        for format in self._present_info["formats"]:
            channels, _, fmt = format.partition("-")
            channels = {"i": "r", "ia": "rg"}.get(channels, channels)
            fmt = {
                "u8": "8unorm",
                "u16": "16uint",
                "f16": "16float",
                "f32": "32float",
            }.get(fmt, fmt)
            wgpu_format = channels + fmt
            wgpu_format_srgb = wgpu_format + "-srgb"
            if wgpu_format_srgb in wgpu.TextureFormat:
                formats.append(wgpu_format_srgb)
            formats.append(wgpu_format)

        # Assume alpha modes for now
        alpha_modes = ["opaque"]

        # Build capabilitied dict
        capabilities = {
            "formats": formats,
            "view_formats": formats,
            "usages": 0xFF,
            "alpha_modes": alpha_modes,
        }
        return capabilities

    def _drop_texture(self):
        if self._texture is not None:
            try:
                self._texture._release()  # private method. Not destroy, because it may be in use.
            except Exception:
                pass
            self._texture = None

    def _get_preferred_format(self, adapter: object) -> str:
        formats = self._capabilities["formats"]
        return formats[0] if formats else "bgra8-unorm"

    def _configure(self, config: dict):
        # Get cababilities
        cap_formats = self._capabilities["formats"]
        cap_view_formats = self._capabilities["view_formats"]
        cap_alpha_modes = self._capabilities["alpha_modes"]

        # Check against capabilities
        format = config["format"]
        if format not in cap_formats:
            raise ValueError(
                f"Configure: unsupported texture format: {format} not in {cap_formats}"
            )
        for view_format in config["view_formats"]:
            if view_format not in cap_view_formats:
                raise ValueError(
                    f"Configure: unsupported view format: {view_format} not in {cap_view_formats}"
                )
        alpha_mode = config["alpha_mode"]
        if alpha_mode not in cap_alpha_modes:
            raise ValueError(
                f"Configure: unsupported alpha-mode: {alpha_mode} not in {cap_alpha_modes}"
            )

        # (re)create downloaders
        self._downloaders[:] = [
            ImageDownloader(config["device"], self._context_buffer_usage)
            for _ in self._downloaders
        ]

    def _unconfigure(self) -> None:
        self._drop_texture()
        self._downloaders[:] = [None for _ in self._downloaders]

    def _get_current_texture(self):
        # When the texture is active right now, we could either:
        # * return the existing texture
        # * warn about it, and create a new one
        # * raise an error
        # Right now we return the existing texture, so user can retrieve it in different render passes that write to the same frame.

        if self._texture is None:
            width, height = self.physical_size
            width, height = max(width, 1), max(height, 1)

            # Note that the label 'present' is used by read_texture() to determine
            # that it can use a shared copy buffer.
            device = self._config["device"]
            self._texture = device.create_texture(
                label="present",
                size=(width, height, 1),
                format=self._config["format"],
                usage=self._config["usage"] | self._context_texture_usage,
            )

        return self._texture

    def _rc_present(self) -> None:
        if not self._texture:
            return {"method": "skip"}

        # TODO: in some cases, like offscreen backend, we don't want to skip the first frame!

        # # Get bitmap from oldest downloader
        # bitmap = None
        # downloader = self._downloaders.pop(0)
        # try:
        #     bitmap = downloader.get_bitmap()
        # finally:
        #     self._downloaders.append(downloader)

        def resolver(buf):
            bitmap = downloader.get_bitmap()  # todo: read from mapped buffer instead? or have an awaitable that returns memory
            if bitmap is None:
                return {"method": "skip"}
            else:
                return {"method": "bitmap", "format": "rgba-u8", "data": bitmap}

        # Select new downloader
        downloader = self._downloaders[-1]
        awaitable = downloader.initiate_download(self._texture).then(resolver)

        return {"method": "async", "awaitable": awaitable}

        # downloader._awaitable

    def _rc_close(self):
        self._drop_texture()


class ImageDownloader:
    """A helper class that wraps a copy-buffer to async-download an image from a texture."""

    # Some timings, to put things into perspective:
    #
    #   1 ms -> 1000 fps
    #  10 ms ->  100 fps
    #  16 ms ->   64 fps  (windows timer precision)
    #  33 ms ->   30 fps
    # 100 ms ->   10 fps
    #
    # If we sync-wait with 10ms means the fps is (way) less than 100.
    # If we render at 30 fps, and only present right after the next frame is drawn, we introduce a 33ms delay.
    # That's why we want to present asynchronously, and present the result as soon as it's available.

    def __init__(self, device, buffer_usage):
        self._device = device
        self._buffer_usage = buffer_usage
        self._buffer = None
        self._time = 0

    def initiate_download(self, texture):
        # TODO: assert not waiting

        self._parse_texture_metadata(texture)
        nbytes = self._padded_stride * self._texture_size[1]
        self._ensure_size(nbytes)
        self._copy_texture(texture)

        # Note: the buffer.map_async() method by default also does a flush, to hide a bug in wgpu-core (https://github.com/gfx-rs/wgpu/issues/5173).
        # That bug does not affect this use-case, so we use a special (undocumented :/) map-mode to prevent wgpu-py from doing its sync thing.
        self._awaitable = self._buffer.map_async("READ_NOSYNC", 0, nbytes)
        return self._awaitable

    def _parse_texture_metadata(self, texture):
        size = texture.size
        format = texture.format
        nchannels = 4  # we expect rgba or bgra

        if not format.startswith(("rgba", "bgra")):
            raise RuntimeError(f"Image present unsupported texture format {format}.")
        if "8" in format:
            bytes_per_pixel = nchannels
        elif "16" in format:
            bytes_per_pixel = nchannels * 2
        elif "32" in format:
            bytes_per_pixel = nchannels * 4
        else:
            raise RuntimeError(
                f"Image present unsupported texture format bitdepth {format}."
            )

        memoryview_type = "B"
        if "float" in format:
            memoryview_type = "e" if "16" in format else "f"
        else:
            if "32" in format:
                memoryview_type = "I"
            elif "16" in format:
                memoryview_type = "H"
            else:
                memoryview_type = "B"
            if "sint" in format:
                memoryview_type = memoryview_type.lower()

        plain_stride = bytes_per_pixel * size[0]
        extra_stride = (256 - plain_stride % 256) % 256
        padded_stride = plain_stride + extra_stride

        self._memoryview_type = memoryview_type
        self._nchannels = nchannels
        self._plain_stride = plain_stride
        self._padded_stride = padded_stride
        self._texture_size = size

    def _ensure_size(self, required_size):
        # Get buffer and decide whether we can still use it
        buffer = self._buffer
        if buffer is None:
            pass  # No buffer
        elif required_size > buffer.size:
            buffer = None  # Buffer too small
        elif required_size < 0.25 * buffer.size:
            buffer = None  # Buffer too large
        elif required_size > 0.75 * buffer.size:
            self._time = time.perf_counter()  # Size is fine
        elif time.perf_counter() - self._time > 5.0:
            buffer = None  # Too large too long

        # Create a new buffer if we need one
        if buffer is None:
            buffer_size = required_size
            buffer_size += (4096 - buffer_size % 4096) % 4096
            self._buffer = self._device.create_buffer(
                label="copy-buffer", size=buffer_size, usage=self._buffer_usage
            )

    def _copy_texture(self, texture):
        source = {
            "texture": texture,
            "mip_level": 0,
            "origin": (0, 0, 0),
        }

        destination = {
            "buffer": self._buffer,
            "offset": 0,
            "bytes_per_row": self._padded_stride,
            "rows_per_image": self._texture_size[1],
        }

        # Copy data to temp buffer
        encoder = self._device.create_command_encoder()
        encoder.copy_texture_to_buffer(source, destination, texture.size)
        command_buffer = encoder.finish()
        self._device.queue.submit([command_buffer])

    def get_bitmap(self):
        if self._buffer is None:  # todo: more explicit state tracking
            return None

        memoryview_type = self._memoryview_type
        plain_stride = self._plain_stride
        padded_stride = self._padded_stride

        nbytes = plain_stride * self._texture_size[1]
        plain_shape = (self._texture_size[1], self._texture_size[0], self._nchannels)

        # Download from mappable buffer
        # Because we use `copy=False``, we *must* copy the data.
        if self._buffer.map_state == "pending":
            self._awaitable.sync_wait()
        mapped_data = self._buffer.read_mapped(copy=False)

        # Copy the data
        if padded_stride > plain_stride:
            # Copy per row
            data = memoryview(bytearray(nbytes)).cast(mapped_data.format)
            i_start = 0
            for i in range(self._texture_size[1]):
                row = mapped_data[i * padded_stride : i * padded_stride + plain_stride]
                data[i_start : i_start + plain_stride] = row
                i_start += plain_stride
        else:
            # Copy as a whole
            data = memoryview(bytearray(mapped_data)).cast(mapped_data.format)

        # Alternative copy solution using Numpy.
        # I expected this to be faster, but does not really seem to be. Seems not worth it
        # since we technically don't depend on Numpy. Leaving here for reference.
        # import numpy as np
        # mapped_data = np.asarray(mapped_data)[:data_length]
        # data = np.empty(nbytes, dtype=mapped_data.dtype)
        # mapped_data.shape = -1, padded_stride
        # data.shape = -1, plain_stride
        # data[:] = mapped_data[:, :plain_stride]
        # data.shape = -1
        # data = memoryview(data)

        # TODO: can we pass the mapped data downstream without copying it, i.e. before unmapping the buffer? Saves another copy.

        # Since we use read_mapped(copy=False), we must unmap it *after* we've copied the data.
        self._buffer.unmap()

        # Represent as memory object to avoid numpy dependency
        # Equivalent: np.frombuffer(data, np.uint8).reshape(plain_shape)
        data = data.cast(memoryview_type, plain_shape)

        return data
