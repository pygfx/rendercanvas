"""
Cube auto
---------

Run a wgpu example on an automatically selected backend.
"""

# run_example = true

from rendercanvas.http import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync

canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


@canvas.add_event_handler("key_down")
def process_event(event):
    if event["key"] == " ":
        # print(canvas.get_stats())
        canvas.set_logical_size(300, 300)


if __name__ == "__main__":
    loop.run()
