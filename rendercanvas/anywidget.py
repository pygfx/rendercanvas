"""
A backend based on anywidget, supporting canvases inside a large variety of notebooks and similar browser-like environments.
"""

__all__ = ["AnywidgetRenderCanvas", "RenderCanvas", "loop"]

import time
import asyncio
from base64 import encodebytes
from importlib.resources import files as resource_files

from .base import BaseCanvasGroup, BaseRenderCanvas, logger
from .asyncio import loop
from .core.encoders import encode_array, CAN_JPEG

import numpy as np
import anywidget
from traitlets import Bool, Dict, Int, Unicode


def _load_js_and_css():
    js = ""
    for fname in ["renderview.js", "renderview-anywidget.js"]:
        js_path = resource_files("rendercanvas.core").joinpath(fname)
        js += js_path.read_text() + "\n\n"

    css_path = resource_files("rendercanvas.core").joinpath("renderview.css")

    return js, css_path.read_text()


JS, CSS = _load_js_and_css()


class AnywidgetCanvasGroup(BaseCanvasGroup):
    pass


class AnywidgetRenderCanvas(BaseRenderCanvas, anywidget.AnyWidget):
    """An anywidget canvas to use in notebooks (e.g. jupyter, marimo, VSCode, etc.).

    This is an AnyWidget subclass, so you can easily combine it with other widgets.
    """

    # This class uses some '_rfb_' prefixes to avoid name clashes with super and sub classes.
    # This specific prefix was inherited from jupyter_rfb, and we decided to keep it as is.

    _rc_canvas_group = AnywidgetCanvasGroup(loop)

    _esm = JS
    _css = CSS

    # Client -> server
    _frame_feedback = Dict({}).tag(sync=True)
    _has_visible_views = Bool(False).tag(sync=True)
    # Server -> client
    _css_width = Unicode("500px").tag(sync=True)
    _css_height = Unicode("300px").tag(sync=True)
    _resizable = Bool(True).tag(sync=True)
    _has_titlebar = Bool(False).tag(sync=True)
    _title = Unicode("").tag(sync=True)
    _cursor = Unicode("default").tag(sync=True)
    # Server only
    _max_buffered_frames = Int(2, min=1)
    _quality = Int(80, min=1, max=100)

    def __init__(self, *args, **kwargs):
        # This backend's default title is empty
        kwargs["title"] = kwargs.get("title", "")

        super().__init__(*args, **kwargs)

        self._is_closed = False

        self._rfb_draw_requested = False
        self._rfb_frame_index = 0
        self._rfb_last_confirmed_index = 0
        self._rfb_warned_png = False
        self._rfb_lossless_draw_info = None
        self._use_websocket = True  # Could be a prop, private for now

        self.reset_stats()
        self.on_msg(self._rfb_handle_msg)
        self.observe(
            self._rfb_schedule_maybe_draw,
            names=["_frame_feedback", "_has_visible_views"],
        )

        # Set size, title, etc.
        self._final_canvas_init()

    def _rfb_handle_msg(self, widget, content, buffers):
        """Receive custom messages and filter our events."""
        event_type = content.get("type")

        if event_type is not None:
            event = content

            if event_type == "resize":
                self._last_event = event
                self._size_info.set_physical_size(
                    event["pwidth"], event["pheight"], event["ratio"]
                )
            elif event_type == "close":
                self.close()
            else:
                # Compatibility between new renderview event spec and current rendercanvas/pygfx events
                event["event_type"] = event.pop("type")
                event["time_stamp"] = event.pop("timestamp")
                # Turn lists into tuples (js/json does not have tuples)
                if "buttons" in event:
                    event["buttons"] = tuple(event["buttons"])
                if "modifiers" in event:
                    event["modifiers"] = tuple(event["modifiers"])
                self.submit_event(event)

    def _rfb_schedule_maybe_draw(self, *args):
        """Schedule _maybe_draw() to be called in a fresh event loop iteration."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.call_soon(self._rfb_maybe_draw)

    def _rfb_maybe_draw(self):
        """Perform a draw, if we can and should."""
        feedback = self._frame_feedback
        # Update stats
        self._rfb_update_stats(feedback)
        # Determine whether we should perform a draw: a draw was requested, and
        # the client is ready for a new frame, and the client widget is visible.
        frames_in_flight = self._rfb_frame_index - feedback.get("index", 0)
        should_draw = (
            self._rfb_draw_requested
            and frames_in_flight < self._max_buffered_frames
            and self._has_visible_views
        )
        # Do the draw if we should.
        if should_draw:
            self._rfb_draw_requested = False
            self._time_to_draw()  # -> _rc_present_bitmap -> _rfb_send_frame

    def _rfb_schedule_lossless_draw(self, array, delay=0.3):
        self._rfb_cancel_lossless_draw()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(delay, self._rfb_lossless_draw)
        self._rfb_lossless_draw_info = array, handle

    def _rfb_cancel_lossless_draw(self):
        if self._rfb_lossless_draw_info:
            _, handle = self._rfb_lossless_draw_info
            self._rfb_lossless_draw_info = None
            handle.cancel()

    def _rfb_lossless_draw(self):
        array, _ = self._rfb_lossless_draw_info
        self._rfb_send_frame(array, True)

    def _rfb_send_frame(self, array, is_lossless_redraw=False):
        """Actually send a frame over to the client."""
        # For considerations about performance,
        # see https://github.com/vispy/jupyter_rfb/issues/3

        quality = 100 if is_lossless_redraw else self._quality

        self._rfb_frame_index += 1
        timestamp = time.time()

        # Turn array into a based64-encoded JPEG or PNG
        t1 = time.perf_counter()
        mimetype, data = encode_array(array, quality)
        if self._use_websocket:
            datas = [data]
            data_b64 = None
        else:
            datas = []
            data_b64 = f"data:{mimetype};base64," + encodebytes(data).decode()
        t2 = time.perf_counter()

        if "jpeg" in mimetype:
            self._rfb_schedule_lossless_draw(array)
        else:
            self._rfb_cancel_lossless_draw()
            # Issue png warning?
            if quality < 100 and not CAN_JPEG and not self._rfb_warned_png:
                self._rfb_warned_png = True
                logger.warning(
                    "No JPEG encoder found, using PNG instead. Install simplejpeg for better performance."
                )

        if is_lossless_redraw:
            # No stats, also not on the confirmation of this frame
            self._rfb_last_confirmed_index = self._rfb_frame_index
        else:
            # Stats
            self._rfb_stats["img_encoding_sum"] += t2 - t1
            self._rfb_stats["sent_frames"] += 1
            if self._rfb_stats["start_time"] <= 0:  # Start measuring
                self._rfb_stats["start_time"] = timestamp
                self._rfb_last_confirmed_index = self._rfb_frame_index - 1

        # Compose message and send
        msg = dict(
            type="framebufferdata",
            mimetype=mimetype,
            data_b64=data_b64,
            index=self._rfb_frame_index,
            timestamp=timestamp,
        )
        self.send(msg, datas)

    # ----- related to stats

    def reset_stats(self):
        """Restart measuring statistics from the next sent frame."""
        self._rfb_stats = {
            "start_time": 0,
            "last_time": 1,
            "sent_frames": 0,
            "confirmed_frames": 0,
            "roundtrip_count": 0,
            "roundtrip_sum": 0,
            "delivery_sum": 0,
            "img_encoding_sum": 0,
        }

    def get_stats(self):
        """Get the current stats since the last time ``.reset_stats()`` was called.

        Stats is a dict with the following fields:

        * *sent_frames*: the number of frames sent.
        * *confirmed_frames*: number of frames confirmed by the client.
        * *roundtrip*: average time for processing a frame, including receiver confirmation.
        * *delivery*: average time for processing a frame until it's received by the client.
          This measure assumes that the clock of the server and client are precisely synced.
        * *img_encoding*: the average time spent on encoding the array into an image.
        * *b64_encoding*: the average time spent on base64 encoding the data.
        * *fps*: the average FPS, measured from the first frame sent since ``.reset_stats()``
          was called, until the last confirmed frame.
        """
        d = self._rfb_stats
        roundtrip_count_div = d["roundtrip_count"] or 1
        sent_frames_div = d["sent_frames"] or 1
        fps_div = (d["last_time"] - d["start_time"]) or 0.001
        return {
            "sent_frames": d["sent_frames"],
            "confirmed_frames": d["confirmed_frames"],
            "roundtrip": d["roundtrip_sum"] / roundtrip_count_div,
            "delivery": d["delivery_sum"] / roundtrip_count_div,
            "img_encoding": d["img_encoding_sum"] / sent_frames_div,
            "fps": d["confirmed_frames"] / fps_div,
        }

    def _rfb_update_stats(self, feedback):
        """Update the stats when a new frame feedback has arrived."""
        last_index = feedback.get("index", 0)
        if last_index > self._rfb_last_confirmed_index:
            timestamp = feedback["timestamp"]
            nframes = last_index - self._rfb_last_confirmed_index
            self._rfb_last_confirmed_index = last_index
            self._rfb_stats["confirmed_frames"] += nframes
            self._rfb_stats["roundtrip_count"] += 1
            self._rfb_stats["roundtrip_sum"] += time.time() - timestamp
            self._rfb_stats["delivery_sum"] += feedback["localtime"] - timestamp
            self._rfb_stats["last_time"] = time.time()

    # --- the API to be a rendercanvas backend

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_info(self, present_methods):
        # Only allow simple format for now. srgb is assumed.
        if "bitmap" in present_methods:
            return {
                "method": "bitmap",
                "formats": ["rgba-u8"],
            }
        else:
            return None  # raises error

    def _rc_request_draw(self):
        # Technically, _maybe_draw() may not perform a draw if there are too
        # many frames in-flight. But in this case, we'll eventually get
        # new frame_feedback, which will then trigger a draw.
        if not self._rfb_draw_requested:
            self._rfb_draw_requested = True
            self._rfb_cancel_lossless_draw()
            self._rfb_schedule_maybe_draw()

    def _rc_request_paint(self):
        # We technically don't need to call _time_to_paint, because this backend only does bitmap mode.
        # But in case the base backend will do something in _time_to_paint later, we behave nice.
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._time_to_paint)

    def _rc_force_paint(self):
        pass  # works as-is via push_frame

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        assert format == "rgba-u8"
        self._rfb_send_frame(np.asarray(data))

    def _rc_set_logical_size(self, width, height):
        self._css_width = f"{width}px"
        self._css_height = f"{height}px"

    def _rc_close(self):
        anywidget.AnyWidget.close(self)
        self._rfb_handle_msg(self, {"type": "close"}, [])
        self._is_closed = True

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        self._title = str(title)
        self._has_titlebar = bool(title)

    def _rc_set_cursor(self, cursor):
        self._cursor = cursor

    def set_css_width(self, css_width: str):
        """Set the width of the canvas as a CSS string."""
        self._css_width = css_width

    def set_css_height(self, css_height: str):
        """Set the height of the canvas as a CSS string."""
        self._css_height = css_height

    def set_resizable(self, resizable: bool):
        """Set whether the canvas is manually resizable.

        Note that the canvas can only be made resizable if it was attached to a
        wrapper HTML element (not directly to a ``<canvas>``).
        """
        self._resizable = resizable


# Make available under a common name
RenderCanvas = AnywidgetRenderCanvas
loop = loop
