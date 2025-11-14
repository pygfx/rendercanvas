import sys

__all__ = ["BaseContext"]


class BaseContext:
    """The base class for context objects in ``rendercanvas``."""

    # Subclasses must define their present-methods that they support, in oder of preference
    present_methods = []

    def __init__(self, present_info: dict):
        self._present_info = present_info
        assert present_info["method"] in ("bitmap", "screen")  # internal sanity check
        self._size_info = {
            "physical_size": (0, 0),
            "native_pixel_ratio": 1.0,
            "canvas_pixel_ratio": 1.0,
            "total_pixel_ratio": 1.0,
            "logical_size": (0.0, 0.0),
        }
        self._object_with_physical_size = None  # to support old wgpu-py api
        self._wgpu_context = None

    def __repr__(self):
        return f"<rendercanvas.contexts.{self.__class__.__name__} object at {hex(id(self))}>"

    def _create_wgpu_py_context(self) -> object:
        """Create a wgpu.GPUCanvasContext"""
        import wgpu

        if hasattr(wgpu.gpu, "get_canvas_context"):
            # New style wgpu-py API
            self._wgpu_context = wgpu.gpu.get_canvas_context(self._present_info)
        else:
            # Old style wgpu-py API
            backend_module = wgpu.gpu.__module__
            CanvasContext = sys.modules[backend_module].GPUCanvasContext  # noqa: N806
            self._object_with_physical_size = pseudo_canvas = PseudoCanvasForWgpuPy()
            self._wgpu_context = CanvasContext(
                pseudo_canvas, {"screen": self._present_info}
            )

    def _rc_set_size_dict(self, size_info: dict) -> None:
        """Called by the BaseRenderCanvas to update the size."""
        # Note that we store the dict itself, not a copy. So our size is always up-to-date,
        # but this function is called on resize nonetheless so we can pass resizes downstream.
        self._size_info = size_info
        if self._object_with_physical_size is not None:
            self._object_with_physical_size.set_physical_size(
                *size_info["physical_size"]
            )
        elif self._wgpu_context is not None:
            self._wgpu_context.set_physical_size(*size_info["physical_size"])

    @property
    def physical_size(self) -> tuple[int, int]:
        """The physical size of the render target in integer pixels."""
        return self._size_info["physical_size"]

    @property
    def logical_size(self) -> tuple[float, float]:
        """The logical size (width, height) of the render target in float pixels.

        The logical size can be smaller than the physical size, e.g. on HiDPI
        monitors or when the user's system has the display-scale set to e.g.
        125%. The logical size can in theory also be larger than the physical
        size, but this is much less common.
        """
        return self._size_info["logical_size"]

    @property
    def pixel_ratio(self) -> float:
        """The float ratio between logical and physical pixels.

        The pixel ratio is typically 1.0 for normal screens and 2.0 for HiDPI
        screens, but fractional values are also possible if the system
        display-scale is set to e.g. 125%.
        """
        return self._size_info["total_pixel_ratio"]

    @property
    def looks_like_hidpi(self) -> bool:
        """Whether it looks like the window is on a hipdi screen.

        This is determined by checking whether the native pixel-ratio (i.e.
        the ratio reported by the canvas backend) is larger or equal dan 2.0.
        """
        return self._size_info["native_pixel_ratio"] >= 2.0

    def _rc_present(self):
        """Called by BaseRenderCanvas to collect the result. Subclasses must implement this.

        The implementation should always return a present-result dict, which
        should have at least a field 'method'.

        * If there is nothing to present, e.g. because nothing was rendered yet:
            * return ``{"method": "skip"}`` (special case).
        * If presentation could not be done for some reason:
            * return ``{"method": "fail", "message": "xx"}`` (special case).
        * If ``present_method`` is "screen":
            * Render to screen using the present info.
            * Return ``{"method", "screen"}`` as confirmation.
        * If ``present_method`` is "bitmap":
            * Return ``{"method": "bitmap", "data": data, "format": format}``.
            * 'data' is a memoryview, or something that can be converted to a memoryview, like a numpy array.
            * 'format' is the format of the bitmap, must be in ``present_info['formats']`` ("rgba-u8" is always supported).
        """

        # This is a stub
        return {"method": "skip"}

    def _rc_close(self):
        """Close context and release resources. Called by the canvas when it's closed."""
        pass


class PseudoCanvasForWgpuPy:
    def __init__(self):
        self._physical_size = 0, 0

    def set_physical_size(self, w: int, h: int):
        self._physical_size = w, h

    def get_physical_size(self) -> tuple[int, int]:
        return self._physical_size
