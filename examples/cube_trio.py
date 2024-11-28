"""
Cube trio
---------

Run a wgpu example on the glfw backend, and the trio loop
"""

from rendercanvas.glfw import RenderCanvas
from rendercanvas.trio import loop

from rendercanvas.utils.cube import setup_drawing_sync


canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    loop.run()
