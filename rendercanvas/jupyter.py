"""
Support for rendering in a Jupyter widget. Provides a widget subclass that
can be used as cell output, or embedded in an ipywidgets gui.
"""

__all__ = ["JupyterRenderCanvas", "RenderCanvas", "loop"]

import time

from .base import BaseCanvasGroup, BaseRenderCanvas
from .core.events import EventType
from .asyncio import loop

import numpy as np
from jupyter_rfb import RemoteFrameBuffer


class JupyterCanvasGroup(BaseCanvasGroup):
    pass


class JupyterRenderCanvas(BaseRenderCanvas, RemoteFrameBuffer):
    """An ipywidgets widget providing a render canvas. Needs the jupyter_rfb library."""

    _rc_canvas_group = JupyterCanvasGroup(loop)

    # Set jupyter_rfb bitmask to use the old-style events. Pygfx assumes these. We will solve this compat issue
    # when we refactor rendercanvas event objects.
    # In the new events:(event_type -> type, time_stamp -> timestamp, pixel_ratio -> ratio
    _event_compatibility = 1

    def __init__(self, *args, **kwargs):
        # This backend's default title is empty
        kwargs["title"] = kwargs.get("title", "")

        super().__init__(*args, **kwargs)

        # Internal variables
        self._last_image = None
        self._is_closed = False
        self._draw_request_time = 0
        self._rendercanvas_event_types = set(EventType)

        # The send_frame() method was added in jupyter_rfb 1.0, but it was always there as a private method,
        # so we can make it backwards compatible.
        try:
            self.send_frame  # noqa
        except AttributeError:
            self.send_frame = self._rfb_send_frame

        # Set size, title, etc.
        self._final_canvas_init()

    def get_frame(self):
        # The _time_to_draw() does the drawing and then calls
        # present_context.present(), which calls our present() method.
        # The result is either a numpy array or None, and this matches
        # with what this method is expected to return.
        self._time_to_draw()
        return None

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_info(self, present_methods):
        # We stick to the a format, because these can be easily converted to png.
        # We assume that srgb is used for  perceptive color mapping. This is the
        # common colorspace for e.g. png and jpg images. Most tools (browsers
        # included) will blit the png to screen as-is, and a screen wants colors
        # in srgb.
        if "bitmap" in present_methods:
            return {
                "method": "bitmap",
                "formats": ["rgba-u8"],
            }
        else:
            return None  # raises error

    def _rc_request_draw(self):
        self._draw_request_time = time.perf_counter()
        RemoteFrameBuffer.request_draw(self)  # -> get_frame() -> _time_to_draw()

    def _rc_request_paint(self):
        # We technically don't need to call _time_to_paint, because this backend only does bitmap mode.
        # But in case the base backend will do something in _time_to_paint later, we behave nice.
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._time_to_paint)

    def _rc_force_paint(self):
        pass

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        assert format == "rgba-u8"
        self._last_image = np.asarray(data)
        self.send_frame(self._last_image)

    def _rc_set_logical_size(self, width, height):
        self.css_width = f"{width}px"
        self.css_height = f"{height}px"

    def _rc_close(self):
        RemoteFrameBuffer.close(self)

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        self.title = title
        self.has_titlebar = bool(title)  # show titlebar when a title is set

    def _rc_set_cursor(self, cursor):
        self.cursor = cursor

    # %% Turn jupyter_rfb events into rendercanvas events

    def handle_event(self, event):
        event_type = event.get("event_type")
        if event_type == "close":
            self._is_closed = True
        elif event_type == "resize":
            logical_size = event["width"], event["height"]
            pixel_ratio = event["pixel_ratio"]
            pwidth = int(logical_size[0] * pixel_ratio)
            pheight = int(logical_size[1] * pixel_ratio)
            self._size_info.set_physical_size(pwidth, pheight, pixel_ratio)
            return

        # Only submit events that rendercanvas knows. Otherwise, if new events are added
        # to jupyter_rfb that rendercanvas does not (yet) know, rendercanvas will complain.
        if event_type in self._rendercanvas_event_types:
            self.submit_event(event)


# Make available under a name that is the same for all backends
RenderCanvas = JupyterRenderCanvas
loop = loop
