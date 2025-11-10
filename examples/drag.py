"""
Drag
----

An example that shows coloured squares that can be dragged around using
the pointer device. Hit space to add a new block, or escape to reset
the blocks to their initial state.

This example is also useful for testing and developing backends and
events, since any unintended delays (in the presentation of the bitmap,
or the delivery of events) are easily felt as lag.
"""

import numpy as np
from rendercanvas.auto import RenderCanvas, loop


canvas = RenderCanvas(present_method=None, update_mode="continuous")

context = canvas.get_context("bitmap")


# The size of the blocks: hw is half the block width
block_size = 100

# Define blocks to show: [x, y, size, rgba]
initial_blocks = [
    [110, 110, block_size, (255, 0, 0, 255)],
    [220, 110, block_size, (0, 255, 0, 255)],
    [330, 110, block_size, (0, 0, 255, 255)],
    [110, 220, block_size, (255, 255, 0, 255)],
    [220, 220, block_size, (0, 255, 255, 255)],
    [330, 220, block_size, (255, 0, 255, 255)],
]

# Make a copy, so we can reset the initial blocks
blocks = [block.copy() for block in initial_blocks]


# Dragging info. If not None it is (block_index, block_start_pos, pointer_start_pos)
dragging = None

# The bitmap
world = np.zeros((100, 100, 4), np.uint8)


@canvas.add_event_handler("resize")
def on_resize(event):
    # Resize the bitmap with the canvas, but in logical (not physical) pixels

    global world
    w, h = int(event["width"]), int(event["height"])
    world = np.zeros((h, w, 4), np.uint8)


@canvas.add_event_handler("pointer_down")
def on_pointer_down(event):
    # Detect a drag start.
    # Note how we iterate over the blocks in reversed order, so it matches with
    # the fact that later blocks are drawn over earlier blocks.

    global dragging
    hs = block_size // 2  # half-size

    x, y = event["x"], event["y"]
    if event["button"] == 1:
        dragging = None
        for i in reversed(range(len(blocks))):
            block = blocks[i]
            bx, by = block[:2]
            if bx - hs < x < bx + hs and by - hs < y < by + hs:
                dragging = i, (bx, by), (x, y)
                block[2] = block_size + 6
                canvas.set_cursor("pointer")
                break


@canvas.add_event_handler("pointer_move")
def on_pointer_move(event):
    # If we're dragging a block, update it's position.
    # We have stored the start position of the pointer and the block.
    # That way we can easily calculate the delta position for the block,
    # and even cancel the drag if we want

    x, y = event["x"], event["y"]
    hs = block_size // 2

    if dragging is not None:
        i, (bx, by), (rx, ry) = dragging

        # Calculate delta pos, from the current pointer pos and the reference
        dx, dy = x - rx, y - ry

        # Then apply the delta
        new_x = int(bx + dx)
        new_y = int(by + dy)

        # Update the block position, while applying limits

        block = blocks[i]
        block[0] = min(max(new_x, hs), world.shape[1] - hs)
        block[1] = min(max(new_y, hs), world.shape[0] - hs)


@canvas.add_event_handler("pointer_up")
def on_pointer_up(event):
    # Stop the drag action

    global dragging
    if event["button"] == 1:
        if dragging is not None:
            blocks[dragging[0]][2] = block_size
        dragging = None

        canvas.set_cursor("default")


@canvas.add_event_handler("key_down")
def on_key(event):
    key = event["key"]
    if key == "Escape":
        blocks[:] = [block.copy() for block in initial_blocks]
    elif key == " ":
        blocks.append(
            [
                block_size // 2 + 10,
                block_size // 2 + 10,
                block_size,
                (255, 255, 255, 255),
            ]
        )


@canvas.request_draw
def animate():
    # Clear
    world.fill(0)
    world[:, :, 3] = 255

    # Draw blocks, in order that they are in the list
    for x, y, size, color in blocks:
        hs = size // 2
        world[y - hs : y + hs, x - hs : x + hs] = color

    # Present
    context.set_bitmap(world)


loop.run()
