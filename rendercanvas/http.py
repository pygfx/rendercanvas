"""
A remote backend one or more browser views.

This module implements an ASGI web application, so it runs on any ASGI server. We default to uvicorn.
"""

__all__ = ["HttpRenderCanvas", "RenderCanvas", "asgi", "loop"]

import json
import time
import asyncio
from importlib.resources import files as resource_files

from .base import BaseCanvasGroup, BaseRenderCanvas, logger
from .asyncio import AsyncioLoop
from .core.encoders import encode_array, CAN_JPEG

import numpy as np


HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Minimal WS App</title>
    <script src='renderview.js'></script>
    <link rel="stylesheet" href="renderview.css">
</head>
<body>
  <h1>WebSocket Test</h1>

    <div id='canvas' class='renderview-wrapper' style='width:640px; height:480px'>
        Loading ...
    </div>
    <br><br>
    <input id="msg" placeholder="Type message..." />
    <button onclick="send()">Send</button>
    <pre id="log"></pre>

    <script>
        const log = (msg) => {
            document.getElementById("log").textContent += msg + "\\n";
        };

        const ws = new WebSocket("ws://" + location.host + "/ws");

        ws.onopen = () => log("Connected!");
        ws.onmessage = (e) => log("Server: " + e.data);
        ws.onclose = () => log("Disconnected");

        function send() {
            const input = document.getElementById("msg");
            ws.send(input.value);
            log("You: " + input.value);
            input.value = "";
        }

    </script>
    <script type='module'>
        let wrapperElement = document.getElementById('canvas')
        let viewElement = document.createElement("img")
        window.view = new window.BaseRenderView(viewElement, wrapperElement)
    </script>
</body>
</html>
"""


def _load_resource(fname):
    return resource_files("rendercanvas.core").joinpath(fname).read_text()


# A dict with resources to serve. It maps path -> (content-type, body)
resources = {}
resources["/"] = "text/html", HTML
resources["/index.html"] = "text/html", HTML
resources["/renderview.js"] = "text/javascript", _load_resource("renderview.js")
resources["/renderview.css"] = "text/css", _load_resource("renderview.css")


class Websocket:
    """An ASGI websocket

    Each websocket represents one view. These could be in the same browser
    window, or in different continents.
    """

    def __init__(self, app, id):
        self._app = app
        self._id = id
        self._send_queue = asyncio.Queue()

    async def _websocket_receiver(self, receive):
        while True:
            event = await receive()  # asgi event
            if event["type"] == "websocket.receive":
                if "text" in event:
                    self._on_receive(event["text"])
                elif "bytes" in event:
                    self._on_receive(event["bytes"])
            elif event["type"] == "websocket.disconnect":
                # TODO: handle closing from client side
                break

    async def _websocket_sender(self, send):
        while True:
            msg = await self._send_queue.get()
            if msg is None:
                await send({"type": "websocket.close", "code": 1000})
            elif isinstance(msg, str):
                await send({"type": "websocket.send", "text": msg})
            else:
                await send({"type": "websocket.send", "bytes": msg})

    def _on_receive(self, text_or_bytes: str | bytes):
        if isinstance(text_or_bytes, bytes):
            print("Unexpectedly received bytes ({len(msg}).")
        else:
            text = text_or_bytes
            try:
                event = json.loads(text)  # JS event
            except Exception:
                short_text = text[:100] + "…" if len(text) > 100 else text
                print(f"Received non-json message: {short_text!r}")
                return
            else:
                # todo: some messages, like frame feedback, should be processed per-ws, others only by one.
                self._app._on_event(self._id, event)

    def send(self, data):
        """Send data into the websocket."""
        _ = self._send_queue.put(data)

    def close(self):
        """Close the websocket from our end."""
        _ = self._send_queue.put(None)  # None means close, see _websocket_sender()


# TODO: how does this work when ppl want to include this in a larger web application, with e.g. FastAPI or Falcon?


class Asgi:
    """The ASGI application.

    This is pretty low-level web-server code, but it means we have minimal dependencies.

    One server, one canvas. So can create only one canvas in a process. Unless
    we can have multiple ASGI apps running simultaneously, e.g. on different ports or paths.

    One websocket for each client. But only first websocket in the list controls.
    """

    def __init__(self, resources):
        self._resources = resources
        self._websockets = []
        self._event_callback = lambda id, ev: None
        self._ws_count = 0

    async def __call__(self, scope, receive, send):
        """The ASGI entrypoint."""

        if scope["type"] == "http":
            content_type_and_body = self._resources.get(scope["path"], None)
            if content_type_and_body is not None:
                content_type, body = content_type_and_body
                if isinstance(body, str):
                    body = body.encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"content-type", content_type.encode())],
                    }
                )
                await send({"type": "http.response.body", "body": body})
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Not Found"})

        elif scope["type"] == "websocket":
            await send({"type": "websocket.accept"})

            self._ws_count += 1
            ws = Websocket(self, self._ws_count)
            self._websockets.append(ws)

            try:
                receiver = asyncio.create_task(ws._websocket_receiver(receive))
                sender = asyncio.create_task(ws._websocket_sender(send))
                _done, pending = await asyncio.wait(
                    [receiver, sender],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
            finally:
                self._websockets.remove(ws)

    def _on_event(self, id, event):
        """Called when a websocket receives an event."""
        self._event_callback(id, event)

    def send_all(self, data: bytes):
        """Send data to all websockets."""
        for ws in self._websockets:
            ws.send(data)

    def close(self):
        """Disconnect all clients."""
        # TODO: also put in a closed (non-restartable) state? i.e. think about lifetime cycle
        for ws in self._websockets:
            ws.close()


class HttpLoop(AsyncioLoop):
    def run(self, host="localhost", port=60649):
        self._host = host
        self._port = port
        return super().run()

    def _rc_run(self):
        from uvicorn.main import main as uvicorn_main

        print(f"Starting server at http://{self._host}:{self._port}")
        uvicorn_main(
            [
                f"--host={self._host}",
                f"--port={self._port}",
                "--log-level=warning",
                f"{__name__}:asgi",
            ]
        )


loop = HttpLoop()


class HttpCanvasGroup(BaseCanvasGroup):
    pass


class HttpRenderCanvas(BaseRenderCanvas):
    """A remote canvas that is served over http and viewed in a browser."""

    _rc_canvas_group = HttpCanvasGroup(loop)

    _max_buffered_frames = 2
    _quality = 80

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # todo: limit to a single canvas
        asgi._event_callback = self._on_event

        self._is_closed = False

        self._draw_requested = False
        self._frame_index = 0
        self._last_confirmed_index = 0
        self._warned_png = False
        self._lossless_draw_info = None

        self.reset_stats()

        # Set size, title, etc.
        self._final_canvas_init()

    def _on_event(self, id: int, event: dict):
        try:
            type = event["type"]
        except KeyError:
            logger.warning(f"Invalid event: {event!r}")
            return

        # TODO: some logic depends on the id
        # TODO: keep track of frame feedback per id, main ws determines frame rate, others drop frames as necessary

        if type.startswith("comm-"):
            if type == "comm-frame-feedback":
                self._frame_feedback = event["value"]
                loop.call_soon(self._maybe_draw)
            elif type == "comm-has-visible-views":
                self._has_visible_views = event["value"]
                loop.call_soon(self._maybe_draw)
            else:
                logger.warning(f"Unknown comm event: {event!r}")
        else:
            # A renderview event

            if type == "resize":
                self._size_info.set_physical_size(
                    event["pwidth"], event["pheight"], event["ratio"]
                )
            elif type == "close":
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

    def _maybe_draw(self):
        """Perform a draw, if we can and should."""
        feedback = self._frame_feedback
        # Update stats
        self._update_stats(feedback)
        # Determine whether we should perform a draw: a draw was requested, and
        # the client is ready for a new frame, and the client widget is visible.
        frames_in_flight = self._frame_index - feedback.get("index", 0)
        should_draw = (
            self._draw_requested
            and frames_in_flight < self._max_buffered_frames
            and self._has_visible_views
        )
        # Do the draw if we should.
        if should_draw:
            self._draw_requested = False
            self._time_to_draw()  # -> _rc_present_bitmap -> _send_frame

    def _schedule_lossless_draw(self, array, delay=0.3):
        self._cancel_lossless_draw()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(delay, self._lossless_draw)
        self._lossless_draw_info = array, handle

    def _cancel_lossless_draw(self):
        if self._lossless_draw_info:
            _, handle = self._lossless_draw_info
            self._lossless_draw_info = None
            handle.cancel()

    def _lossless_draw(self):
        array, _ = self._lossless_draw_info
        self._send_frame(array, True)

    def _send_frame(self, array, is_lossless_redraw=False):
        """Actually send a frame over to the client."""
        # For considerations about performance,
        # see https://github.com/vispy/jupyter_rfb/issues/3

        quality = 100 if is_lossless_redraw else self._quality

        self._frame_index += 1
        timestamp = time.time()

        # Turn array into a based64-encoded JPEG or PNG
        t1 = time.perf_counter()
        mimetype, data = encode_array(array, quality)
        datas = [data]
        data_b64 = None
        t2 = time.perf_counter()

        if "jpeg" in mimetype:
            self._schedule_lossless_draw(array)
        else:
            self._cancel_lossless_draw()
            # Issue png warning?
            if quality < 100 and not CAN_JPEG and not self._warned_png:
                self._warned_png = True
                logger.warning(
                    "No JPEG encoder found, using PNG instead. Install simplejpeg for better performance."
                )

        if is_lossless_redraw:
            # No stats, also not on the confirmation of this frame
            self._last_confirmed_index = self._frame_index
        else:
            # Stats
            self._stats["img_encoding_sum"] += t2 - t1
            self._stats["sent_frames"] += 1
            if self._stats["start_time"] <= 0:  # Start measuring
                self._stats["start_time"] = timestamp
                self._last_confirmed_index = self._frame_index - 1

        # Compose message and send
        msg = dict(
            type="framebufferdata",
            mimetype=mimetype,
            data_b64=data_b64,
            index=self._frame_index,
            timestamp=timestamp,
        )
        self.send(msg, datas)

    # ----- related to stats

    def reset_stats(self):
        """Restart measuring statistics from the next sent frame."""
        self._stats = {
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
        d = self._stats
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

    def _update_stats(self, feedback):
        """Update the stats when a new frame feedback has arrived."""
        last_index = feedback.get("index", 0)
        if last_index > self._last_confirmed_index:
            timestamp = feedback["timestamp"]
            nframes = last_index - self._last_confirmed_index
            self._last_confirmed_index = last_index
            self._stats["confirmed_frames"] += nframes
            self._stats["roundtrip_count"] += 1
            self._stats["roundtrip_sum"] += time.time() - timestamp
            self._stats["delivery_sum"] += feedback["localtime"] - timestamp
            self._stats["last_time"] = time.time()

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
        if not self._draw_requested:
            self._draw_requested = True
            self._cancel_lossless_draw()
            loop.call_soon(self._maybe_draw)

    def _rc_request_paint(self):
        # We technically don't need to call _time_to_paint, because this backend only does bitmap mode.
        # But in case the base backend will do something in _time_to_paint later, we behave nice.
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._time_to_paint)

    def _rc_force_paint(self):
        pass  # works as-is via push_frame

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        assert format == "rgba-u8"
        self._send_frame(np.asarray(data))

    def _rc_set_logical_size(self, width, height):
        asgi.send({"type": "comm-css-width", "value": f"{width}px"})
        asgi.send({"type": "comm-css-height", "value": f"{height}px"})

    def _rc_close(self):
        asgi.close()
        self._is_closed = True

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        asgi.send({"type": "comm-title", "value": title})

    def _rc_set_cursor(self, cursor):
        asgi.send({"type": "comm-cursor", "value": cursor})

    def set_css_width(self, css_width: str):
        """Set the width of the canvas as a CSS string."""
        asgi.send({"type": "comm-css-width", "value": css_width})

    def set_css_height(self, css_height: str):
        """Set the height of the canvas as a CSS string."""
        asgi.send({"type": "comm-css-height", "value": css_height})


asgi = Asgi(resources)
RenderCanvas = HttpRenderCanvas
