"""Tkinter backend for rendercanvas.

Direct GPU presentation is supported on Windows and should be with X11/XWayland.
Other platforms fall back to bitmap presentation.
Async integration is limited.

Tkinter does not support gamepads, touch, stylus pressure, gestures, raw mouse input, or pointer lock,
but you could use glfw and update state directly as a workaround.

"""

__all__ = [
    "RenderCanvas",
    "RenderWidget",
    "TkLoop",
    "TkRenderCanvas",
    "TkRenderWidget",
    "loop",
]

import queue
import sys
import tkinter as tk
import weakref

from .base import BaseCanvasGroup, BaseLoop, BaseRenderCanvas, WrapperRenderCanvas
from .core.coreutils import get_alt_x11_display, weakbind


# mouse buttons
# 1 = left   for Tk & rendercanvas  
# 2 = middle for Tk, right  for rendercanvas
# 3 = right  for Tk, middle for rendercanvas
_MOUSE_BUTTON_MAP = {1: 1, 2: 3, 3: 2}

_KEY_MAP = {
    "Down": "ArrowDown",
    "Up": "ArrowUp",
    "Left": "ArrowLeft",
    "Right": "ArrowRight",
    "BackSpace": "Backspace",
    "Caps_Lock": "CapsLock",
    "Delete": "Delete",
    "End": "End",
    "Return": "Enter",
    "Escape": "Escape",
    "Home": "Home",
    "Insert": "Insert",
    "Num_Lock": "NumLock",
    "Prior": "PageUp",
    "Next": "PageDown",
    "Pause": "Pause",
    "Scroll_Lock": "ScrollLock",
    "Tab": "Tab",
    "Shift_L": "Shift",
    "Shift_R": "Shift",
    "Control_L": "Control",
    "Control_R": "Control",
    "Alt_L": "Alt",
    "Alt_R": "Alt",
    "Meta_L": "Meta",
    "Meta_R": "Meta",
    "Super_L": "Meta",
    "Super_R": "Meta",
    # F1, F2, etc.. correspond 1 to 1
}

_CURSOR_MAP = {
    "default": "",
    "text": "xterm",
    "crosshair": "crosshair",
    "pointer": "hand2",
    "ew-resize": "sb_h_double_arrow",
    "ns-resize": "sb_v_double_arrow",
    "nesw-resize": "size_ne_sw",
    "nwse-resize": "size_nw_se",
    "not-allowed": "X_cursor",
    "none": "none",
}


def _modifiers(state: int) -> tuple[str, ...]:
    modifiers = []
    if state & 0x0001:
        modifiers.append("Shift")
    if state & 0x0004:
        modifiers.append("Control")
    if state & (0x0008 | 0x20000):
        modifiers.append("Alt")
    if state & (0x0040 | 0x200000):
        modifiers.append("Meta")
    return tuple(modifiers)


def _char_from_event(event) -> str | None:
    if event.keysym == "Return":
        return "\n"
    if event.keysym == "Tab":
        return "\t"
    if event.char and event.char.isprintable():
        return event.char
    return None


class TkLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._root = None

    def _rc_init(self):
        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()
        self._root = root

    def _rc_run(self):
        self._rc_init()

        if self._root is None: return
        
        # BaseLoop expects one iteration even without canvases, so pending
        # tasks can run before the loop transitions back to "off".
        if not self.get_canvases():
            self._root.update()
            self.stop()
            self._root = None
            return
        
        self._root.mainloop()
        self._root = None

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        if self._root is not None:
            #try:
            self._root.quit()
            #self.root = None
	        #except tk.TclError:
	        #    pass

    def _rc_add_task(self, async_func, name):
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        self._root.after(int(max(delay * 1000, 0)), callback)

    def _rc_call_soon_threadsafe(self, callback):
        if self._root is None: return
        self._root.after(0, callback)


loop = TkLoop()


class TkCanvasGroup(BaseCanvasGroup):
    pass


class TkRenderWidget(BaseRenderCanvas, tk.Canvas):
    """A render canvas that can be embedded in a Tkinter application."""

    _rc_canvas_group = TkCanvasGroup(loop)

    def __init__(self, master=None, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("takefocus", True)
        super().__init__(master, **kwargs)

        self._paint_pending = False
        self._buttons = set()
        self._pointer_pos = (0, 0)
        self._photo = None
        self._image_item = None

        self.bind("<Configure>", self._on_resize)
        self.bind("<Map>", lambda event: self._set_visible(True))
        self.bind("<Unmap>", lambda event: self._set_visible(False))
        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Enter>", lambda event: self.submit_event({"event_type": "pointer_enter"}))
        self.bind("<Leave>", lambda event: self.submit_event({"event_type": "pointer_leave"}))
        self.bind("<Motion>", self._on_pointer_move)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_wheel)
        self.bind("<Button-5>", self._on_wheel)
        self.bind("<KeyPress>", self._on_key_down)
        self.bind("<KeyRelease>", self._on_key_up)
        self.bind("<FocusOut>", self._on_focus_out)

        for button in _MOUSE_BUTTON_MAP:
            self.bind(f"<ButtonPress-{button}>", self._on_pointer_down)
            self.bind(f"<ButtonRelease-{button}>", self._on_pointer_up)
            self.bind(f"<Double-Button-{button}>", self._on_double_click)

        self._final_canvas_init()

    def _rc_gui_poll(self):
        try:
            self.update_idletasks()
            if not isinstance(self._rc_canvas_group.get_loop(), TkLoop):
                self.update()
        except tk.TclError:
            pass

    def _rc_get_present_info(self, present_methods):
        for method in present_methods:
            if method == "screen":
                surface_ids = self._get_surface_ids()
                if surface_ids is not None:
                    return {"method": "screen", **surface_ids}
            elif method == "bitmap":
                return {"method": "bitmap", "formats": ["rgba-u8"]}
        return None

    def _get_surface_ids(self):
        try:
            self.update_idletasks()
            window = int(self.winfo_id())
        except tk.TclError:
            return None

        if sys.platform == "win32":
            return {"window": window}

        if sys.platform.startswith("linux"):
            if self.tk.call("tk", "windowingsystem") == "x11":
                display = get_alt_x11_display()
                if display:
                    return {
                        "platform": "x11",
                        "window": window,
                        "display": int(display),
                    }

        return None

    def _rc_request_draw(self):
        self._time_to_draw()

    def _rc_request_paint(self):
        if self._paint_pending:
            return
        self._paint_pending = True
        try:
            self.after_idle(self._paint)
        except tk.TclError:
            self._paint_pending = False

    def _paint(self):
        self._paint_pending = False
        self._time_to_paint()

    def _rc_force_paint(self):
        self._time_to_paint()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        if format != "rgba-u8":
            raise ValueError(f"Unsupported bitmap format {format!r}")

        try:
            rgba = memoryview(data)
        except TypeError as err:
            raise ValueError("Expected an HxWx4 uint8 bitmap") from err

        if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.itemsize != 1:
            raise ValueError("Expected an HxWx4 uint8 bitmap")

        height, width = rgba.shape[:2]
        flat = rgba.cast("B") if rgba.c_contiguous else memoryview(rgba.tobytes())

        rgb = bytearray(width * height * 3)
        rgb[0::3] = flat[0::4]
        rgb[1::3] = flat[1::4]
        rgb[2::3] = flat[2::4]

        ppm = f"P6\n{width} {height}\n255\n".encode() + rgb
        photo = tk.PhotoImage(master=self, data=ppm, format="PPM")

        self._photo = photo

        if self._image_item is None:
            self._image_item = self.create_image( 0, 0, anchor="nw", image=photo )
        else:
            self.itemconfigure(self._image_item, image=photo)

    def _rc_set_logical_size(self, width, height):
        width, height = max(1, round(width)), max(1, round(height))
        if getattr(self.master, "_is_tk_rendercanvas", False):
            self.master.geometry(f"{width}x{height}")
        else:
            self.configure(width=width, height=height)
        self._size_info.set_physical_size(width, height, 1.0)

    def _rc_close(self):
        widget = self.master if getattr(self.master, "_is_tk_rendercanvas", False) else self
        try:
            widget.destroy()
        except tk.TclError:
            pass

    def _rc_set_title(self, title):
        if getattr(self.master, "_is_tk_rendercanvas", False):
            self.master.title(title)

    def _rc_set_cursor(self, cursor):
        try:
            self.configure(cursor=_CURSOR_MAP[cursor])
        except tk.TclError:
            self.configure(cursor="")

    def _on_resize(self, event):
        self._size_info.set_physical_size(max(0, event.width), max(0, event.height), 1.0)
        self.request_draw()

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._photo = None
        self.submit_event({"event_type": "close"})
        current_loop = self._rc_canvas_group.get_loop()
        if current_loop is not None and not current_loop.get_canvases():
            current_loop.stop(force=True)

    def _pointer_event(self, event_type, event, *, touches=True):
        self._pointer_pos = event.x, event.y
        button = _MOUSE_BUTTON_MAP.get(event.num, 0)
        result = {
            "event_type": event_type,
            "x": event.x,
            "y": event.y,
            "button": button,
            "buttons": tuple(sorted(self._buttons)),
            "modifiers": _modifiers(event.state),
        }
        if touches:
            result.update(ntouches=0, touches={})
        self.submit_event(result)

    def _on_pointer_down(self, event):
        self.focus_set()
        self._buttons.add(_MOUSE_BUTTON_MAP[event.num])
        self._pointer_event("pointer_down", event)

    def _on_pointer_up(self, event):
        self._buttons.discard(_MOUSE_BUTTON_MAP[event.num])
        self._pointer_event("pointer_up", event)

    def _on_pointer_move(self, event):
        self._pointer_event("pointer_move", event)

    def _on_double_click(self, event):
        self._buttons.add(_MOUSE_BUTTON_MAP[event.num])
        self._pointer_event("double_click", event, touches=False)

    def _on_focus_out(self, event):
        while self._buttons:
            button = self._buttons.pop()
            self.submit_event(
                {
                    "event_type": "pointer_up",
                    "x": self._pointer_pos[0],
                    "y": self._pointer_pos[1],
                    "button": button,
                    "buttons": tuple(sorted(self._buttons)),
                    "modifiers": (),
                    "ntouches": 0,
                    "touches": {},
                }
            )

    def _on_wheel(self, event):
        self._pointer_pos = event.x, event.y

        """
        On Windows, <MouseWheel> provides event.delta, usually in multiples of 120.
        On macOS, event.delta is typically already expressed in smaller scroll units.
        On Linux/X11, ordinary wheel movement often arrives as mouse buttons:
        Button 4 = scroll up, Button 5 = scroll down
        The sign is reversed because Tk and rendercanvas use opposite conventions.
        """
        if event.num in (4, 5):
            delta = -100 if event.num == 4 else 100
        else:
            unit = 120 if sys.platform == "win32" else 1
            delta = -100 * event.delta / unit

        # horizontal scroll if shift modifier is pressed
        horizontal = bool(event.state & 0x0001)
        self.submit_event(
            {
                "event_type": "wheel",
                "dx": delta if horizontal else 0,
                "dy": 0 if horizontal else delta,
                "x": event.x,
                "y": event.y,
                "modifiers": _modifiers(event.state),
            }
        )

    def _key_event(self, event_type, event):
        key = _KEY_MAP.get(event.keysym, event.char or event.keysym)
        print(key)
        self.submit_event(
            {
                "event_type": event_type,
                "key": key,
                "modifiers": _modifiers(event.state),
            }
        )

    def _on_key_down(self, event):
        self._key_event("key_down", event)
        char = _char_from_event(event)
        if char is not None:
            self.submit_event(
                {
                    "event_type": "char",
                    "data": char,
                    "char_str": char,
                    "modifiers": None,
                }
            )

    def _on_key_up(self, event):
        self._key_event("key_up", event)

class TkRenderCanvas(WrapperRenderCanvas):
    """A standalone Tkinter window containing a TkRenderWidget."""

    def __init__(self, master=None, **kwargs):

        self._window = tk.Toplevel(master or loop._root)
        self._window._is_tk_rendercanvas = True

        self._subwidget = TkRenderWidget(self._window, **kwargs)
        self._subwidget.pack(fill="both", expand=True)

        window_ref = weakref.ref(self._window)

        def close():
            if window_ref := widget_ref():
                window_ref.close()

        self._window.protocol("WM_DELETE_WINDOW", close)


# Make available under a name that is the same for all gui backends
RenderWidget = TkRenderWidget
RenderCanvas = TkRenderCanvas
