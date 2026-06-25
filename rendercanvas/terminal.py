"""
A stub backend for documentation purposes.
"""

__all__ = ["RenderCanvas", "TerminalRenderCanvas", "loop"]


import sys

from .base import BaseCanvasGroup, BaseRenderCanvas
from .asyncio import AsyncioLoop

import numpy as np

# The terminal backend requires the blessed library, which is simple and has few dependencies
import blessed


term = blessed.Terminal()


class TerminalLoop(AsyncioLoop):
    def _rc_run(self):
        with term.fullscreen(), term.hidden_cursor():
            super()._rc_run()


loop = TerminalLoop()


class TerminalCanvasGroup(BaseCanvasGroup):
    pass


class TerminalRenderCanvas(BaseRenderCanvas):
    """A canvas in the terminal, using blessed."""

    _rc_canvas_group = TerminalCanvasGroup(loop)

    def __init__(self, *args, pixel_ratio=0.25, upscale_factor=1, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixel_ratio = max(1 / 32, float(pixel_ratio))
        self._upscale_factor = max(1, int(upscale_factor))

        self._closed = False
        self._term_size = 0, 0

        # TODO: force singleton

        self._rc_gui_poll()
        self._final_canvas_init()

    def _rc_gui_poll(self):
        # Check for resize
        term_size = term.width, term.height
        if term_size != self._term_size:
            self._term_size = term_size
            # Determine physical size. Each char is two vertical pixels. Have a margin to avoid jump artifacts.
            pwidth = term_size[0] * self._upscale_factor
            pheight = term_size[1] * 2 * self._upscale_factor
            self._size_info.set_physical_size(pwidth, pheight, self._pixel_ratio)
            self.request_draw()

        # Check for key pressed
        key = term.inkey(timeout=0)
        if key:
            sys.stderr.write(key + "\n")

    def _rc_get_present_info(self, present_methods):
        if "bitmap" in present_methods:
            return {
                "method": "bitmap",
                "formats": ["rgba-u8", "rgba-f16", "rgba-u16"],
            }
        else:
            return None  # raises error

    def _rc_request_draw(self):
        self._time_to_draw()

    def _rc_request_paint(self):
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._time_to_paint)

    def _rc_force_paint(self):
        self._time_to_paint()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # Get image from data, optionally downscale
        factor = self._upscale_factor
        if factor == 1:
            img = data
        else:
            h, w, c = data.shape
            img = (
                data.reshape(h // factor, factor, w // factor, factor, c)
                .mean(axis=(1, 3))
                .astype(np.uint8)
            )

        # Push lines to stdout
        for y in range(0, img.shape[0], 2):
            top_row = img[y][:, :3]
            bot_row = img[y + 1][:, :3]
            line = "".join(
                term.on_color_rgb(*rgb1) + term.color_rgb(*rgb2) + "▄"
                for rgb1, rgb2 in zip(top_row, bot_row, strict=True)
            )
            sys.stdout.write(term.move_xy(0, y // 2))
            sys.stdout.write(line)

        # Reset and flush. Moving to (0, 0) prevents flicker by avoiding the jump to the *next* line.
        sys.stdout.write(term.move_xy(0, 0) + term.normal + "\n")
        sys.stdout.flush()

    def _rc_set_logical_size(self, width, height):
        pass  # we ignore setting the size, we simply take the full size of the window

    def _rc_close(self):
        self._closed = True

    def _rc_get_closed(self):
        return self._closed

    def _rc_set_title(self, title):
        pass

    def _rc_set_cursor(self, cursor):
        pass


# Make available under a common name
loop = loop
RenderCanvas = TerminalRenderCanvas
