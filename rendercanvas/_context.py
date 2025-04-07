"""
A stub context implementation for documentation purposes.
It does actually work, but presents nothing.
"""

import weakref


def rendercanvas_context_hook(canvas, present_methods):
    """Hook function to allow ``rendercanvas`` to detect your context implementation.

    If you make a function with this name available in the module ``your.module``,
    ``rendercanvas`` will detect and call this function in order to obtain the canvas object.
    That way, anyone can use ``canvas.get_context("your.module")`` to use your context.
    The arguments are the same as for ``ContextInterface``.
    """
    return ContextInterface(canvas, present_methods)


class ContextInterface:
    """The interface that a context must implement, to be usable with a ``RenderCanvas``.

    Arguments:
        canvas (BaseRenderCanvas): the canvas to render to.
        present_methods (dict): The supported present methods of the canvas.

    The ``present_methods`` dict has a field for each supported present-method. A
    canvas must support either "screen" or "bitmap". It may support both, as well as
    additional (specialized) present methods. Below we list the common methods and
    what fields the subdicts have.

    * Render method "screen":
        * "window": the native window id.
        * "display": the native display id (Linux only).
        * "platform": to determine between "x11" and "wayland" (Linux only).
    * Render method "bitmap":
        * "formats": a list of supported formats. It should always include "rgba-u8".
          Other options can be be "i-u8" (intensity/grayscale), "i-f32", "bgra-u8", "rgba-u16", etc.

    """

    def __init__(self, canvas, present_methods):
        self._canvas_ref = weakref.ref(canvas)
        self._present_methods = present_methods

    @property
    def canvas(self):
        """The associated canvas object. Internally, this should preferably be stored using a weakref."""
        return self._canvas_ref()

    def present(self):
        """Present the result to the canvas.

        This is called by the canvas, and should not be called by user-code.

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
        pass
