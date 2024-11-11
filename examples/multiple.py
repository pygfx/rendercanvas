"""
Run cube example in two canvases.
"""

# test_example = true

from rendercanvas.auto import RenderCanvas, loop

from rendercanvas.utils.cube import setup_drawing_sync

canvas1 = RenderCanvas(title="$backend 1", update_mode="continuous")
draw_frame1 = setup_drawing_sync(canvas1)
canvas1.request_draw(draw_frame1)

canvas2 = RenderCanvas(title="$backend 2", update_mode="continuous")
draw_frame2 = setup_drawing_sync(canvas2)
canvas2.request_draw(draw_frame2)


if __name__ == "__main__":
    loop.run()
