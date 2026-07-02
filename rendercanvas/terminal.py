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
            term.enable_kitty_keyboard(
                report_events=True,
                report_all_keys=True,
                report_alternates=True,
                report_text=True,
            ),
            term.cbreak(),
            term.mouse_enabled(report_motion=True),
            set_pointer_to_arrow(),
        ):
            super()._rc_run()


loop = TerminalLoop()


class TerminalCanvasGroup(BaseCanvasGroup):
    pass


class TerminalRenderCanvas(BaseRenderCanvas):
    """A canvas that renders in the terminal.

    Arguments:
        pixel_ratio : float
            The (initial) ratio that determines the logical size of the window. Default 0.25; the pixels are huge!

    Restrictions of this backend:

    * Obviously the resolution is very low: 2 pixels (vertically) per character.
    * Limited support for modifiers in pointer and key events (only Shift).
    * The experience may differ depending on the terminal you're at.

    """

    _rc_canvas_group = TerminalCanvasGroup(loop)

    def __init__(self, *args, pixel_ratio=0.25, **kwargs):
        super().__init__(*args, **kwargs)

        # NOTE: it is assumed that there is exactly one canvas. If this assumption is violated I guess they will alternately flicker.

        self._pixel_ratio = pixel_ratio

        self._closed = False
        self._term_size = 0, 0
        self._pointer_pos = (0, 0)
        self._pointer_buttons = ()
        self._pressed_keys = {}

        self._rc_gui_poll()
        self._final_canvas_init()

        # Start with a pointer enter event
        self.submit_event({"event_type": "pointer_enter"})

    def set_pixel_ratio(self, pixel_ratio: float):
        """Set the pixel ratio, changing the logical size of the canvas.

        Since each character represents only 2 (vertical) pixels, the total
        number of pixels is very small. A pixel_ratio of 1/8 is likely most
        realistic (since text chars are typically 8 pixels wide). However, to be
        able to read any rendered text you'll want a pixel_ratio of about 1, but
        then the visualization may appear very much zoomed in. In other words,
        the optimal pixel ratio for the terminal backend depends on the
        application.

        Therefore, the pixel ratio can be changed using a button at the
        top-right of the screen, or programmatically using this method.
        """
        self._pixel_ratio = float(pixel_ratio)
        pwidth, pheight = self.get_physical_size()
        self._size_info.set_physical_size(pwidth, pheight, self._pixel_ratio)
        self.request_draw()

    def _rc_gui_poll(self):
        # Check for resize
        term_size = term.width, term.height
        if term_size != self._term_size:
            self._term_size = term_size
            # Determine physical size. Each char is two vertical pixels. Have a margin to avoid jump artifacts.
            pwidth = term_size[0]
            pheight = term_size[1] * 2
            self._size_info.set_physical_size(pwidth, pheight, self._pixel_ratio)
            self.request_draw()

        # Check for key/mouse pressed. Read buffered events until the buffer is empty.
        while True:
            keystroke = term.inkey(timeout=0)
            if not keystroke:
                break
            stroke_name = keystroke.name or ""

            if stroke_name.startswith("MOUSE_SCROLL_"):
                delta = 200  # empirically determined. Can adjust.
                if stroke_name.endswith("UP"):
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

            elif stroke_name.startswith("MOUSE_"):
                # Get pos
                term_x, term_y = keystroke.mouse_xy
                x = float(term_x) / self._pixel_ratio
                y = float(term_y) * 2 / self._pixel_ratio
                self._pointer_pos = x, y
                # Get kind
                if "MOTION" in stroke_name:
                    kind = "move"
                elif "RELEASED" in stroke_name:
                    kind = "up"
                else:
                    kind = "down"
                # Get button and buttons. We ignore that buttons can be clicked when other buttons are down
                button = 0
                if "LEFT" in stroke_name:
                    button = 1
                elif "RIGHT" in stroke_name:
                    button = 2
                elif "MIDDLE" in stroke_name:
                    button = 3
                buttons = () if kind == "up" else (button,)
                self._pointer_buttons = buttons
                # Modifiers
                modifiers = []
                if "SHIFT" in stroke_name:
                    modifiers.append("Shift")
                # Exit when the cross in the top-right is clicked
                if (
                    kind == "down"
                    and button == 1
                    and term_y == 0
                    and term_x >= self._term_size[0] - 4
                ):
                    if term_x == self._term_size[0] - 4:
                        p = round(np.log2(self._pixel_ratio))
                        self.set_pixel_ratio(2 ** (p - 1))
                    elif term_x == self._term_size[0] - 3:
                        p = round(np.log2(self._pixel_ratio))
                        self.set_pixel_ratio(2 ** (p + 1))
                    elif term_x == self._term_size[0] - 1:
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
                key_name = keystroke.key_name
                # self.set_title(
                #     f"{stroke_name} | {key_name} | {keystroke.value!r}  repeated: {keystroke.repeated} pressed: {keystroke.pressed}"
                # )
                # The application exits on Control-C, we could also exit on escape, but escape may be an application event.
                if stroke_name == "KEY_CTRL_C":
                    loop.stop()
                # Get key
                if key_name:
                    key = KEY_MAP.get(key_name, "")
                if not key:
                    key = keystroke.value
                if not key:
                    key = key_name.split("_")[-1].lower()
                    if len(key) != 1:
                        key = ""
                # Modifiers
                modifiers = []
                if "SHIFT" in stroke_name:
                    modifiers.append("Shift")
                # Handle repeat and release
                if keystroke.repeated:
                    continue  # repeat for arrow keys etc.
                elif keystroke.pressed and key:
                    event_type = "key_down"
                    if key_name in self._pressed_keys:
                        continue  # repeat for character keys etc
                    else:
                        self._pressed_keys[key_name] = key
                elif not keystroke.pressed:
                    event_type = "key_up"
                    key = self._pressed_keys.pop(key_name, None) or key
                # Submit event
                if key:
                    ev = {
                        "event_type": event_type,
                        "key": key,
                        "modifiers": tuple(modifiers),
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
        # Get 8bit image
        if format == "rgba-f16":
            img = np.rint(data)
            np.clip(img, 0, 255, out=img)
            img = img.astype(np.uint8)
        elif format == "rgba-u16":
            img = data // 256
            img = img.astype(np.uint8)
        else:  # format == "rgba-u8":
            img = data

        # Push lines to stdout
        for y in range(0, img.shape[0], 2):
            top_row = img[y][:, :3]
            bot_row = img[y + 1][:, :3]
            line = "".join(
                term.on_color_rgb(*rgb1) + term.color_rgb(*rgb2) + "▄"
                for rgb1, rgb2 in zip(top_row, bot_row, strict=True)
            )
            term_stream.write(term.move_xy(0, y // 2) + line)
            # Show close button on the first line. Do here rather then at end to avoid flicker.
            if y == 0:
                s = f"ratio {self._pixel_ratio:0.4g} -+ ×"  # noqa: RUF001
                term_stream.write(
                    term.normal + term.move_xy(img.shape[1] - len(s), 0) + s
                )

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
