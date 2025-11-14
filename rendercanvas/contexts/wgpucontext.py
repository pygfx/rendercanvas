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

        # The last used texture
        self._texture = None

    def _get_capabilities(self):
        """Get dict of capabilities and cache the result."""

        import wgpu

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

    def _unconfigure(self) -> None:
        self._drop_texture()

    def _get_current_texture(self):
        # When the texture is active right now, we could either:
        # * return the existing texture
        # * warn about it, and create a new one
        # * raise an error
        # Right now we return the existing texture, so user can retrieve it in different render passes that write to the same frame.

        if self._texture is None:
            import wgpu

            width, height = self.physical_size
            width, height = max(width, 1), max(height, 1)

            # Note that the label 'present' is used by read_texture() to determine
            # that it can use a shared copy buffer.
            device = self._config["device"]
            self._texture = device.create_texture(
                label="present",
                size=(width, height, 1),
                format=self._config["format"],
                usage=self._config["usage"] | wgpu.TextureUsage.COPY_SRC,
            )

        return self._texture

    def _rc_present(self) -> None:
        if not self._texture:
            return {"method": "skip"}

        bitmap = self._get_bitmap()
        self._drop_texture()
        return {"method": "bitmap", "format": "rgba-u8", "data": bitmap}

    def _get_bitmap(self):
        texture = self._texture
        device = texture._device

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

        data = device.queue.read_texture(
            {
                "texture": texture,
                "mip_level": 0,
                "origin": (0, 0, 0),
            },
            {
                "offset": 0,
                "bytes_per_row": bytes_per_pixel * size[0],
                "rows_per_image": size[1],
            },
            size,
        )

        # Derive struct dtype from wgpu texture format
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

        # Represent as memory object to avoid numpy dependency
        # Equivalent: np.frombuffer(data, np.uint8).reshape(size[1], size[0], nchannels)

        return data.cast(memoryview_type, (size[1], size[0], nchannels))

    def _rc_close(self):
        self._drop_texture()
