"""
A stub backend for documentation purposes.
"""

__all__ = ["RenderCanvas", "StubLoop", "StubRenderCanvas", "loop"]

from .base import BaseCanvasGroup, WrapperRenderCanvas, BaseRenderCanvas, BaseLoop


class StubLoop(BaseLoop):
    """
    The ``Loop`` represents the event-loop that drives the rendering and events.

    Some backends will provide a corresponding loop (like qt and ws). Other backends may use
    existing loops (like glfw and jupyter). And then there are loop-backends that only implement
    a loop (e.g. asyncio or trio).

    Backends must subclass ``BaseLoop`` and implement a set of methods prefixed with ``_rc_``.
    """

    def _rc_init(self):
        raise NotImplementedError()

    def _rc_run(self):
        raise NotImplementedError()

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        raise NotImplementedError()

    def _rc_add_task(self, async_func, name):
        raise NotImplementedError()

    def _rc_call_later(self, delay, callback):
        raise NotImplementedError()


loop = StubLoop()


class StubCanvasGroup(BaseCanvasGroup):
    """
    The ``CanvasGroup`` representss a group of canvas objects from the same class, that share a loop.

    The initial/default loop is passed when the ``CanvasGroup`` is instantiated.

    Backends can subclass ``BaseCanvasGroup`` and set an instance at their ``RenderCanvas._rc_canvas_group``.
    It can also be omitted for canvases that don't need to run in a loop. Note that this class is only
    for internal use, mainly to connect canvases to a loop; it is not public API.

    The subclassing is only really done so the group has a distinguishable name. Though we may add ``_rc_`` methods
    to this class in the future.
    """


class StubRenderCanvas(BaseRenderCanvas):
    """
    The ``RenderCanvas`` represents the canvas to render to.

    Backends must subclass ``BaseRenderCanvas`` and implement a set of methods prefixed with ``_rc_``.
    This class also shows a few other private methods of the base canvas class, that a backend must be aware of.
    """

    # Note that the methods below don't have docstrings, but Sphinx recovers the docstrings from the base class.

    # Just listed here so they end up in the docs

    def _final_canvas_init(self):
        return super()._final_canvas_init()

    def _set_size_info(self, physical_size, pixel_ratio):
        return super()._set_size_info(physical_size, pixel_ratio)

    def _process_events(self):
        return super()._process_events()

    def _draw_frame_and_present(self):
        return super()._draw_frame_and_present()

    # Must be implemented by subclasses.

    _rc_canvas_group = StubCanvasGroup(loop)

    def _rc_gui_poll(self):
        raise NotImplementedError()

    def _rc_get_present_methods(self):
        raise NotImplementedError()

    def _rc_request_draw(self):
        pass

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        raise NotImplementedError()

    def _rc_set_logical_size(self, width, height):
        pass

    def _rc_close(self):
        pass

    def _rc_get_closed(self):
        return False

    def _rc_set_title(self, title):
        pass

    def _rc_set_cursor(self, cursor):
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


# Make available under a common name
RenderCanvas = StubRenderCanvas
loop = StubLoop()
