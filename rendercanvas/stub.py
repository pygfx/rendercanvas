"""
A stub backend for documentation purposes.
"""

__all__ = ["RenderCanvas", "loop"]

from .base import WrapperRenderCanvas, BaseRenderCanvas, BaseLoop


class StubRenderCanvas(BaseRenderCanvas):
    """
    Backends must subclass ``BaseRenderCanvas`` and implement a set of methods prefixed with ``_rc_``.
    This class also shows a few other private methods of the base canvas class, that a backend must be aware of.
    """

    # Note that the methods below don't have docstrings, but Sphinx recovers the docstrings from the base class.

    # Just listed here so they end up in the docs

    def _final_canvas_init(self):
        return super()._final_canvas_init()

    def _process_events(self):
        return super()._process_events()

    def _draw_frame_and_present(self):
        return super()._draw_frame_and_present()

    # Must be implemented by subclasses.

    def _rc_get_loop(self):
        return None

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_methods(self):
        raise NotImplementedError()

    def _rc_request_draw(self):
        pass

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        raise NotImplementedError()

    def _rc_get_physical_size(self):
        raise NotImplementedError()

    def _rc_get_logical_size(self):
        raise NotImplementedError()

    def _rc_get_pixel_ratio(self):
        raise NotImplementedError()

    def _rc_set_logical_size(self, width, height):
        pass

    def _rc_close(self):
        pass

    def _rc_get_closed(self):
        return False

    def _rc_set_title(self, title):
        pass


class ToplevelRenderCanvas(WrapperRenderCanvas):
    """
    Some backends require a toplevel wrapper. These can inherit from ``WrapperRenderCanvas``.
    These have to instantiate the wrapped canvas and set it as ``_subwidget``. Implementations
    are typically very small.
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)

        self._subwidget = StubRenderCanvas(self, **kwargs)


class StubLoop(BaseLoop):
    """
    Backends must subclass ``BaseLoop`` and implement a set of methods prefixed with ``_rc__``.
    """

    def _rc_run(self):
        raise NotImplementedError()

    def _rc_stop(self):
        raise NotImplementedError()

    def _rc_call_soon(self, callback, *args):
        self.call_later(0, callback, *args)


# Make available under a common name
RenderCanvas = StubRenderCanvas
loop = StubLoop()
run = loop.run
