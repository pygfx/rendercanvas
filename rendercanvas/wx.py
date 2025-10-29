"""
Support for rendering in a wxPython window. Provides a widget that
can be used as a standalone window or in a larger GUI.
"""

__all__ = ["RenderCanvas", "WxLoop", "WxRenderCanvas", "WxRenderWidget", "loop"]

import sys
import time
import ctypes
from typing import Optional

import wx

from ._coreutils import (
    logger,
    SYSTEM_IS_WAYLAND,
    get_alt_x11_display,
    get_alt_wayland_display,
)
from .base import (
    WrapperRenderCanvas,
    BaseRenderCanvas,
    BaseCanvasGroup,
    BaseLoop,
)


BUTTON_MAP = {
    wx.MOUSE_BTN_LEFT: 1,
    wx.MOUSE_BTN_RIGHT: 2,
    wx.MOUSE_BTN_MIDDLE: 3,
    wx.MOUSE_BTN_AUX1: 4,
    wx.MOUSE_BTN_AUX2: 5,
    # wxPython doesn't have exact equivalents for TaskButton, ExtraButton4, and ExtraButton5
}

MOUSE_EVENT_MAP = {
    "pointer_down": [
        wx.wxEVT_LEFT_DOWN,
        wx.wxEVT_MIDDLE_DOWN,
        wx.wxEVT_RIGHT_DOWN,
        wx.wxEVT_AUX1_DOWN,
        wx.wxEVT_AUX2_DOWN,
    ],
    "pointer_up": [
        wx.wxEVT_LEFT_UP,
        wx.wxEVT_MIDDLE_UP,
        wx.wxEVT_RIGHT_UP,
        wx.wxEVT_AUX1_UP,
        wx.wxEVT_AUX2_UP,
    ],
    "double_click": [
        wx.wxEVT_LEFT_DCLICK,
        wx.wxEVT_MIDDLE_DCLICK,
        wx.wxEVT_RIGHT_DCLICK,
        wx.wxEVT_AUX1_DCLICK,
        wx.wxEVT_AUX2_DCLICK,
    ],
    "wheel": [wx.wxEVT_MOUSEWHEEL],
}

# reverse the mouse event map (from one-to-many to many-to-one)
MOUSE_EVENT_MAP_REVERSED = {
    value: key for key, values in MOUSE_EVENT_MAP.items() for value in values
}

MODIFIERS_MAP = {
    wx.MOD_SHIFT: "Shift",
    wx.MOD_CONTROL: "Control",
    wx.MOD_ALT: "Alt",
    wx.MOD_META: "Meta",
}

KEY_MAP = {
    wx.WXK_DOWN: "ArrowDown",
    wx.WXK_UP: "ArrowUp",
    wx.WXK_LEFT: "ArrowLeft",
    wx.WXK_RIGHT: "ArrowRight",
    wx.WXK_BACK: "Backspace",
    wx.WXK_CAPITAL: "CapsLock",
    wx.WXK_DELETE: "Delete",
    wx.WXK_END: "End",
    wx.WXK_RETURN: "Enter",
    wx.WXK_ESCAPE: "Escape",
    wx.WXK_F1: "F1",
    wx.WXK_F2: "F2",
    wx.WXK_F3: "F3",
    wx.WXK_F4: "F4",
    wx.WXK_F5: "F5",
    wx.WXK_F6: "F6",
    wx.WXK_F7: "F7",
    wx.WXK_F8: "F8",
    wx.WXK_F9: "F9",
    wx.WXK_F10: "F10",
    wx.WXK_F11: "F11",
    wx.WXK_F12: "F12",
    wx.WXK_HOME: "Home",
    wx.WXK_INSERT: "Insert",
    wx.WXK_ALT: "Alt",
    wx.WXK_CONTROL: "Control",
    wx.WXK_SHIFT: "Shift",
    wx.WXK_COMMAND: "Meta",  # wx.WXK_COMMAND is used for Meta (Command key on macOS)
    wx.WXK_NUMLOCK: "NumLock",
    wx.WXK_PAGEDOWN: "PageDown",
    wx.WXK_PAGEUP: "PageUp",
    wx.WXK_PAUSE: "Pause",
    wx.WXK_SCROLL: "ScrollLock",
    wx.WXK_TAB: "Tab",
}

CURSOR_MAP = {
    "default": None,
    "text": wx.CURSOR_IBEAM,
    "crosshair": wx.CURSOR_CROSS,
    "pointer": wx.CURSOR_HAND,
    "ew-resize": wx.CURSOR_SIZEWE,
    "ns-resize": wx.CURSOR_SIZENS,
    "nesw-resize": wx.CURSOR_SIZENESW,
    "nwse-resize": wx.CURSOR_SIZENWSE,
    "not-allowed": wx.CURSOR_NO_ENTRY,
    "none": wx.CURSOR_BLANK,
}


def enable_hidpi():
    """Enable high-res displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass  # fail on non-windows


enable_hidpi()


_show_image_method_warning = (
    "wx falling back to offscreen rendering, which is less performant."
)


class TimerWithCallback(wx.Timer):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def Notify(self, *args):  # noqa: N802
        try:
            self._callback()
        except RuntimeError:
            pass  # wrapped C/C++ object of type WxRenderWidget has been deleted


class WxLoop(BaseLoop):
    _app = None

    def _rc_init(self):
        if self._app is None:
            self._app = wx.App.GetInstance()
            if self._app is None:
                self._app = wx.App()
                wx.App.SetInstance(self._app)

    def _rc_run(self):
        self._app.MainLoop()

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        # It looks like we cannot make wx stop the loop.
        # In general not a problem, because the BaseLoop will try
        # to close all windows before stopping a loop.
        pass

    def _rc_add_task(self, async_func, name):
        # we use the async adapter with call_later
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        wx.CallLater(max(int(delay * 1000), 1), callback)

    def process_wx_events(self):
        old_loop = wx.GUIEventLoop.GetActive()
        event_loop = wx.GUIEventLoop()
        wx.EventLoop.SetActive(event_loop)
        while event_loop.Pending():
            event_loop.Dispatch()
        wx.EventLoop.SetActive(old_loop)


loop = WxLoop()


class WxCanvasGroup(BaseCanvasGroup):
    pass


class WxRenderWidget(BaseRenderCanvas, wx.Window):
    """A wx Window representing a render canvas that can be embedded in a wx application."""

    _rc_canvas_group = WxCanvasGroup(loop)

    def __init__(self, *args, present_method=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Determine present method
        self._surface_ids = None
        if not present_method:
            self._present_to_screen = True
            if SYSTEM_IS_WAYLAND:
                # See comments in same place in qt.py
                self._present_to_screen = False
        elif present_method == "screen":
            self._present_to_screen = True
        elif present_method == "bitmap":
            global _show_image_method_warning

            _show_image_method_warning = None
            self._present_to_screen = False
        else:
            raise ValueError(f"Invalid present_method {present_method}")

        self._is_closed = False
        self._pointer_inside = None
        self._is_pointer_inside_according_to_wx = False

        # We keep a timer to prevent draws during a resize. This prevents
        # issues with mismatching present sizes during resizing (on Linux).
        self._resize_timer = TimerWithCallback(self._on_resize_done)
        self._draw_lock = False

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda x: None)
        self.Bind(wx.EVT_SIZE, self._on_resize)

        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_KEY_UP, self._on_key_up)

        self.Bind(wx.EVT_MOUSE_EVENTS, self._on_mouse_events)
        self.Bind(wx.EVT_MOTION, self._on_mouse_move)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_window_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_window_enter)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus)

        self.Show()
        self._final_canvas_init()

    def _on_resize_done(self, *args):
        self._draw_lock = False
        self.Refresh()

    def on_paint(self, event):
        dc = wx.PaintDC(self)  # needed for wx
        if not self._draw_lock:
            self._draw_frame_and_present()
        del dc
        event.Skip()

    def _get_surface_ids(self):
        if sys.platform.startswith("win") or sys.platform.startswith("darwin"):
            return {
                "window": int(self.GetHandle()),
            }
        elif sys.platform.startswith("linux"):
            if False:
                # We fall back to XWayland, see _coreutils.py
                return {
                    "platform": "wayland",
                    "window": int(self.GetHandle()),
                    "display": int(get_alt_wayland_display()),
                }
            else:
                return {
                    "platform": "x11",
                    "window": int(self.GetHandle()),
                    "display": int(get_alt_x11_display()),
                }
        else:
            logger.warning(f"Cannot get wx surface info on {sys.platform}.")
            return None

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        if isinstance(self._rc_canvas_group.get_loop(), WxLoop):
            pass  # all is well
        else:
            loop.process_wx_events()

    def _rc_get_present_methods(self):
        global _show_image_method_warning

        if self._present_to_screen and self._surface_ids is None:
            # On wx it can take a little while for the handle to be available,
            # causing GetHandle() to be initially 0, so getting a surface will fail.
            etime = time.perf_counter() + 1
            while self.GetHandle() == 0 and time.perf_counter() < etime:
                loop.process_wx_events()
            self._surface_ids = self._get_surface_ids()
            if self._surface_ids is None:
                self._present_to_screen = False

        methods = {}
        if self._present_to_screen:
            methods["screen"] = self._surface_ids
        else:
            if _show_image_method_warning:
                logger.warning(_show_image_method_warning)
                _show_image_method_warning = None
            methods["bitmap"] = {"formats": ["rgba-u8"]}
        return methods

    def _rc_request_draw(self):
        if self._draw_lock:
            return
        try:
            self.Refresh()
        except Exception:
            pass  # avoid errors when window no longer lives

    def _rc_force_draw(self):
        self.Refresh()
        self.Update()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # todo: we can easily support more formats here
        assert format == "rgba-u8"
        width, height = data.shape[1], data.shape[0]

        dc = wx.PaintDC(self)
        bitmap = wx.Bitmap.FromBufferRGBA(width, height, data)
        dc.DrawBitmap(bitmap, 0, 0, False)

    def _rc_set_logical_size(self, width, height):
        width, height = int(width), int(height)
        parent = self.Parent
        if isinstance(parent, WxRenderCanvas):
            parent.SetSize(width, height)
        elif parent is not None:
            self.SetSize(width, height)
        else:
            # The widget has no parent, likely because its going to inserted in a GUI later.
            # This method is likely called from _final_canvas_init and if we call self.SetSize() it will likely error/segfault.
            # See https://github.com/pygfx/rendercanvas/issues/91
            pass

    def _rc_close(self):
        self._is_closed = True
        parent = self.Parent
        if isinstance(parent, WxRenderCanvas):
            parent.Hide()
        else:
            self.Hide()

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        # Set title only on frame
        parent = self.Parent
        if isinstance(parent, WxRenderCanvas):
            parent.SetTitle(title)

    def _rc_set_cursor(self, cursor):
        cursor_flag = CURSOR_MAP.get(cursor)
        if cursor_flag is None:
            self.SetCursor(wx.NullCursor)  # System default
        else:
            cursor_object = wx.Cursor(cursor_flag)
            self.SetCursor(cursor_object)

    # %% Turn wx events into rendercanvas events

    def _on_resize(self, event: wx.SizeEvent):
        self._draw_lock = True
        self._resize_timer.Start(100, wx.TIMER_ONE_SHOT)

        lsize = float(self.Size[0]), float(self.Size[1])
        # Note: this is not hidpi-ready (at least on win10)
        # Observations:
        # * On Win10 this always returns 1 - so hidpi is effectively broken
        ratio = self.GetContentScaleFactor()
        # We use the same logic as for Qt to derive the physical size.
        psize = round(lsize[0] * ratio + 0.01), round(lsize[1] * ratio + 0.01)
        self._set_size_info(psize, ratio)

    def _on_key_down(self, event: wx.KeyEvent):
        char_str = self._get_char_from_event(event)
        self._key_event("key_down", event, char_str)

        if char_str is not None:
            self._char_input_event(char_str)

    def _on_key_up(self, event: wx.KeyEvent):
        char_str = self._get_char_from_event(event)
        self._key_event("key_up", event, char_str)

    def _key_event(self, event_type: str, event: wx.KeyEvent, char_str: Optional[str]):
        modifiers = tuple(
            MODIFIERS_MAP[mod]
            for mod in MODIFIERS_MAP.keys()
            if mod & event.GetModifiers()
        )

        ev = {
            "event_type": event_type,
            "key": KEY_MAP.get(event.GetKeyCode(), char_str),
            "modifiers": modifiers,
        }

        if not event.IsAutoRepeat():
            self.submit_event(ev)

    def _char_input_event(self, char_str: Optional[str]):
        if char_str is None:
            return

        ev = {
            "event_type": "char",
            "char_str": char_str,
            "modifiers": None,
        }
        self.submit_event(ev)

    @staticmethod
    def _get_char_from_event(event: wx.KeyEvent) -> Optional[str]:
        keycode = event.GetKeyCode()
        modifiers = event.GetModifiers()

        # Check if keycode corresponds to a printable ASCII character
        if 32 <= keycode <= 126:
            char = chr(keycode)
            if not modifiers & wx.MOD_SHIFT:
                char = char.lower()
            return char

        # Check for special keys (e.g., Enter, Tab)
        if keycode == wx.WXK_RETURN:
            return "\n"
        if keycode == wx.WXK_TAB:
            return "\t"

        # Handle non-ASCII characters and others
        uni_char = event.GetUnicodeKey()
        if uni_char != wx.WXK_NONE:
            return chr(uni_char)

        return None

    def _mouse_event(self, event_type: str, event: wx.MouseEvent, touches: bool = True):
        button = BUTTON_MAP.get(event.GetButton(), 0)
        buttons = (button,)  # in wx only one button is pressed per event

        modifiers = tuple(
            MODIFIERS_MAP[mod]
            for mod in MODIFIERS_MAP.keys()
            if mod & event.GetModifiers()
        )

        ev = {
            "event_type": event_type,
            "x": event.GetX(),
            "y": event.GetY(),
            "button": button,
            "buttons": buttons,
            "modifiers": modifiers,
        }

        if touches:
            ev.update(
                {
                    "ntouches": 0,
                    "touches": {},  # TODO: Wx touch events
                }
            )

        if event_type == "wheel":
            delta = event.GetWheelDelta()
            axis = event.GetWheelAxis()
            rotation = event.GetWheelRotation()

            dx = 0
            dy = 0

            if axis == wx.MOUSE_WHEEL_HORIZONTAL:
                dx = delta * rotation
            elif axis == wx.MOUSE_WHEEL_VERTICAL:
                dy = delta * rotation

            ev.update({"dx": -dx, "dy": -dy})

        self.submit_event(ev)

    def _on_mouse_events(self, event: wx.MouseEvent):
        event_type = event.GetEventType()

        event_type_name = MOUSE_EVENT_MAP_REVERSED.get(event_type, None)
        if event_type_name is None:
            return

        self._mouse_event(event_type_name, event)

    def _on_mouse_move(self, event: wx.MouseEvent):
        # On MacOS this event does not happen unless a button is pressed (i.e. dragging)
        self._mouse_event("pointer_move", event)

    def _on_window_enter(self, event: wx.MouseEvent):
        if event.GetEventType() == wx.wxEVT_ENTER_WINDOW:
            pointer_inside = True
            ev = {"event_type": "pointer_enter"}
        else:  # event.GetEventType() == wx.wxEVT_LEAVE_WINDOW
            pointer_inside = False
            ev = {"event_type": "pointer_leave"}

        # Track the state of wx
        self._is_pointer_inside_according_to_wx = pointer_inside

        # Update our state only if we have focus
        if self.HasFocus() and pointer_inside != self._pointer_inside:
            self._pointer_inside = pointer_inside
            self.submit_event(ev)

    def _on_focus(self, event: wx.FocusEvent):
        if event.GetEventType() == wx.wxEVT_SET_FOCUS:
            if self._is_pointer_inside_according_to_wx:
                if not self._pointer_inside:
                    ev = {"event_type": "pointer_enter"}
                    self._pointer_inside = True
                    self.submit_event(ev)
        else:  # event.GetEventType() == wx.wxEVT_KILL_FOCUS
            if self._pointer_inside:
                ev = {"event_type": "pointer_leave"}
                self._pointer_inside = False
                self.submit_event(ev)


class WxRenderCanvas(WrapperRenderCanvas, wx.Frame):
    """A toplevel wx Frame providing a render canvas."""

    # Most of this is proxying stuff to the inner widget.

    def __init__(self, parent=None, **kwargs):
        # There needs to be an application before any widget is created.
        loop._rc_init()
        # Any kwargs that we want to pass to *this* class, must be explicitly
        # specified in the signature. The rest goes to the subwidget.
        super().__init__(parent)

        self._subwidget = WxRenderWidget(parent=self, **kwargs)

        self.Bind(wx.EVT_CLOSE, lambda e: self.Destroy())

        self.Show()
        self._final_canvas_init()

    # wx methods

    def Destroy(self):  # noqa: N802 - this is a wx method
        self._subwidget._is_closed = True
        super().Destroy()

        # wx stops running its loop as soon as the last canvas closes.
        # So when that happens, we manually run the loop for a short while
        # so that we can clean up properly
        if not self._subwidget._rc_canvas_group.get_canvases():
            etime = time.perf_counter() + 0.15
            while time.perf_counter() < etime:
                time.sleep(0.01)
                loop.process_wx_events()


# Make available under a name that is the same for all gui backends
RenderWidget = WxRenderWidget
RenderCanvas = WxRenderCanvas
