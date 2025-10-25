"""
Support to render in a glfw window. The advantage of glfw is that it's
very lightweight.

Install pyGLFW using ``pip install glfw``. On Windows this is enough.
On Linux, install the glfw lib using ``sudo apt install libglfw3``,
or ``sudo apt install libglfw3-wayland`` when using Wayland.
"""

__all__ = ["GlfwRenderCanvas", "RenderCanvas", "loop"]

import sys
import time

import glfw

from .base import BaseRenderCanvas, BaseCanvasGroup
from .asyncio import loop
from ._coreutils import SYSTEM_IS_WAYLAND, weakbind, logger


# Make sure that glfw is new enough
glfw_version_info = tuple(int(i) for i in glfw.__version__.split(".")[:2])
if glfw_version_info < (1, 9):
    raise ImportError("rendercanvas requires glfw 1.9 or higher.")

# Do checks to prevent pitfalls on hybrid Xorg/Wayland systems
api_is_wayland = False
if sys.platform.startswith("linux") and SYSTEM_IS_WAYLAND:
    if not hasattr(glfw, "get_x11_window"):
        # Probably glfw was imported before this module, so we missed our chance
        # to set the env var to make glfw use x11.
        api_is_wayland = True
        logger.warning("Using GLFW with Wayland, which is experimental.")


# Some glfw functions are not always available
set_window_content_scale_callback = lambda *args: None
set_window_maximize_callback = lambda *args: None
get_window_content_scale = lambda *args: (1, 1)

if hasattr(glfw, "set_window_content_scale_callback"):
    set_window_content_scale_callback = glfw.set_window_content_scale_callback
if hasattr(glfw, "set_window_maximize_callback"):
    set_window_maximize_callback = glfw.set_window_maximize_callback
if hasattr(glfw, "get_window_content_scale"):
    get_window_content_scale = glfw.get_window_content_scale


# Map keys to JS key definitions
# https://www.glfw.org/docs/3.3/group__keys.html
# https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key/Key_Values
KEY_MAP = {
    glfw.KEY_DOWN: "ArrowDown",
    glfw.KEY_UP: "ArrowUp",
    glfw.KEY_LEFT: "ArrowLeft",
    glfw.KEY_RIGHT: "ArrowRight",
    glfw.KEY_BACKSPACE: "Backspace",
    glfw.KEY_CAPS_LOCK: "CapsLock",
    glfw.KEY_DELETE: "Delete",
    glfw.KEY_END: "End",
    glfw.KEY_ENTER: "Enter",  # aka return
    glfw.KEY_ESCAPE: "Escape",
    glfw.KEY_F1: "F1",
    glfw.KEY_F2: "F2",
    glfw.KEY_F3: "F3",
    glfw.KEY_F4: "F4",
    glfw.KEY_F5: "F5",
    glfw.KEY_F6: "F6",
    glfw.KEY_F7: "F7",
    glfw.KEY_F8: "F8",
    glfw.KEY_F9: "F9",
    glfw.KEY_F10: "F10",
    glfw.KEY_F11: "F11",
    glfw.KEY_F12: "F12",
    glfw.KEY_HOME: "Home",
    glfw.KEY_INSERT: "Insert",
    glfw.KEY_LEFT_ALT: "Alt",
    glfw.KEY_LEFT_CONTROL: "Control",
    glfw.KEY_LEFT_SHIFT: "Shift",
    glfw.KEY_LEFT_SUPER: "Meta",  # in glfw super means Windows or MacOS-command
    glfw.KEY_NUM_LOCK: "NumLock",
    glfw.KEY_PAGE_DOWN: "PageDown",
    glfw.KEY_PAGE_UP: "PageUp",
    glfw.KEY_PAUSE: "Pause",
    glfw.KEY_PRINT_SCREEN: "PrintScreen",
    glfw.KEY_RIGHT_ALT: "Alt",
    glfw.KEY_RIGHT_CONTROL: "Control",
    glfw.KEY_RIGHT_SHIFT: "Shift",
    glfw.KEY_RIGHT_SUPER: "Meta",
    glfw.KEY_SCROLL_LOCK: "ScrollLock",
    glfw.KEY_TAB: "Tab",
}

KEY_MAP_MOD = {
    glfw.KEY_LEFT_SHIFT: "Shift",
    glfw.KEY_RIGHT_SHIFT: "Shift",
    glfw.KEY_LEFT_CONTROL: "Control",
    glfw.KEY_RIGHT_CONTROL: "Control",
    glfw.KEY_LEFT_ALT: "Alt",
    glfw.KEY_RIGHT_ALT: "Alt",
    glfw.KEY_LEFT_SUPER: "Meta",
    glfw.KEY_RIGHT_SUPER: "Meta",
}

CURSOR_MAP = {
    "default": None,
    # "arrow": glfw.ARROW_CURSOR,  # CSS only has 'default', not 'arrow'
    "text": glfw.IBEAM_CURSOR,
    "crosshair": glfw.CROSSHAIR_CURSOR,
    "pointer": glfw.POINTING_HAND_CURSOR,
    "ew-resize": glfw.RESIZE_EW_CURSOR,
    "ns-resize": glfw.RESIZE_NS_CURSOR,
    "nesw-resize": glfw.RESIZE_NESW_CURSOR,
    "nwse-resize": glfw.RESIZE_NWSE_CURSOR,
    # "": glfw.RESIZE_ALL_CURSOR,  # Looks like 'grabbing' in CSS
    "not-allowed": glfw.NOT_ALLOWED_CURSOR,
    "none": None,  # handled in method
}


def get_glfw_present_methods(window):
    if sys.platform.startswith("win"):
        return {
            "screen": {
                "platform": "windows",
                "window": int(glfw.get_win32_window(window)),
            }
        }
    elif sys.platform.startswith("darwin"):
        return {
            "screen": {
                "platform": "cocoa",
                "window": int(glfw.get_cocoa_window(window)),
            }
        }
    elif sys.platform.startswith("linux"):
        if api_is_wayland:
            return {
                "screen": {
                    "platform": "wayland",
                    "window": int(glfw.get_wayland_window(window)),
                    "display": int(glfw.get_wayland_display()),
                }
            }
        else:
            return {
                "screen": {
                    "platform": "x11",
                    "window": int(glfw.get_x11_window(window)),
                    "display": int(glfw.get_x11_display()),
                }
            }
    else:
        raise RuntimeError(f"Cannot get GLFW surface info on {sys.platform}.")


def get_physical_size(window):
    psize = glfw.get_framebuffer_size(window)
    return int(psize[0]), int(psize[1])


def enable_glfw():
    glfw.init()  # this also resets all window hints
    glfw._rc_alive = True


class GlfwCanvasGroup(BaseCanvasGroup):
    glfw = glfw  # make sure we can access the glfw module in the __del__

    def __del__(self):
        # Because this object is used as a class attribute (on the canvas), this
        # __del__ method gets called later than a function registed to atexit.
        # This is important when used in combination with wgpu, where the release of the surface
        # should happen before the termination of glfw. On some systems this can otherwiser
        # result in a segfault, see https://github.com/pygfx/pygfx/issues/642
        try:
            self.glfw._rc_alive = False
            self.glfw.terminate()
        except Exception:
            pass
        try:
            super().__del__()
        except Exception:
            pass  # object has no __del__


class GlfwRenderCanvas(BaseRenderCanvas):
    """A glfw window providing a render canvas."""

    # See https://www.glfw.org/docs/latest/group__window.html

    _rc_canvas_group = GlfwCanvasGroup(loop)

    def __init__(self, *args, present_method=None, **kwargs):
        enable_glfw()
        super().__init__(*args, **kwargs)

        if present_method == "bitmap":
            logger.warning(
                "Ignoring present_method 'bitmap'; glfw can only render to screen"
            )

        # Set window hints
        glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)
        glfw.window_hint(glfw.RESIZABLE, True)
        glfw.window_hint(glfw.VISIBLE, False)  # start hidden

        # Create the window (the initial size may not be in logical pixels)
        self._window = glfw.create_window(640, 480, "", None, None)

        # Other internal variables
        self._changing_pixel_ratio = False
        self._is_minimized = False
        self._is_in_poll_events = False
        self._cursor_object = None

        # Register callbacks. We may get notified too often, but that's
        # ok, they'll result in a single draw.
        glfw.set_framebuffer_size_callback(self._window, weakbind(self._on_size_change))
        glfw.set_window_close_callback(self._window, weakbind(self._on_want_close))
        glfw.set_window_refresh_callback(self._window, weakbind(self._on_window_dirty))
        glfw.set_window_focus_callback(self._window, weakbind(self._on_window_dirty))
        set_window_content_scale_callback(
            self._window, weakbind(self._on_pixelratio_change)
        )
        set_window_maximize_callback(self._window, weakbind(self._on_window_dirty))
        glfw.set_window_iconify_callback(self._window, weakbind(self._on_iconify))

        # User input
        self._key_modifiers = ()
        self._pointer_buttons = ()
        self._pointer_pos = 0, 0
        self._pointer_inside = None
        self._pointer_lock = False
        self._double_click_state = {"clicks": 0}
        glfw.set_mouse_button_callback(self._window, weakbind(self._on_mouse_button))
        glfw.set_cursor_pos_callback(self._window, weakbind(self._on_cursor_pos))
        glfw.set_cursor_enter_callback(self._window, weakbind(self._on_cursor_enter))
        glfw.set_scroll_callback(self._window, weakbind(self._on_scroll))
        glfw.set_key_callback(self._window, weakbind(self._on_key))
        glfw.set_char_callback(self._window, weakbind(self._on_char))

        # Initialize the size
        self._pixel_ratio = -1
        self._screen_size_is_logical = False

        # Set size, title, etc.
        self._determine_size()
        self._final_canvas_init()

        # Now show the window
        glfw.show_window(self._window)

    def _on_window_dirty(self, *args):
        self.request_draw()

    def _on_iconify(self, window, iconified):
        self._is_minimized = bool(iconified)
        if not self._is_minimized:
            self._rc_request_draw()

    def _determine_size(self):
        if self._window is None:
            return
        # Note: On Wayland  glfw.get_window_content_scale() produces (1.0, 1.0) regardless of the OS settings.

        # Because the value of get_window_size is in physical-pixels
        # on some systems and in logical-pixels on other, we use the
        # framebuffer size and pixel ratio to derive the logical size.
        pixel_ratio = get_window_content_scale(self._window)[0]
        psize = get_physical_size(self._window)

        self._pixel_ratio = pixel_ratio  # store
        self._set_size_info(psize, pixel_ratio)

    def _on_want_close(self, *args):
        # Called when the user attempts to close the window, for example by clicking the close widget in the title bar.
        # We could prevent closing the window here. But we don't :)
        pass  # Prevent closing: glfw.set_window_should_close(self._window, 0)

    def _maybe_close(self):
        if self._window is not None:
            if glfw.window_should_close(self._window):
                self.close()

    def _set_logical_size(self, new_logical_size):
        if self._window is None:
            return
        # There is unclarity about the window size in "screen pixels".
        # It appears that on Windows and X11 its the same as the
        # framebuffer size, and on macOS it's logical pixels.
        # See https://github.com/glfw/glfw/issues/845
        # Here, we simply do a quick test so we can compensate.

        # The current screen size and physical size, and its ratio
        pixel_ratio = get_window_content_scale(self._window)[0]
        ssize = glfw.get_window_size(self._window)
        psize = glfw.get_framebuffer_size(self._window)

        # Apply
        screen_ratio = ssize[0] / psize[0]
        glfw.set_window_size(
            self._window,
            int(new_logical_size[0] * pixel_ratio * screen_ratio),
            int(new_logical_size[1] * pixel_ratio * screen_ratio),
        )
        self._screen_size_is_logical = screen_ratio != 1

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        glfw.post_empty_event()  # Awake the event loop, if it's in wait-mode
        try:
            self._is_in_poll_events = True
            glfw.poll_events()  # Note: this blocks when the window is being resized
        finally:
            self._is_in_poll_events = False
        self._maybe_close()

    def _rc_get_present_methods(self):
        return get_glfw_present_methods(self._window)

    def _rc_request_draw(self):
        if not self._is_minimized:
            loop = self._rc_canvas_group.get_loop()
            loop.call_soon(self._draw_frame_and_present)

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, **kwargs):
        raise NotImplementedError()
        # AFAIK glfw does not have a builtin way to blit an image. It also does
        # not really need one, since it's the most reliable backend to
        # render to the screen.

    def _rc_set_logical_size(self, width, height):
        if width < 0 or height < 0:
            raise ValueError("Window width and height must not be negative")
        self._set_logical_size((float(width), float(height)))

    def _rc_close(self):
        if self._window is not None:
            glfw.destroy_window(self._window)  # not just glfw.hide_window
            self._window = None
            self.submit_event({"event_type": "close"})
        # If this is the last canvas to close, the loop will stop, and glfw will not be polled anymore.
        # But on some systems glfw needs a bit of time to properly close the window.
        if not self._rc_canvas_group.get_canvases():
            poll_glfw_briefly(0.05)

    def _rc_get_closed(self):
        return self._window is None

    def _rc_set_title(self, title):
        if self._window is not None:
            glfw.set_window_title(self._window, title)

    def _rc_set_cursor(self, cursor):
        if self._cursor_object is not None:
            glfw.destroy_cursor(self._cursor_object)
            self._cursor_object = None

        cursor_flag = CURSOR_MAP.get(cursor)
        if cursor == "none":
            # Create a custom cursor that's simply empty
            image = memoryview(bytearray(8 * 8 * 4))
            image = image.cast("B", shape=(8, 8, 4))
            image_for_glfw_wrapper = image.shape[1], image.shape[0], image.tolist()
            self._cursor_object = glfw.create_cursor(image_for_glfw_wrapper, 0, 0)
        elif cursor_flag is None:
            # The default (arrow)
            self._cursor_object = None
        else:
            self._cursor_object = glfw.create_standard_cursor(cursor_flag)

        glfw.set_cursor(self._window, self._cursor_object)

    # %% Turn glfw events into rendercanvas events

    def _on_pixelratio_change(self, *args):
        if self._changing_pixel_ratio:
            return
        self._changing_pixel_ratio = True  # prevent recursion (on Wayland)
        try:
            self._set_logical_size(self.get_logical_size())
            self._determine_size()
        finally:
            self._changing_pixel_ratio = False
        self.request_draw()

    def _on_size_change(self, *args):
        self._determine_size()
        self.request_draw()
        # During a resize, the glfw.poll_events() function blocks, so
        # our event-loop is on pause. However, glfw still sends resize
        # events, and we can use these to draw, to get a smoother
        # experience. Note that if the user holds the mouse still while
        # resizing, there are no draws. Also note that any animations
        # that rely on the event-loop are paused (only animations
        # updated in the draw callback are alive).
        if self._is_in_poll_events and not self._is_minimized:
            self._draw_frame_and_present()

    def _on_mouse_button(self, window, but, action, mods):
        # Map button being changed, which we use to update self._pointer_buttons.
        button_map = {
            glfw.MOUSE_BUTTON_1: 1,  # == MOUSE_BUTTON_LEFT
            glfw.MOUSE_BUTTON_2: 2,  # == MOUSE_BUTTON_RIGHT
            glfw.MOUSE_BUTTON_3: 3,  # == MOUSE_BUTTON_MIDDLE
            glfw.MOUSE_BUTTON_4: 4,
            glfw.MOUSE_BUTTON_5: 5,
            glfw.MOUSE_BUTTON_6: 6,
            glfw.MOUSE_BUTTON_7: 7,
            glfw.MOUSE_BUTTON_8: 8,
        }
        button = button_map.get(but, 0)

        # Handler pointer locking
        if self._pointer_lock:
            if action == glfw.RELEASE:
                self._pointer_lock = False
            return
        elif not self._pointer_inside:
            if action == glfw.PRESS:
                # This press is to select the window (regaining focus)
                self._pointer_lock = True
                return

        if action == glfw.PRESS:
            event_type = "pointer_down"
            buttons = set(self._pointer_buttons)
            buttons.add(button)
            self._pointer_buttons = tuple(sorted(buttons))
        elif action == glfw.RELEASE:
            event_type = "pointer_up"
            buttons = set(self._pointer_buttons)
            buttons.discard(button)
            self._pointer_buttons = tuple(sorted(buttons))
        else:
            return

        ev = {
            "event_type": event_type,
            "x": self._pointer_pos[0],
            "y": self._pointer_pos[1],
            "button": button,
            "buttons": tuple(self._pointer_buttons),
            "modifiers": tuple(self._key_modifiers),
            "ntouches": 0,  # glfw does not have touch support
            "touches": {},
        }

        # Emit the current event
        self.submit_event(ev)

        # Maybe emit a double-click event
        self._follow_double_click(action, button)

    def _follow_double_click(self, action, button):
        # If a sequence of down-up-down-up is made in nearly the same
        # spot, and within a short time, we emit the double-click event.

        if self._pointer_lock:
            return

        x, y = self._pointer_pos[0], self._pointer_pos[1]
        state = self._double_click_state

        timeout = 0.25
        distance = 5

        # Clear the state if it does no longer match
        if state["clicks"] > 0:
            d = ((x - state["x"]) ** 2 + (y - state["y"]) ** 2) ** 0.5
            if (
                d > distance
                or time.perf_counter() - state["time"] > timeout
                or button != state["button"]
            ):
                self._double_click_state = {"clicks": 0}

        clicks = self._double_click_state["clicks"]

        # Check and update order. Emit event if we make it to the final step
        if clicks == 0 and action == glfw.PRESS:
            self._double_click_state = {
                "clicks": 1,
                "button": button,
                "time": time.perf_counter(),
                "x": x,
                "y": y,
            }
        elif clicks == 1 and action == glfw.RELEASE:
            self._double_click_state["clicks"] = 2
        elif clicks == 2 and action == glfw.PRESS:
            self._double_click_state["clicks"] = 3
        elif clicks == 3 and action == glfw.RELEASE:
            self._double_click_state = {"clicks": 0}
            ev = {
                "event_type": "double_click",
                "x": self._pointer_pos[0],
                "y": self._pointer_pos[1],
                "button": button,
                "buttons": tuple(self._pointer_buttons),
                "modifiers": tuple(self._key_modifiers),
                "ntouches": 0,  # glfw does not have touch support
                "touches": {},
            }
            self.submit_event(ev)

    def _on_cursor_pos(self, window, x, y):
        if self._pointer_lock:
            return

        # Maybe trigger initial enter
        if self._pointer_inside is None:
            if glfw.get_window_attrib(window, glfw.HOVERED):
                self._on_cursor_enter(window, True)

        # Only process move events if inside or if drag-tracking
        if not (self._pointer_inside or self._pointer_buttons):
            return

        # Store pointer position in logical coordinates
        if self._screen_size_is_logical:
            self._pointer_pos = x, y
        else:
            self._pointer_pos = x / self._pixel_ratio, y / self._pixel_ratio

        ev = {
            "event_type": "pointer_move",
            "x": self._pointer_pos[0],
            "y": self._pointer_pos[1],
            "button": 0,
            "buttons": tuple(self._pointer_buttons),
            "modifiers": tuple(self._key_modifiers),
            "ntouches": 0,  # glfw does not have touch support
            "touches": {},
        }

        self.submit_event(ev)

    def _on_cursor_enter(self, window, entered):
        self._pointer_inside = bool(entered)
        ev = {"event_type": "pointer_enter" if entered else "pointer_leave"}
        self.submit_event(ev)

    def _on_scroll(self, window, dx, dy):
        # wheel is 1 or -1 in glfw, in jupyter_rfb this is ~100
        ev = {
            "event_type": "wheel",
            "dx": 100.0 * dx,
            "dy": -100.0 * dy,
            "x": self._pointer_pos[0],
            "y": self._pointer_pos[1],
            "buttons": tuple(self._pointer_buttons),
            "modifiers": tuple(self._key_modifiers),
        }
        self.submit_event(ev)

    def _on_key(self, window, key, scancode, action, mods):
        modifier = KEY_MAP_MOD.get(key, None)

        if action == glfw.PRESS:
            event_type = "key_down"
            if modifier:
                modifiers = set(self._key_modifiers)
                modifiers.add(modifier)
                self._key_modifiers = tuple(sorted(modifiers))
        elif action == glfw.RELEASE:
            event_type = "key_up"
            if modifier:
                modifiers = set(self._key_modifiers)
                modifiers.discard(modifier)
                self._key_modifiers = tuple(sorted(modifiers))
        else:  # glfw.REPEAT
            return

        # Note that if the user holds shift while pressing "5", will result in "5",
        # and not in the "%" that you'd expect on a US keyboard. Glfw wants us to
        # use set_char_callback for text input, but then we'd only get an event for
        # key presses (down followed by up). So we accept that GLFW is less complete
        # in this respect.
        if key in KEY_MAP:
            keyname = KEY_MAP[key]
        else:
            try:
                keyname = chr(key)
            except ValueError:
                return  # Probably a special key that we don't have in our KEY_MAP
            if "Shift" not in self._key_modifiers:
                keyname = keyname.lower()

        ev = {
            "event_type": event_type,
            "key": keyname,
            "modifiers": tuple(self._key_modifiers),
        }

        if not action == glfw.REPEAT:
            self.submit_event(ev)

    def _on_char(self, window, char):
        # Undocumented char event to make imgui work, see https://github.com/pygfx/wgpu-py/issues/530
        ev = {
            "event_type": "char",
            "char_str": chr(char),
            "modifiers": tuple(self._key_modifiers),
        }
        self.submit_event(ev)


def poll_glfw_briefly(poll_time=0.1):
    """Briefly poll glfw for a set amount of time.
    Intended to work around the bug that destroyed windows sometimes hang
    around if the mainloop exits: https://github.com/glfw/glfw/issues/1766
    I found that 10ms is enough, but make it 100ms just in case. You should
    only run this right after your mainloop stops.
    """
    if not glfw._rc_alive:
        return
    end_time = time.perf_counter() + poll_time
    while time.perf_counter() < end_time:
        glfw.wait_events_timeout(end_time - time.perf_counter())


# Make available under a name that is the same for all backends
loop = loop  # default loop is AsyncioLoop
RenderCanvas = GlfwRenderCanvas
