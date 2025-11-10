"""
Noise
-----

Simple example that uses the bitmap-context to show images of noise.
"""

# run_example = true

import numpy as np
from rendercanvas.auto import RenderCanvas, loop


canvas = RenderCanvas(update_mode="continuous")
context = canvas.get_bitmap_context()


@canvas.request_draw
def animate():
    w, h = canvas.get_logical_size()
    shape = int(h) // 4, int(w) // 4

    bitmap = np.random.uniform(0, 255, shape).astype(np.uint8)
    context.set_bitmap(bitmap)


loop.run()
