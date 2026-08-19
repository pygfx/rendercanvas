"""
Text
----

Example that renders text with the bitmap context, using Pillow's ImageDraw.
"""

# run_example = true

import numpy as np
from rendercanvas.auto import RenderCanvas, loop
from PIL import Image, ImageDraw, ImageFont


canvas = RenderCanvas(update_mode="continuous")
ctx = canvas.get_bitmap_context()


@canvas.request_draw
def animate():
    w, h = ctx.physical_size
    ratio = ctx.pixel_ratio

    img = Image.new("RGBA", (w, h), "#fff")
    # draw = aggdraw.Draw(img)  # like ImageDraw.Draw(img), but with subpixel support
    draw = ImageDraw.Draw(img)

    font_size = 16
    line_height_p = font_size * 1.5 * ratio
    font = ImageFont.load_default(size=font_size * ratio)

    x = 10.0 * ratio
    y = 0.0

    for line in lorem.splitlines():
        draw.text((x, y), text=line, fill=(0, 0, 0), font=font)
        y += line_height_p

    ctx.set_bitmap(np.asarray(img))


lorem = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit,sed do eiusmod
tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim
veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex
ea commodo consequat. Duis aute irure dolor in reprehenderit in
voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur
sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt
mollit anim id est laborum.
"""

loop.run()
