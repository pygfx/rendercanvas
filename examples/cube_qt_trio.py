"""
Cube qt canvas on the trio loop
-------------------------------

Run a wgpu example on the Qt backend, but with the trio loop.

Not sure why you'd want this, but it works! Note that the other way
around, e.g. runnning a glfw canvas with the Qt loop does not work so
well.
"""

import trio
from rendercanvas.pyside6 import RenderCanvas
from rendercanvas.trio import loop
from rendercanvas.utils.cube import setup_drawing_sync

RenderCanvas.select_loop(loop)

canvas = RenderCanvas(title="The $backend with $loop", update_mode="continuous")
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    trio.run(loop.run_async)
