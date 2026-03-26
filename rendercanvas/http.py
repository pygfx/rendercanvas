"""
A remote backend one or more browser views.

This module implements an ASGI web application, so it runs on any ASGI server. We default to uvicorn.
"""

import json
import asyncio
from importlib.resources import files as resource_files

from .asyncio import AsyncioLoop


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
            event = await receive()
            if event["type"] == "websocket.receive":
                if "text" in event:
                    self._on_receive(event["text"])
                elif "bytes" in event:
                    self._on_receive(event["bytes"])
            elif event["type"] == "websocket.disconnect":
                break

    async def _websocket_sender(self, send):
        while True:
            msg = await self._send_queue.get()
            if isinstance(msg, str):
                await send({"type": "websocket.send", "text": msg})
            else:
                await send({"type": "websocket.send", "bytes": msg})

    def send(self, data):
        """Send data into the websocket."""
        _ = self._send_queue.put(data)

    def _on_receive(self, msg):
        if isinstance(msg, bytes):
            print("Unexpectedly received bytes ({len(msg}).")
        try:
            event = json.loads(msg)
        except Exception:
            short_text = text[:100] + "…" if len(text) > 100 else text
            print(f"Received non-json message: {short_text!r}")
            return
        else:
            # todo: some messages, like frame feedback, should be processed per-ws, others only by one.
            self._app._on_event(self._id, event)


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
        self._event_callback = lambda ev: None
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
                done, pending = await asyncio.wait(
                    [receiver, sender],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
            finally:
                self._websockets.remove(ws)

    def _on_event(self, id, event):
        """Called when a websocket receives an event."""
        print(id, event)

    def send_all(self, data: bytes):
        """Send data to all websockets."""
        for ws in self._websockets:
            ws.send(data)


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


asgi = Asgi(resources)

loop = HttpLoop()
