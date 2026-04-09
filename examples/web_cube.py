"""
Cube in the browser
-------------------

Run a wgpu example with the http backend. Also see web_fastapi.py for
how to integrate a rendercanvas into a larger web application.
"""

# run_example = true

from rendercanvas.http import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync

canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


# the loop.run() of this backend uses uvicorn to start a webserver
loop.run()
