"""
Cube trio
---------

Run a wgpu example on the glfw backend, and the trio loop
"""

import trio
from rendercanvas.glfw import RenderCanvas
from rendercanvas.trio import loop
from rendercanvas.utils.cube import setup_drawing_sync


RenderCanvas.select_loop(loop)

canvas = RenderCanvas(
    title="The wgpu cube on $backend with $loop", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    # This works, but is not very trio-ish
    # loop.run()

    # This looks more like it
    # trio.run(loop.run_async)

    # But for the sake of completeness ...

    async def main():
        # ... add Trio stuff here
        await loop.run_async()

    trio.run(main)
