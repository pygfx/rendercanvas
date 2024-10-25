"""
Run a wgpu example on the wx backend.
"""

from rendercanvas.wx import WgpuCanvas, run

from rendercanvas.utils.cube import setup_drawing_sync


canvas = WgpuCanvas(size=(640, 480), title="The wgpu cube example on wx")
draw_frame = setup_drawing_sync(canvas)


@canvas.request_draw
def animate():
    draw_frame()
    canvas.request_draw()


if __name__ == "__main__":
    run()
