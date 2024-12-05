"""
Cube asyncio
------------

Run a wgpu example on the glfw backend, and the asyncio loop
"""

import asyncio

from rendercanvas.glfw import RenderCanvas
from rendercanvas.asyncio import loop
from rendercanvas.utils.cube import setup_drawing_sync


# The asyncio loop is the default, but this may change, so better be explicit.
RenderCanvas.select_loop(loop)

canvas = RenderCanvas(
    title="The wgpu cube on $backend with $loop", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":

    async def main():
        # ... add asyncio stuff here
        await loop.run_async()

    asyncio.run(main())
