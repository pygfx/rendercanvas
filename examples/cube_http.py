"""
Cube in the browser
-------------------

Run a wgpu example with the http backend. Note that the http backend can be used
with most examples by simply using ``from rendercanvas.http import RenderCanvas,
loop``. This example also shows how the web-page can be customized.

Also see fastapi_app.py for how to integrate a rendercanvas into a larger web
application.
"""

# run_example = false

from rendercanvas.http import RenderCanvas, loop, resources
from rendercanvas.utils.cube import setup_drawing_sync
from rendercanvas.core.encoders import encode_png
import numpy as np


canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


# Define custom HTML. This is optional.
html = """<!DOCTYPE html>
<html>
<head>
    <title>RenderCanvas over http</title>
    <script type='module' src='renderview.js'></script>
    <script type='module' src='renderview-client.js'></script>
    <link rel="stylesheet" href="renderview.css">
    <link rel="icon" href="logo.png">
</head>
<body style='margin:0'>

    <div id='canvas' class='' style='display:block; width:100vw; height:min(100vh,80vw); --line-thickness:0'>
        Loading ...
    </div>

    <div id='status' style='position:fixed; top:10px; right:10px; background:#ccc; color:#000; padding:0.5em; font-family: monospace; border-radius:5px; '></div>
</body>
</html>
"""

# The resources is simply a dict that maps filenames to (content-type, body) tuples.
resources["index.html"] = "text/html", html


# You can also add new resources, like images or even extra web pages.
im = np.random.uniform(0, 255, (16, 16, 3)).astype(np.uint8)
resources["logo.png"] = "image/png", encode_png(im)


# The loop.run() of this backend uses uvicorn to start a webserver.
# The args are optional and default to "localhost" and port 60649
loop.run("localhost", 8080)
