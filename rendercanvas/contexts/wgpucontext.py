from .basecontext import BaseRenderCanvasContext

import wgpu

# TODO: A weird thing about this is that I am replicatinh wgpu._classes.GPUCanvasContext, which feels rather strange indeed. Also in terms of keeping the API up to date??


class WgpuRenderCanvasContext(BaseRenderCanvasContext):
    """A context that to render wgpu."""

    # todo: use __new__ and produce different classes as to connect context to the present method?
    def __init__(self, canvas, present_methods):
        super().__init__(canvas, present_methods)
        self._present_method = "screen" if "screen" in present_methods else "bitmap"

        if self._present_method == "screen":
            # todo: pass all present methods?
            self._real_canvas_context = wgpu.rendercanvas_context_hook(
                canvas, present_methods
            )
        else:
            pass  # we fake it.

        self._capabilities = None
        self._config = None

    def _get_capabilities(self):
        """Get dict of capabilities and cache the result."""
        if self._capabilities is None:
            self._capabilities = {}
            # Query format capabilities from the info provided by the canvas
            formats = []
            for format in self._present_methods["bitmap"]["formats"]:
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
                if wgpu_format_srgb in enums.TextureFormat:
                    formats.append(wgpu_format_srgb)
                formats.append(wgpu_format)
            # Assume alpha modes for now
            alpha_modes = [enums.CanvasAlphaMode.opaque]
            # Build capabilitied dict
            self._capabilities = {
                "formats": formats,
                "usages": 0xFF,
                "alpha_modes": alpha_modes,
            }
            # Derived defaults
            if "view_formats" not in self._capabilities:
                self._capabilities["view_formats"] = self._capabilities["formats"]

        return self._capabilities

    def get_preferred_format(self, adapter: GPUAdapter) -> enums.TextureFormatEnum:
        """Get the preferred surface texture format."""
        capabilities = self._get_capabilities()
        formats = capabilities["formats"]
        return formats[0] if formats else "bgra8-unorm"

    def get_configuration(self) -> dict:
        """Get the current configuration (or None if the context is not yet configured)."""
        return self._config

    def configure(
        self,
        *,
        device: GPUDevice,
        format: enums.TextureFormatEnum,
        usage: flags.TextureUsageFlags = 0x10,
        view_formats: Sequence[enums.TextureFormatEnum] = (),
        color_space: str = "srgb",
        tone_mapping: structs.CanvasToneMappingStruct | None = None,
        alpha_mode: enums.CanvasAlphaModeEnum = "opaque",
    ) -> None:
        """Configures the presentation context for the associated canvas.
        Destroys any textures produced with a previous configuration.
        This clears the drawing buffer to transparent black.

        Arguments:
            device (WgpuDevice): The GPU device object to create compatible textures for.
            format (enums.TextureFormat): The format that textures returned by
                ``get_current_texture()`` will have. Must be one of the supported context
                formats. Can be ``None`` to use the canvas' preferred format.
            usage (flags.TextureUsage): Default ``TextureUsage.OUTPUT_ATTACHMENT``.
            view_formats (list[enums.TextureFormat]): The formats that views created
                from textures returned by ``get_current_texture()`` may use.
            color_space (PredefinedColorSpace): The color space that values written
                into textures returned by ``get_current_texture()`` should be displayed with.
                Default "srgb". Not yet supported.
            tone_mapping (enums.CanvasToneMappingMode): Not yet supported.
            alpha_mode (structs.CanvasAlphaMode): Determines the effect that alpha values
                will have on the content of textures returned by ``get_current_texture()``
                when read, displayed, or used as an image source. Default "opaque".
        """
        # Check types
        tone_mapping = {} if tone_mapping is None else tone_mapping

        if not isinstance(device, GPUDevice):
            raise TypeError("Given device is not a device.")

        if format is None:
            format = self.get_preferred_format(device.adapter)
        if format not in enums.TextureFormat:
            raise ValueError(f"Configure: format {format} not in {enums.TextureFormat}")

        if not isinstance(usage, int):
            usage = str_flag_to_int(flags.TextureUsage, usage)

        color_space  # noqa - not really supported, just assume srgb for now
        tone_mapping  # noqa - not supported yet

        # Allow more than the IDL modes, see https://github.com/pygfx/wgpu-py/pull/719
        extra_alpha_modes = ["auto", "unpremultiplied", "inherit"]  # from webgpu.h
        all_alpha_modes = [*enums.CanvasAlphaMode, *extra_alpha_modes]
        if alpha_mode not in all_alpha_modes:
            raise ValueError(
                f"Configure: alpha_mode {alpha_mode} not in {enums.CanvasAlphaMode}"
            )

        # Check against capabilities

        capabilities = self._get_capabilities(device.adapter)

        if format not in capabilities["formats"]:
            raise ValueError(
                f"Configure: unsupported texture format: {format} not in {capabilities['formats']}"
            )

        if not usage & capabilities["usages"]:
            raise ValueError(
                f"Configure: unsupported texture usage: {usage} not in {capabilities['usages']}"
            )

        for view_format in view_formats:
            if view_format not in capabilities["view_formats"]:
                raise ValueError(
                    f"Configure: unsupported view format: {view_format} not in {capabilities['view_formats']}"
                )

        if alpha_mode not in capabilities["alpha_modes"]:
            raise ValueError(
                f"Configure: unsupported alpha-mode: {alpha_mode} not in {capabilities['alpha_modes']}"
            )

        # Store

        self._config = {
            "device": device,
            "format": format,
            "usage": usage,
            "view_formats": view_formats,
            "color_space": color_space,
            "tone_mapping": tone_mapping,
            "alpha_mode": alpha_mode,
        }

        if self._present_method == "screen":
            self._configure_screen(**self._config)

    def unconfigure(self) -> None:
        """Removes the presentation context configuration.
        Destroys any textures produced while configured.
        """
        if self._present_method == "screen":
            self._unconfigure_screen()
        self._config = None
        self._drop_texture()

    def get_current_texture(self) -> GPUTexture:
        pass

    def _rc_present(self):
        pass
