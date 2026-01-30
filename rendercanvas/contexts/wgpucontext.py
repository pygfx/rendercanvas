import time
from typing import Sequence

import numpy as np

from .basecontext import BaseContext
from .._coreutils import logger, log_exception


__all__ = ["WgpuContext", "WgpuContextToBitmap", "WgpuContextToScreen"]


class WgpuContext(BaseContext):
    """A context that exposes an API that provides a GPU texture to render to.

    This is inspired by JS' ``GPUCanvasContext``, and the more performant
    approach for rendering to a ``rendercanvas``. Use
    ``canvas.get_wgpu_context()`` to create a ``WgpuContext``.
    """

    # Note:  instantiating this class creates an instance of a sub-class, dedicated to the present method of the canvas.

    present_methods = ["screen", "bitmap"]  # in order of preference

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

    def _rc_present(self, *, force_sync: bool = False) -> dict:
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

    def _rc_present(self, *, force_sync: bool = False) -> dict:
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
        # We have a single texture (not a ring of textures), because copying the
        # contents to a download-buffer is near-instant.
        self._texture = None

        # Object to download the rendered images to the CPU/RAM. Mapping the
        # buffers to RAM takes time, and we want to wait for this
        # asynchronously. We could have a ring of buffers to allow multiple
        # concurrent downloads (start downloading the next frame before the
        # previous is done downloading), but from what we've observed, this does
        # not improve the FPS. It does costs memory though, and can actually
        # strain the GPU more.
        self._downloader = None

    def _get_capabilities(self):
        """Get dict of capabilities and cache the result."""

        import wgpu

        # Earlier versions wgpu may not be optimal, or may not even work.
        if wgpu.version_info < (0, 27):
            raise RuntimeError(
                f"The version of wgpu {wgpu.__version__!r} is too old to support bitmap-present of the current version of rendercanvas. Please update wgpu-py."
            )
        if wgpu.version_info < (1, 29):
            logger.warning(
                f"The version of wgpu is {wgpu.__version__!r}, you probably want to upgrade to at least 0.29 to benefit from performance upgrades for async-bitmap-present."
            )

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

        # (re)create downloader
        self._downloader = ImageDownloader(config["device"], self._context_buffer_usage)

    def _unconfigure(self) -> None:
        self._drop_texture()
        self._downloader = None

    def _get_current_texture(self):
        # When the texture is active right now, we could either:
        # * return the existing texture
        # * warn about it, and create a new one
        # * raise an error
        # Right now we return the existing texture, so user can retrieve it in different render passes that write to the same frame.

        width, height = self.physical_size
        need_texture_size = max(width, 1), max(height, 1), 1

        if self._texture is None or self._texture.size != need_texture_size:
            # Note that the label 'present' is used by read_texture() to determine
            # that it can use a shared copy buffer.
            device = self._config["device"]
            self._texture = device.create_texture(
                label="present",
                size=need_texture_size,
                format=self._config["format"],
                usage=self._config["usage"] | self._context_texture_usage,
            )

        return self._texture

    def _rc_present(self, *, force_sync: bool = False) -> dict:
        if not self._texture:
            return {"method": "skip"}
        if force_sync:
            return self._downloader.do_sync_download(
                self._texture, self._present_params
            )
        else:
            awaitable = self._downloader.initiate_download(
                self._texture, self._present_params
            )
            return {"method": "async", "awaitable": awaitable}

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
        self._awaitable = None
        self._action = None
        self._time_since_size_ok = 0

    def _clear_pending_download(self):
        if self._action is not None:
            self._action.cancel()
        if self._awaitable is not None:
            if self._buffer.map_state == "pending":
                self._awaitable.sync_wait()
            if self._buffer.map_state == "mapped":
                self._buffer.unmap()

    def _get_awaitable_for_download(self, texture, present_params=None):
        # First clear any pending downloads.
        # This covers cases when switching between ``force_draw()`` and normal rendering.
        self._clear_pending_download()

        # Create new action object and make sure that the buffer is the correct size
        action = AsyncImageDownloadAction(texture, present_params)
        stride, nbytes = action.stride, action.nbytes
        self._ensure_buffer_size(nbytes)
        action.set_buffer(self._buffer)

        # Initiate copying the texture to the buffer
        self._queue_command_to_copy_texture(texture, stride)

        # Note: the buffer.map_async() method by default also does a flush, to hide a bug in wgpu-core (https://github.com/gfx-rs/wgpu/issues/5173).
        # That bug does not affect this use-case, so we use a special (undocumented :/) map-mode to prevent wgpu-py from doing its sync thing.
        awaitable = self._buffer.map_async("READ_NOSYNC", 0, nbytes)

        self._action = action
        self._awaitable = awaitable

    def initiate_download(self, texture, present_params):
        self._get_awaitable_for_download(texture, present_params)
        self._awaitable.then(self._action.resolve)
        return self._action

    def do_sync_download(self, texture, present_params):
        # Start a fresh download
        self._get_awaitable_for_download(texture)

        # With a fresh action
        self._action.cancel()
        action = AsyncImageDownloadAction(texture, present_params)
        action.set_buffer(self._buffer)

        # Async-wait, then resolve
        self._awaitable.sync_wait()
        result = action.resolve()
        assert result is not None
        return result

    def _ensure_buffer_size(self, required_size):
        # Get buffer and decide whether we can still use it
        buffer = self._buffer
        if buffer is None:
            pass  # No buffer
        elif required_size > buffer.size:
            buffer = None  # Buffer too small
        elif required_size < 0.50 * buffer.size:
            buffer = None  # Buffer more than twice as large as needed
        elif required_size > 0.85 * buffer.size:
            self._time_since_size_ok = time.perf_counter()  # Size is fine
        elif time.perf_counter() - self._time_since_size_ok > 5.0:
            buffer = None  # Too large too long

        # Create a new buffer if we need one
        if buffer is None:
            buffer_size = required_size
            buffer_size += (4096 - buffer_size % 4096) % 4096
            self._buffer = self._device.create_buffer(
                label="copy-buffer", size=buffer_size, usage=self._buffer_usage
            )

    def _queue_command_to_copy_texture(self, texture, stride):
        source = {
            "texture": texture,
            "mip_level": 0,
            "origin": (0, 0, 0),
        }

        destination = {
            "buffer": self._buffer,
            "offset": 0,
            "bytes_per_row": stride,
            "rows_per_image": texture.size[1],
        }

        # Copy data to temp buffer
        encoder = self._device.create_command_encoder()
        encoder.copy_texture_to_buffer(source, destination, texture.size)
        command_buffer = encoder.finish()
        self._device.queue.submit([command_buffer])


class AsyncImageDownloadAction:
    """Single-use image download helper object that has a 'then' method (i.e. follows the awaitable pattern a bit)."""

    def __init__(self, texture, present_params):
        self._callbacks = []
        self._present_params = present_params
        # The image is stored in wgpu buffer, which needs to get mapped before we can read the bitmap
        self._buffer = None
        # We examine the texture to understand what the bitmap will look like
        self._parse_texture_metadata(texture)

    def set_buffer(self, buffer):
        self._buffer = buffer

    def is_pending(self):
        return self._buffer is not None

    def cancel(self):
        self._buffer = None

    def then(self, callback):
        self._callbacks.append(callback)

    def resolve(self, _=None):
        # Use log_exception because this is used in a GPUPromise.then()
        with log_exception("Error in AsyncImageDownloadAction.resolve:"):
            buffer = self._buffer
            if buffer is None:
                return
            self._buffer = None

            try:
                data = self._get_bitmap(buffer)
            finally:
                buffer.unmap()
            result = {
                "method": "bitmap",
                "format": "rgba-u8",
                "data": data,
            }
            for callback in self._callbacks:
                callback(result)
            self._callbacks = []
            return result

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

        dtype = "uint8"
        if "float" in format:
            dtype = "float16" if "16" in format else "float32"
        else:
            dtype = "int" if "sint" in format else "uint"
            if "32" in format:
                dtype += "32"
            elif "16" in format:
                dtype += "16"
            else:
                dtype += "8"

        plain_stride = bytes_per_pixel * size[0]
        extra_stride = (256 - plain_stride % 256) % 256
        padded_stride = plain_stride + extra_stride

        self._dtype = dtype
        self._nchannels = nchannels
        self._padded_stride = padded_stride
        self._texture_size = size

        # For ImageDownloader
        self.stride = padded_stride
        self.nbytes = padded_stride * size[1]

    def _get_bitmap(self, buffer):
        dtype = self._dtype
        nchannels = self._nchannels
        padded_stride = self._padded_stride
        size = self._texture_size
        plain_shape = (size[1], size[0], nchannels)
        present_params = self._present_params or {}

        # Read bitmap from mapped buffer. Note that the data is mapped, so we
        # *must* copy the data before unmapping the buffer. By applying any
        # processing *here* while the buffer is mapped, we can avoid one
        # data-copy. E.g. we can create a numpy view on the data and then copy
        # *that*, rather than copying the raw data and then making another copy
        # to make it contiguous.

        # Note that this code here is the main reason for having numpy as a
        # dependency: with just memoryview (no numpy), we cannot create a
        # strided array, and we cannot copy strided data without iterating over
        # all rows.

        # Get array
        if buffer.map_state == "pending":
            raise RuntimeError("Buffer state is 'pending' in get_bitmap()")
        mapped_data = buffer.read_mapped(copy=False)

        # Determine how to process it.
        submethod = present_params.get("submethod", "contiguous-array")

        # Triage. AK: I implemented some stubs, primarily as an indication of
        # how I see this scaling out to more sophisticated methods. Here we can
        # add diff images, gpu-based pseudo-jpeg, etc.

        if submethod == "contiguous-array":
            # This is the default.

            # Wrap the data in a (possible strided) numpy array
            data = np.asarray(mapped_data, dtype=dtype).reshape(
                plain_shape[0], padded_stride // nchannels, nchannels
            )
            # Make a copy, making it contiguous.
            data = data[:, : plain_shape[1], :].copy()

        elif submethod == "strided-array":
            # In some cases it could be beneficial to use the data that has 256-byte aligned rows,
            # e.g. when the data must be uploaded to a GPU again.

            # Wrap the data in a (possible strided) numpy array
            data = np.asarray(mapped_data, dtype=dtype).reshape(
                plain_shape[0], padded_stride // nchannels, nchannels
            )
            # Make a copy of the strided data, and create a view on that.
            data = data.copy()[:, : plain_shape[1], :]

        elif submethod == "jpeg":
            # For now just a stub, activate in the upcoming Anywidget backend

            import simplejpeg

            # Get strided array view
            data = np.asarray(mapped_data, dtype=dtype).reshape(
                plain_shape[0], padded_stride // nchannels, nchannels
            )
            data = data[:, : plain_shape[1], :]

            # Encode jpeg on the mapped data
            data = simplejpeg.encode_jpeg(
                data,
                present_params.get("quality", 85),
                "rgba",
                present_params.get("subsampling", "420"),
                fastdct=True,
            )

        elif submethod == "png":
            # For cases where lossless compression is needed. We can easily do this in pure Python, I have code for that somewhere.
            raise NotImplementedError("present submethod 'png'")

        elif submethod == "gpu-jpeg":
            # jpeg encoding on the GPU, produces pseudo-jpeg that needs to be decoded with a special shader at the receiving end.
            # This implementation is more work, because we need to setup a GPU pipeline with multiple compute shaders.
            raise NotImplementedError("present submethod 'gpu-jpeg'")

        else:
            raise RuntimeError(f"Unknown present submethod {submethod!r}")

        return data
