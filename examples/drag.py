"""
Noise
-----

Simple example that uses the bitmap-context to show images of noise.
"""

# run_example = true

import numpy as np
from rendercanvas.auto import RenderCanvas, loop


canvas = RenderCanvas(update_mode="continuous")
context = canvas.get_context("bitmap")


w, h = 12, 12
currentpos = [1, 1]

@canvas.request_draw
def animate():
    x, y = currentpos

    bitmap = np.zeros((h, w, 4), np.uint8)
    bitmap[y, x] = 255

    context.set_bitmap(bitmap)



@canvas.add_event_task
async def foo(emitter):
    while True:

        # Wait for pointer down
        event = await emitter.for_event("pointer_down")

        # Does this select the current position of the active block?
        width, height = canvas.get_logical_size()
        x = int(w * event["x"] / width)
        y = int(h * event["y"] / height)
        if [x, y] != currentpos:
            print("nope", x, y)
            continue

        # Move until pointer up
        while True:
            event = await emitter.for_event("pointer_move", "pointer_up")
            if event["event_type"] == "pointer_up":
                break

            width, height = canvas.get_logical_size()
            x = int(w * event["x"] / width)
            y = int(h * event["y"] / height)
            print(x, y)
            currentpos[:] = x, y


loop.run()
