"""
Run triangle and cube examples two canvases.
"""

# test_example = true

from rendercanvas.auto import RenderCanvas, loop

from triangle import setup_drawing_sync as setup_drawing_sync_triangle
from cube import setup_drawing_sync as setup_drawing_sync_cube


canvas1 = RenderCanvas(title=f"Triangle example on {RenderCanvas.__name__}")
draw_frame1 = setup_drawing_sync_triangle(canvas1)
canvas1.request_draw(draw_frame1)

canvas2 = RenderCanvas(title=f"Cube example on {RenderCanvas.__name__}")
draw_frame2 = setup_drawing_sync_cube(canvas2)
canvas2.request_draw(draw_frame2)


if __name__ == "__main__":
    loop.run()
