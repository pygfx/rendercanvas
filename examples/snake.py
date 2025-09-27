"""
Snake game
----------

Simple snake game based on bitmap rendering. Work in progress.
"""

from collections import deque

import numpy as np

from rendercanvas.auto import RenderCanvas, loop


canvas = RenderCanvas(present_method=None, update_mode="continuous")

context = canvas.get_context("bitmap")

world = np.zeros((120, 160), np.uint8)
pos = [100, 100]
direction = [1, 0]
q = deque()


@canvas.add_event_handler("key_down")
def on_key(event):
    key = event["key"]
    if key == "ArrowLeft":
        direction[0] = -1
        direction[1] = 0
    elif key == "ArrowRight":
        direction[0] = 1
        direction[1] = 0
    elif key == "ArrowUp":
        direction[0] = 0
        direction[1] = -1
    elif key == "ArrowDown":
        direction[0] = 0
        direction[1] = 1


@canvas.request_draw
def animate():
    pos[0] += direction[0]
    pos[1] += direction[1]

    if pos[0] < 0:
        pos[0] = world.shape[1] - 1
    elif pos[0] >= world.shape[1]:
        pos[0] = 0
    if pos[1] < 0:
        pos[1] = world.shape[0] - 1
    elif pos[1] >= world.shape[0]:
        pos[1] = 0

    q.append(tuple(pos))
    world[pos[1], pos[0]] = 255

    while len(q) > 20:
        old_pos = q.popleft()
        world[old_pos[1], old_pos[0]] = 0

    context.set_bitmap(world)


loop.run()

# %%
#
# .. only:: html
#
#     Interactive example
#     ===================
#     Keyboard events are supported in the browser. Use the arrow keys to control the snake!
#
#     .. raw:: html
#
#         <iframe src="../_static/_pyodide_iframe.html"></iframe>
#
