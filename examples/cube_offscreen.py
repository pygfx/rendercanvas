"""
Render a wgpu example offscreen, and display as an image.
"""

import os
import tempfile
import webbrowser

import imageio.v3 as iio
from rendercanvas.offscreen import RenderCanvas
from rendercanvas.utils.cube import setup_drawing_sync


canvas = RenderCanvas(size=(640, 480), pixel_ratio=2)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)

image = canvas.draw()
assert image.shape == (960, 1280, 4)

filename = os.path.join(tempfile.gettempdir(), "rendercanvasexample.png")
iio.imwrite(filename, image)
webbrowser.open("file://" + filename)
