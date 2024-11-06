"""
Run a wgpu example on an automatically selected backend.
"""

from rendercanvas.auto import RenderCanvas, run

from rendercanvas.utils.cube import setup_drawing_sync


canvas = RenderCanvas(
    size=(640, 480), title=f"The wgpu cube example on a {RenderCanvas.__name__}"
)
draw_frame = setup_drawing_sync(canvas)


@canvas.request_draw
def animate():
    draw_frame()
    canvas.request_draw()


if __name__ == "__main__":
    run()
