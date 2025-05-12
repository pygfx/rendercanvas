"""
Demo
----

An example that uses events to trigger some canvas functionality.

A nice demo, and very convenient to test the different backends.

* Can be closed with Escape or by pressing the window close button.
* In both cases, it should print "Close detected" exactly once.
* Hit "f" to spend 2 seconds doing direct draws.
* Hit "s" to async-sleep the scheduling loop for 2 seconds. Resizing
  and closing the window still work.

"""

import time

from rendercanvas.auto import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync
from rendercanvas.utils.asyncs import sleep
import rendercanvas


canvas = RenderCanvas(
    size=(640, 480),
    title="Canvas events with $backend on $loop - $fps fps",
    max_fps=10,
    update_mode="continuous",
    present_method="",
)


draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)

# Note: in this demo we listen to all events (using '*'). In general
# you want to select one or more specific events to handle.


@canvas.add_event_handler("*")
async def process_event(event):
    if event["event_type"] not in ["pointer_move", "before_draw", "animate"]:
        print(event)

    if event["event_type"] == "key_down":
        if event["key"] == "Escape":
            canvas.close()
        elif event["key"] in " f":
            # Force draw for 2 secs
            print("force-drawing ...")
            etime = time.time() + 2
            i = 0
            while time.time() < etime:
                i += 1
                canvas.force_draw()
            print(f"Drew {i} frames in 2s.")
        elif event["key"] == "s":
            print("Async sleep ... zzzz")
            await sleep(2)
            print("waking up")
        elif event["key"] == "c":
            # Swap cursor
            shapes = list(rendercanvas.CursorShape)
            canvas.cursor_index = getattr(canvas, "cursor_index", -1) + 1
            if canvas.cursor_index >= len(shapes):
                canvas.cursor_index = 0
            cursor = shapes[canvas.cursor_index]
            canvas.set_cursor(cursor)
            print(f"Cursor: {cursor!r}")
    elif event["event_type"] == "close":
        # Should see this exactly once, either when pressing escape, or
        # when pressing the window close button.
        print("Close detected!")
        assert canvas.get_closed()


if __name__ == "__main__":
    loop.run()
