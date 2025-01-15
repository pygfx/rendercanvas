"""
Cube raw loop
-------------

Run a wgpu example on the glfw backend, and the raw loop.
"""

from rendercanvas.glfw import RenderCanvas
from rendercanvas.raw import loop
from rendercanvas.utils.cube import setup_drawing_sync


RenderCanvas.select_loop(loop)

canvas = RenderCanvas(
    title="The wgpu cube on $backend with $loop", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    loop.run()
