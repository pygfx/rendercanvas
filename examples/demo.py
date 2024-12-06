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

from rendercanvas.glfw import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync
from rendercanvas.utils.asyncs import sleep

canvas = RenderCanvas(
    size=(640, 480),
    title="Canvas events with $backend - $fps fps",
    max_fps=10,
    update_mode="continuous",
    present_method="",
)


draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


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
    elif event["event_type"] == "close":
        # Should see this exactly once, either when pressing escape, or
        # when pressing the window close button.
        print("Close detected!")
        assert canvas.get_closed()


if __name__ == "__main__":
    loop.run()
