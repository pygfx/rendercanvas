"""
Support for rendering in a Jupyter widget. Provides a widget subclass that
can be used as cell output, or embedded in an ipywidgets gui.
"""

__all__ = ["JupyterRenderCanvas", "RenderCanvas", "loop"]

import time

from .base import BaseCanvasGroup, BaseRenderCanvas
from ._events import EventType
from .asyncio import loop

import numpy as np
from jupyter_rfb import RemoteFrameBuffer


class JupyterCanvasGroup(BaseCanvasGroup):
    pass


class JupyterRenderCanvas(BaseRenderCanvas, RemoteFrameBuffer):
    """An ipywidgets widget providing a render canvas. Needs the jupyter_rfb library."""

    _rc_canvas_group = JupyterCanvasGroup(loop)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Internal variables
        self._last_image = None
        self._pixel_ratio = 1
        self._logical_size = 0, 0
        self._is_closed = False
        self._draw_request_time = 0
        self._rendercanvas_event_types = set(EventType)

        # Set size, title, etc.
        self._final_canvas_init()

    def get_frame(self):
        # The _draw_frame_and_present() does the drawing and then calls
        # present_context.present(), which calls our present() method.
        # The result is either a numpy array or None, and this matches
        # with what this method is expected to return.
        self._draw_frame_and_present()
        return self._last_image

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_methods(self):
        # We stick to the two common formats, because these can be easily converted to png
        # We assyme that srgb is used for  perceptive color mapping. This is the
        # common colorspace for e.g. png and jpg images. Most tools (browsers
        # included) will blit the png to screen as-is, and a screen wants colors
        # in srgb.
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_request_draw(self):
        self._draw_request_time = time.perf_counter()
        RemoteFrameBuffer.request_draw(self)

    def _rc_force_draw(self):
        # A bit hacky to use the internals of jupyter_rfb this way.
        # This pushes frames to the browser as long as the websocket
        # buffer permits it. It works!
        # But a better way would be `await canvas.wait_draw()`.
        # Todo: would also be nice if jupyter_rfb had a public api for this.
        array = self.get_frame()
        if array is not None:
            self._rfb_send_frame(array)

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # Convert memoryview to ndarray (no copy)
        assert format == "rgba-u8"
        self._last_image = np.frombuffer(data, np.uint8).reshape(data.shape)

    def _rc_get_physical_size(self):
        return int(self._logical_size[0] * self._pixel_ratio), int(
            self._logical_size[1] * self._pixel_ratio
        )

    def _rc_get_logical_size(self):
        return self._logical_size

    def _rc_get_pixel_ratio(self):
        return self._pixel_ratio

    def _rc_set_logical_size(self, width, height):
        self._logical_size = width, height
        self.css_width = f"{width}px"
        self.css_height = f"{height}px"

    def _rc_close(self):
        RemoteFrameBuffer.close(self)

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        pass  # not supported yet

    def _rc_set_cursor(self, cursor):
        self.cursor = cursor

    # %% Turn jupyter_rfb events into rendercanvas events

    def handle_event(self, event):
        event_type = event.get("event_type")
        if event_type == "close":
            self._is_closed = True
        elif event_type == "resize":
            self._pixel_ratio = event["pixel_ratio"]
            self._logical_size = event["width"], event["height"]

        # Only submit events that rendercanvas known. Otherwise, if new events are added
        # to jupyter_rfb that rendercanvas does not (yet) know, rendercanvas will complain.
        if event_type in self._rendercanvas_event_types:
            self.submit_event(event)


# Make available under a name that is the same for all backends
RenderCanvas = JupyterRenderCanvas
loop = loop
