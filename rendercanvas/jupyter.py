"""
Support for rendering in a Jupyter widget. Provides a widget subclass that
can be used as cell output, or embedded in an ipywidgets gui.
"""

__all__ = ["RenderCanvas", "loop"]

import time
import weakref

from .base import BaseRenderCanvas
from .asyncio import AsyncioLoop

import numpy as np
from jupyter_rfb import RemoteFrameBuffer
from IPython.display import display


class JupyterRenderCanvas(BaseRenderCanvas, RemoteFrameBuffer):
    """An ipywidgets widget providing a render canvas. Needs the jupyter_rfb library."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Internal variables
        self._last_image = None
        self._pixel_ratio = 1
        self._logical_size = 0, 0
        self._is_closed = False
        self._draw_request_time = 0

        # Register so this can be display'ed when run() is called
        loop._pending_jupyter_canvases.append(weakref.ref(self))

        # Set size, title, etc.
        self._final_canvas_init()

    def get_frame(self):
        # The _draw_frame_and_present() does the drawing and then calls
        # present_context.present(), which calls our present() method.
        # The result is either a numpy array or None, and this matches
        # with what this method is expected to return.

        # When we had to wait relatively long for the drawn to be made,
        # we do another round processing events, to minimize the perceived lag.
        # We only do this when the delay is significant, so that under good
        # circumstances, the scheduling behaves the same as for other canvases.
        if time.perf_counter() - self._draw_request_time > 0.02:
            self._process_events()

        self._draw_frame_and_present()
        return self._last_image

    # %% Methods to implement RenderCanvas

    def _rc_get_loop(self):
        return loop

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
        self.css_width = f"{width}px"
        self.css_height = f"{height}px"

    def _rc_close(self):
        RemoteFrameBuffer.close(self)

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        pass  # not supported yet

    # %% Turn jupyter_rfb events into rendercanvas events

    def handle_event(self, event):
        event_type = event.get("event_type")
        if event_type == "close":
            self._is_closed = True
        elif event_type == "resize":
            self._pixel_ratio = event["pixel_ratio"]
            self._logical_size = event["width"], event["height"]

        self.submit_event(event)


# Make available under a name that is the same for all backends
RenderCanvas = JupyterRenderCanvas


class JupyterAsyncioLoop(AsyncioLoop):
    def __init__(self):
        super().__init__()
        self._pending_jupyter_canvases = []

    def _rc_gui_poll(self):
        pass  # Jupyter is running in a separate process :)

    def run(self):
        # Show all widgets that have been created so far.
        # No need to actually start an event loop, since Jupyter already runs it.
        canvases = [r() for r in self._pending_jupyter_canvases]
        self._pending_jupyter_canvases.clear()
        for w in canvases:
            if w and not w.get_closed():
                display(w)


loop = JupyterAsyncioLoop()
run = loop.run
