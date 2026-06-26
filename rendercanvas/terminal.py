"""
Support for rendering in a terminal session, using the blessed library.
"""

# Dev notes:
#
# I've chosen to use the half-block rendering approach to increase the vertical
# resolution and have more or less square pixels. I've not used sixels, since
# they are subject to a 256 color palette, which can look bad, but also incurs
# additional CPU processing.
#
# The key events are not great. Looks like with kitty keystrokes it can be
# improved but I had limited success, so I decided to just keep it simple. The
# pointer events are much better, but e.g. RMB and most modifier keys except shift
# are consumed by the terminal app for context menu etc.

__all__ = ["RenderCanvas", "TerminalRenderCanvas", "loop"]


import io
import sys
from contextlib import contextmanager

from .base import BaseCanvasGroup, BaseRenderCanvas
from .asyncio import AsyncioLoop

import numpy as np
import blessed


# Store streams
term_stream = sys.__stdout__
original_stdout = sys.stdout
original_stderr = sys.stderr

# Blessed exposes all it's API via a single terminal object
term = blessed.Terminal(stream=term_stream)


@contextmanager
def captured_stdout_and_stderr():
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    sys.stdout = buf_out
    sys.stderr = buf_err
    try:
        yield
    finally:
        term_stream.flush()
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        original_stdout.write(buf_out.getvalue())
        original_stderr.write(buf_err.getvalue())


@contextmanager
def set_pointer_to_arrow():
    does_pointer = term.does_kitty_pointer_shapes()
    if does_pointer:
        sys.stdout.write("\033]22;default\007")  # arrow pointer
    try:
        yield
    finally:
        if does_pointer:
            sys.stdout.write("\033]22;\007")  # reset to terminal default


KEY_MAP = {
    "KEY_DOWN": "ArrowDown",
    "KEY_UP": "ArrowUp",
    "KEY_LEFT": "ArrowLeft",
    "KEY_RIGHT": "ArrowRight",
    "KEY_BACKSPACE": "Backspace",
    "KEY_": "CapsLock",
    "KEY_DELETE": "Delete",
    "KEY_END": "End",
    "KEY_ENTER": "Enter",  # aka return
    "KEY_ESCAPE": "Escape",
    "KEY_F1": "F1",
    "KEY_F2": "F2",
    "KEY_F3": "F3",
    "KEY_F4": "F4",
    "KEY_F5": "F5",
    "KEY_F6": "F6",
    "KEY_F7": "F7",
    "KEY_F8": "F8",
    "KEY_F9": "F9",
    "KEY_F10": "F10",
    "KEY_F11": "F11",
    "KEY_F12": "F12",
    "KEY_HOME": "Home",
    "KEY_INSERT": "Insert",
    "KEY_ALT": "Alt",
    # "KEY_CONTROL": "Control",
    "KEY_COMMAND": "Control",
    # "KEY_SHIFT": "Shift",
    # "KEY_META": "Meta",
    "KEY_NUM_LOCK": "NumLock",
    "KEY_PGDOWN": "PageDown",
    "KEY_PGUP": "PageUp",
    "KEY_PAUSE": "Pause",
    "KEY_PRINT_SCREEN": "PrintScreen",
    # "KEY_ALT": "Alt",
    "KEY_SCROLL_LOCK": "ScrollLock",
    "KEY_TAB": "Tab",
}


class TerminalLoop(AsyncioLoop):
    def _rc_run(self):
        with (
            term.fullscreen(),
            term.hidden_cursor(),
            captured_stdout_and_stderr(),
            term.cbreak(),
            term.mouse_enabled(report_motion=True),
            set_pointer_to_arrow(),
        ):
            super()._rc_run()


loop = TerminalLoop()


class TerminalCanvasGroup(BaseCanvasGroup):
    pass


class TerminalRenderCanvas(BaseRenderCanvas):
    """A canvas that enders in the terminal.

    Restrictions:

    * Obviously the resolution is very low: 2 pixels (vertically) per character.
    * Only key_down events, no key_up.
    * No support for modifiers with key events.
    * Limited support for modifiers in pointer events (only Shift).
    * The experience may differ depending on the terminal you're at.

    """

    _rc_canvas_group = TerminalCanvasGroup(loop)

    def __init__(self, *args, pixel_ratio=0.25, upscale_factor=1, **kwargs):
        super().__init__(*args, **kwargs)

        # NOTE: it is assumed that there is exactly one canvas. If this assumption is violated I guess they will alternately flicker.

        self._pixel_ratio = max(1 / 32, float(pixel_ratio))
        self._upscale_factor = max(1, int(upscale_factor))

        self._closed = False
        self._term_size = 0, 0
        self._pointer_pos = (0, 0)
        self._pointer_buttons = ()

        self._rc_gui_poll()
        self._final_canvas_init()

        # Start with a pointer enter event
        self.submit_event({"event_type": "pointer_enter"})

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

        # Check for key/mouse pressed. Read buffered events until the buffer is empty.
        while keystroke := term.inkey(timeout=0):
            if keystroke.name and keystroke.name.startswith("MOUSE_SCROLL_"):
                delta = 200  # empirically determined. Can adjust.
                if keystroke.name.endswith("UP"):
                    delta = -delta
                ev = {
                    "event_type": "wheel",
                    "dx": 0,
                    "dy": delta,
                    "x": self._pointer_pos[0],
                    "y": self._pointer_pos[1],
                    "buttons": tuple(self._pointer_buttons),
                    "modifiers": tuple(),
                }
                self.submit_event(ev)

            elif keystroke.name and keystroke.name.startswith("MOUSE_"):
                key_name = keystroke.name
                # Get pos
                term_x, term_y = keystroke.mouse_xy
                x = float(term_x) / self._pixel_ratio
                y = float(term_y) * 2 / self._pixel_ratio
                self._pointer_pos = x, y
                # Get kind
                if "MOTION" in key_name:
                    kind = "move"
                elif "RELEASED" in key_name:
                    kind = "up"
                else:
                    kind = "down"
                # Get button and buttons. We ignore that buttons can be clicked when other buttons are down
                button = 0
                if "LEFT" in key_name:
                    button = 1
                elif "RIGHT" in key_name:
                    button = 2
                elif "MIDDLE" in key_name:
                    button = 3
                buttons = () if kind == "up" else (button,)
                self._pointer_buttons = buttons
                # Modifiers
                modifiers = []
                if "SHIFT" in key_name:
                    modifiers.append("Shift")
                # Exit when the cross in the top-right is clicked
                if (
                    kind == "down"
                    and button == 1
                    and term_y == 0
                    and term_x == self._term_size[0] - 1
                ):
                    loop.stop()
                # Submit!
                ev = {
                    "event_type": f"pointer_{kind}",
                    "x": x,
                    "y": y,
                    "button": button,
                    "buttons": buttons,
                    "modifiers": tuple(modifiers),
                    "ntouches": 0,
                    "touches": {},
                }
                self.submit_event(ev)
            else:
                # The application exits on Control-C, we could also exit on escape, but escape may be an application event.
                # if keystroke.key_name == "KEY_ESCAPE":
                #     loop.stop()
                # Get key
                if keystroke.key_name:
                    key = KEY_MAP.get(keystroke.key_name, "")
                else:
                    key = keystroke.value
                # Submit event. Modifiers are tricky, I guess we ignore them
                if key:
                    ev = {
                        "event_type": "key_down",
                        "key": key,
                        "modifiers": tuple(),
                    }
                    self.submit_event(ev)

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
            term_stream.write(term.move_xy(0, y // 2) + line)
            # Show title and close button on the first line. Do here to avoid flicker.
            if y == 0:
                term_stream.write(term.normal + term.move_xy(img.shape[1] - 1, 0) + "×")  # noqa: RUF001

        # Reset and flush. Moving to (0, 0) prevents jump-flicker by avoiding the jump to the *next* line.
        term_stream.write(term.normal + term.move_xy(0, 0) + "\n")
        term_stream.flush()

    def _rc_set_logical_size(self, width, height):
        pass  # we ignore setting the size, we simply take the full size of the window

    def _rc_close(self):
        self._closed = True

    def _rc_get_closed(self):
        return self._closed

    def _rc_set_title(self, title):
        term_stream.write(term.set_window_title(title) + "\n")

    def _rc_set_cursor(self, cursor):
        pass


# Make available under a common name
loop = loop
RenderCanvas = TerminalRenderCanvas
