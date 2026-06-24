"""
A remote backend with one or more browser views.

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
from .core.events import valid_event_types

import numpy as np


HTML = """<!DOCTYPE html>
<html>
<head>
    <title>RenderCanvas over http</title>
    <script type='module' src='renderview.js'></script>
    <script type='module' src='renderview-client.js'></script>
    <link rel="stylesheet" href="renderview.css">
</head>
<body>
  <h1>RenderCanvas over http</h1>

    <div id='canvas' class='renderview-wrapper is-resizable' style='width:640px; height:480px'>
        <p style='width:100%; height:100%; background:#aaa; display: flex; justify-content: center; align-items: center; font-size:150%'>Loading ...</p>
    </div>

    <div id='status' style='position:fixed; top:0; right:0; background:#ccc; color:#000; padding:1em; font-family: monospace'></div>
</body>
</html>
"""


def _load_resource(fname):
    return resource_files("rendercanvas.core").joinpath(fname).read_text()


# A dict with resources to serve. It maps path -> (content-type, body)
resources = {}
resources["index.html"] = "text/html", HTML
resources["renderview.css"] = "text/css", _load_resource("renderview.css")
for fname in ("renderview.js", "renderview-client.js"):
    resources[fname] = "text/javascript", _load_resource(fname)


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
        try:
            while True:
                event = await receive()  # asgi event
                if event["type"] == "websocket.receive":
                    if "text" in event:
                        self._on_receive(event["text"])
                    elif "bytes" in event:
                        self._on_receive(event["bytes"])
                elif event["type"] == "websocket.disconnect":
                    break
        except asyncio.CancelledError:
            pass

    async def _websocket_sender(self, send):
        try:
            while True:
                msg = await self._send_queue.get()
                if msg is None:
                    await send({"type": "websocket.close", "code": 1000})
                    break
                elif isinstance(msg, str):
                    await send({"type": "websocket.send", "text": msg})
                else:
                    await send({"type": "websocket.send", "bytes": msg})
        except asyncio.CancelledError:
            pass
        except Exception as err:
            if "disconnect" in err.__class__.__name__.lower():
                pass
            elif "websocket.close" in err.args[0]:
                pass
            else:
                raise err from None

    def _on_receive(self, text_or_bytes: str | bytes):
        if isinstance(text_or_bytes, bytes):
            logger.warning("Unexpectedly received bytes ({len(msg}).")
        else:
            text = text_or_bytes
            try:
                event = json.loads(text)  # JS event
            except Exception:
                short_text = text[:100] + "…" if len(text) > 100 else text
                logger.warning(f"Received non-json message: {short_text!r}")
                return
            else:
                self._app._on_event(event, self._id)

    def send(self, data: dict | bytes):
        """Send data into the websocket."""
        if isinstance(data, dict):
            data = json.dumps(data)
        elif isinstance(data, bytes):
            data = data
        else:
            RuntimeError("ws.send expects dict or bytes")
        asyncio.create_task(self._send_queue.put(data))  # noqa: RUF006

    def close(self):
        """Close the websocket from our end."""
        _ = self._send_queue.put(None)  # None means close, see _websocket_sender()


class Asgi:
    """The ASGI application.

    This is pretty low-level web-server code, but it means we have minimal dependencies.

    One server, one canvas. So can create only one canvas in a process. Unless
    we can have multiple ASGI apps running simultaneously, e.g. on different ports or paths.

    One websocket for each client. But only first websocket in the list controls.
    """

    def __init__(self, resources):
        self._resources = resources
        self._websockets = {}  # id -> ws
        self._event_callback = lambda ev, id: None
        self._ws_counter = 0

    async def __call__(self, scope, receive, send):
        """The ASGI entrypoint."""

        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    loop.kickstart()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    ...  # Do some shutdown here!
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        elif scope["type"] == "http":
            # Just assume a flat resources dict, so we can mount anywhere in a larger app
            fname = scope["path"].rsplit("/", 1)[-1]
            fname = fname or "index.html"
            content_type_and_body = self._resources.get(fname, None)
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

            # When running mounted in a larger app, we miss out on the lifespan events
            loop.kickstart()

            self._ws_counter += 1
            id = self._ws_counter
            ws = Websocket(self, id)
            self._websockets[id] = ws
            self._event_callback(
                {"type": "_clients_change", "ids": tuple(self._websockets)}, 0
            )

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
                self._websockets.pop(id, None)
                self._event_callback(
                    {"type": "_clients_change", "ids": tuple(self._websockets)}, 0
                )

    def _on_event(self, event, id):
        """Called when a websocket receives an event."""
        try:
            self._event_callback(event, id)
        except Exception as err:
            logger.warning(f"Error handling ws event callback: {err}")

    def send_all(self, msg: dict):
        """Send data to all websockets."""
        assert isinstance(msg, dict)
        for ws in self._websockets.values():
            ws.send(msg)

    def send_to(self, msg: dict, buffers: list[bytes], ids=list[int]):
        if len(buffers) > 0:
            assert msg["nbuffers"] == len(buffers)
        for id in ids:
            ws = self._websockets.get(id, None)
            if ws is not None:
                ws.send(msg)
                for buffer in buffers:
                    ws.send(buffer)

    def close(self):
        """Disconnect all clients."""
        # I guess technically clients can reconnect again. Not sure if that works.
        for ws in self._websockets.values():
            ws.close()

    def get_count(self):
        return len(self._websockets)


class HttpLoop(AsyncioLoop):
    def run(self, host="localhost", port=60649):
        self._host = host
        self._port = port
        return super().run()

    def _rc_run(self):
        # Allow the standard rendercanvas usage (``loop.run()``) to start the web server

        from uvicorn.main import main as uvicorn_main

        # Use warning level; if using info, the message may not be shown
        logger.warning(f"Starting server at http://{self._host}:{self._port}")
        uvicorn_main(
            [
                f"--host={self._host}",
                f"--port={self._port}",
                "--log-level=warning",
                f"{__name__}:asgi",
            ]
        )

    def kickstart(self):
        if self._run_loop is None:
            try:
                asyncio.get_running_loop().create_task(loop._rc_run_async())
            except Exception as err:
                logger.error("could not start rendercanvas loop:", err)
            else:
                logger.info("rendercanvas loop started")


loop = HttpLoop()


class HttpCanvasGroup(BaseCanvasGroup):
    pass


class HttpRenderCanvas(BaseRenderCanvas):
    """A remote canvas that is served over http and viewed in a browser.

    It is assumed that there is exactly one canvas per connected client.
    Multiple clients can simultaneously connect to the server. They will be served
    the same stream of images. There is one "active" client, which determines
    the pase of rendering. Events from the passive clients are ignored.
    Passive clients drop frames if necessary to keep up with the active client.
    """

    _rc_canvas_group = HttpCanvasGroup(loop)

    _max_buffered_frames = 2

    _quality = 80

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Note: we assume there is only a single canvas on the page
        asgi._event_callback = self._on_event

        self._is_closed = False
        self._draw_requested = False
        self._pending_maybe_draw = False

        self._last_frame = None, None
        self._ref_index = 0  # global index to identify a frame
        self._active_client = 0
        self._frame_info_per_client = {}  # {sent: int, confirmed: int, ref: int}

        self._warned_png = False
        self._lossless_draw_info = None

        self.reset_stats()

        # Set size, title, etc.
        self._final_canvas_init()

    def _on_event(self, event: dict, id: int):
        try:
            type = event["type"]
        except KeyError:
            logger.warning(f"Invalid event: {event!r}")
            return

        if type.startswith("_"):
            # Internal event
            if type == "_clients_change":
                # Update our per-client info
                new = {"sent": 0, "confirmed": 0, "ref": 0}
                self._frame_info_per_client = {
                    id: self._frame_info_per_client.get(id, new) for id in event["ids"]
                }
                # select longest connected client as the new active one
                self._active_client = event["ids"][0] if event["ids"] else 0
                self._update_active_states()
                self._schedule_maybe_draw()
            elif type == "_framefeedback":
                # Update last confirmed frame. But only schedule new draws based on the active client.
                self._frame_info_per_client[id]["confirmed"] = event["index"]
                self._schedule_maybe_draw()
                if id == self._active_client:
                    self._update_stats_on_frame_receive(event["timestamp"])
            else:
                logger.warning(f"Unknown event: {event!r}")
        else:
            # A renderview event

            # if type == "visible"
            if id != self._active_client:
                return  # ignore events from passive clients

            if type == "resize":
                self._size_info.set_physical_size(
                    event["pwidth"], event["pheight"], event["ratio"]
                )
            elif type == "close":
                self.close()
            elif type in valid_event_types:
                # Compatibility between new renderview event spec and current rendercanvas/pygfx events
                event["event_type"] = event.pop("type")
                event["time_stamp"] = event.pop("timestamp")
                # Turn lists into tuples (js/json does not have tuples)
                if "buttons" in event:
                    event["buttons"] = tuple(event["buttons"])
                if "modifiers" in event:
                    event["modifiers"] = tuple(event["modifiers"])
                self.submit_event(event)

    def _schedule_maybe_draw(self, *args):
        if not self._pending_maybe_draw:
            self._pending_maybe_draw = True
            loop.call_soon(self._maybe_draw)

    def _maybe_draw(self):
        """Perform a draw, if we can and should."""
        self._pending_maybe_draw = False

        # Based on the active client, determine if we need a new draw
        try:
            info = self._frame_info_per_client[self._active_client]
        except KeyError:
            active_client_ready_for_new_frame = False
        else:
            active_client_ready_for_new_frame = (
                info["sent"] - info["confirmed"] < self._max_buffered_frames
            )
        should_draw = (
            self._draw_requested
            and active_client_ready_for_new_frame
            and len(self._frame_info_per_client) > 0
        )
        # Do the draw if we should. Otherwise maybe send frames to other clients.
        if should_draw:
            self._draw_requested = False
            self._time_to_draw()  # -> _rc_present_bitmap -> _encode_frame
        elif len(self._frame_info_per_client) > 1:
            self._send_last_frame_to_ready_clients()

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
        if self._lossless_draw_info is not None:
            array, _ = self._lossless_draw_info
            self._encode_frame(array, True)

    def _encode_frame(self, array, is_lossless_redraw=False):
        """Encode a frame and store it so we can send it to each client in the right time."""
        # For considerations about performance,
        # see https://github.com/vispy/jupyter_rfb/issues/3
        quality = 100 if is_lossless_redraw else self._quality

        timestamp = time.time()

        # Turn array into a based64-encoded JPEG or PNG
        t1 = time.perf_counter()
        mimetype, data = encode_array(array, quality)
        buffers = [data]
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

        # Stats
        if not is_lossless_redraw:
            self._stats["encoding_sum"] += t2 - t1
            self._stats["encoded_frames"] += 1
            if self._stats["start_time"] <= 0:  # Start measuring
                self._stats["start_time"] = timestamp

        # Compose message and send
        msg = dict(
            type="framebufferdata",
            nbuffers=len(buffers),
            mimetype=mimetype,
            timestamp=timestamp,
            index=0,
        )

        # Store this frame
        self._last_frame = msg, buffers
        self._ref_index += 1

        # Send to clients that are ready
        self._send_last_frame_to_ready_clients()

    def _send_last_frame_to_ready_clients(self):
        """Send the last frame to clients that are ready, and have not yet been sent it."""
        msg, buffers = self._last_frame
        max_buffered_frames = self._max_buffered_frames
        ref_index = self._ref_index

        for id, info in self._frame_info_per_client.items():
            if info["sent"] - info["confirmed"] < max_buffered_frames:
                if info["ref"] < ref_index:
                    this_msg = msg.copy()
                    info["ref"] = ref_index
                    info["sent"] += 1
                    this_msg["index"] = info["sent"]
                    self._stats["sent_frames"] += 1
                    asgi.send_to(this_msg, buffers, [id])

    # ----- related to stats

    def reset_stats(self):
        """Restart measuring statistics from the next sent frame."""
        self._stats = {
            "start_time": 0.0,
            "last_time": 0.0,
            "encoded_frames": 0,
            "sent_frames": 0,
            "confirmed_frames": 0,
            "encoding_sum": 0.0,
            "roundtrip_sum": 0.0,
        }

    def _update_stats_on_frame_receive(self, timestamp):
        """Update the stats when a new frame feedback has arrived."""
        now = time.time()
        self._stats["confirmed_frames"] += 1
        self._stats["roundtrip_sum"] += now - timestamp
        self._stats["last_time"] = now

    def get_stats(self):
        """Get the current stats since the last time ``.reset_stats()`` was called.

        Stats is a dict with the following fields:

        * *encoded_frames*: the number of encoded frames.
        * *sent_frames*: the number of frames sent.
        * *confirmed_frames*: number of frames confirmed by the client.
        * *roundtrip*: average time for processing a frame, including receiver confirmation.
        * *encoding*: the average time spent on encoding the array into an image.
        * *fps*: the average FPS, measured from the first frame sent since ``.reset_stats()``
          was called, until the last confirmed frame.
        """
        d = self._stats
        fps_div = (d["last_time"] - d["start_time"]) or 0.001
        return {
            "encoded_frames": d["encoded_frames"],
            "sent_frames": d["sent_frames"],
            "confirmed_frames": d["confirmed_frames"],
            "encoding": d["encoding_sum"] / d["encoded_frames"],
            "roundtrip": d["roundtrip_sum"] / d["confirmed_frames"],
            "fps": d["confirmed_frames"] / fps_div,
        }

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
            self._schedule_maybe_draw()

    def _rc_request_paint(self):
        # We technically don't need to call _time_to_paint, because this backend only does bitmap mode.
        # But in case the base backend will do something in _time_to_paint later, we behave nice.
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._time_to_paint)

    def _rc_force_paint(self):
        pass  # works as-is via push_frame

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        assert format == "rgba-u8"
        self._encode_frame(np.asarray(data))

    def _rc_set_logical_size(self, width, height):
        asgi.send_all({"type": "comm-css-width", "value": f"{width}px"})
        asgi.send_all({"type": "comm-css-height", "value": f"{height}px"})

    def _rc_close(self):
        asgi.close()
        self._is_closed = True

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        asgi.send_all({"type": "title", "value": title})

    def _rc_set_cursor(self, cursor):
        asgi.send_all({"type": "cursor", "value": cursor})

    def set_css_width(self, css_width: str):
        """Set the width of the canvas as a CSS string."""
        asgi.send_all({"type": "css_width", "value": css_width})

    def set_css_height(self, css_height: str):
        """Set the height of the canvas as a CSS string."""
        asgi.send_all({"type": "css_height", "value": css_height})

    def _update_active_states(self):
        active_ids = [self._active_client]
        passive_ids = set(self._frame_info_per_client.keys())
        passive_ids.discard(self._active_client)

        asgi.send_to({"type": "active", "value": True}, [], active_ids)
        asgi.send_to({"type": "active", "value": False}, [], passive_ids)


asgi = Asgi(resources)
RenderCanvas = HttpRenderCanvas
