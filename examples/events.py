"""
Events
------

An example that display events. Events are printed to stdout and shown in the canvas.
"""

import json

from rendercanvas.auto import RenderCanvas, loop
from PIL import Image, ImageDraw, ImageFont
import numpy as np


canvas = RenderCanvas(title="RenderCanvas events on $backend")
ctx = canvas.get_bitmap_context()

events_list = []
event_count = 0


# Create an event handler that gets all events ('*')


@canvas.add_event_handler("*")
def process_event(event):
    global event_count

    # Skip specific events
    if event["event_type"] in ["before_draw"]:
        return

    # Just print the dict
    print(event)

    # Add to list for drawing in the canvas
    event_count += 1
    events_list.append(event_to_string(event))
    events_list[:-32] = []  # limit to 32 entries

    # Invoke a draw
    canvas.request_draw()


# Draw the events in the canvas itself. A bit complex because of text padding etc.


@canvas.request_draw
def draw():
    w, h = ctx.physical_size
    ratio = ctx.pixel_ratio

    img = Image.new("RGBA", (w, h), "#abc")
    draw = ImageDraw.Draw(img)

    font_size = 16
    line_height = font_size * 1.25
    font = ImageFont.load_default(size=font_size * ratio)

    x = 10.0 * ratio
    y = 0.0

    draw.text((x, y), text=f"{event_count} events", fill=(0, 0, 0), font=font)
    y += 10 * ratio

    a = 1
    for event_str in reversed(events_list):
        y += line_height * ratio
        if y > h:
            break
        a = max(0, a - 0.04)
        fill = round(160 * (1 - a)), round(170 * (1 - a)), round(180 * (1 - a))
        draw.text(
            (x, y),
            text=event_str,
            fill=fill,
            font=font,
        )

    ctx.set_bitmap(np.asarray(img))


def event_to_string(event):
    """Function to turn an event dict into a string, with consistent space for float values."""
    float_keys = ["x", "y", "dx", "dy", "timestamp"]
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
