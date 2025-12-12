"""
Cube auto
---------

Run a wgpu example on an automatically selected backend.
"""

# run_example = true

from rendercanvas.pyside6 import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync

canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    loop.run()
