"""
Events
------

A simple example to demonstrate events. Events are printed in the canvas.
"""

import json

from rendercanvas.auto import RenderCanvas, loop
from PIL import Image, ImageDraw, ImageFont
import numpy as np
# import aggdraw


canvas = RenderCanvas(title="RenderCanvas events on $backend")

events_list = []
event_count = 0


@canvas.add_event_handler("*")
def process_event(event):
    global event_count
    if event["event_type"] not in ["before_draw"]:
        event_count += 1
        events_list.insert(0, event)
        events_list[32:] = []
        canvas.request_draw()


ctx = canvas.get_bitmap_context()


@canvas.request_draw
def draw():
    w, h = ctx.physical_size
    ratio = ctx.pixel_ratio

    img = Image.new("RGBA", (w, h), "#abc")
    # draw = aggdraw.Draw(img)  # like ImageDraw.Draw(img), but with subpixel support
    draw = ImageDraw.Draw(img)

    font = ImageFont.load_default(size=16 * ratio)

    x = 10.0 * ratio
    y = 0.0

    draw.text((x, y), text=f"{event_count} events", fill=(0, 0, 0), font=font)
    y += 10 * ratio

    a = 1
    for event in events_list:
        y += 20 * ratio
        if y > h:
            break
        a = max(0, a - 0.04)
        fill = round(160 * (1 - a)), round(170 * (1 - a)), round(180 * (1 - a))
        draw.text(
            (x, y),
            text=event_to_string(event),
            fill=fill,
            font=font,
        )

    ctx.set_bitmap(np.asarray(img))


float_keys = ["x", "y", "dx", "dy", "timestamp"]


def event_to_string(event):
    s = "{ "
    for key, value in event.items():
        v = json.dumps(value)
        if key in float_keys:
            try:
                i = v.index(".")
            except ValueError:
                v += ".0"
            else:
                v = v[: i + 2]
            pad = 6 - len(v)
            if pad > 0:
                v = " " * pad + v
        s += f"{key}: {v}, "
    s += " }"
    return s


if __name__ == "__main__":
    loop.run()
