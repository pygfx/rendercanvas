import weakref


class BaseContext:
    """A context that supports rendering by generating grayscale or rgba images.

    This is inspired by JS ``get_context('bitmaprenderer')`` which returns a ``ImageBitmapRenderingContext``.
    It is a relatively simple context to implement, and provides a easy entry to using ``rendercanvas``.
    """

    def __init__(self, canvas: object, present_info: dict):
        self._canvas_ref = weakref.ref(canvas)
        self._present_info = present_info
        assert present_info["method"] in ("bitmap", "wgpu")  # internal sanity check
        self._physical_size = 0, 0

    def __repr__(self):
        return f"<rendercanvas.contexts.{self.__class__.__name__} object at {hex(id(self))}>"

    @property
    def canvas(self) -> object:
        """The associated RenderCanvas object (internally stored as a weakref)."""
        return self._canvas_ref()

    def _rc_set_physical_size(self, width: int, height: int) -> None:
        """Called by the BaseRenderCanvas to set the physical size."""
        self._physical_size = int(width), int(height)

    def _rc_present(self):
        """Called by BaseRenderCanvas to collect the result. Subclasses must implement this.

        The implementation should always return a present-result dict, which
        should have at least a field 'method'. The value of 'method' must be
        one of the methods that the canvas supports, i.e. it must be in ``present_methods``.

        * If there is nothing to present, e.g. because nothing was rendered yet:
            * return ``{"method": "skip"}`` (special case).
        * If presentation could not be done for some reason:
            * return ``{"method": "fail", "message": "xx"}`` (special case).
        * If ``present_method`` is "screen":
            * Render to screen using the info in ``present_methods['screen']``).
            * Return ``{"method", "screen"}`` as confirmation.
        * If ``present_method`` is "bitmap":
            * Return ``{"method": "bitmap", "data": data, "format": format}``.
            * 'data' is a memoryview, or something that can be converted to a memoryview, like a numpy array.
            * 'format' is the format of the bitmap, must be in ``present_methods['bitmap']['formats']`` ("rgba-u8" is always supported).
        * If ``present_method`` is something else:
            * Return ``{"method": "xx", ...}``.
            * It's the responsibility of the context to use a render method that is supported by the canvas,
              and that the appropriate arguments are supplied.
        """

        # This is a stub
        return {"method": "skip"}

    def _release(self):
        """Release resources. Called by the canvas when it's closed."""
        pass  # TODO: need this? prefix _rc_?
