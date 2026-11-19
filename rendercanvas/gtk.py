"""
Support for rendering in a Qt widget. Provides a widget subclass that
can be used as a standalone window or in a larger GUI.
"""

__all__ = ["GtkRenderCanvas", "GtkRenderWidget", "GtkLoop", "RenderCanvas", "loop"]

import sys
import ctypes
import weakref
import importlib
import time

from .base import WrapperRenderCanvas, BaseCanvasGroup, BaseRenderCanvas, BaseLoop
from ._coreutils import (
    logger,
    SYSTEM_IS_WAYLAND,
    get_alt_x11_display,
    get_alt_wayland_display,
)


import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject
import cairo
import numpy as np

class CallerHelper(GObject.Object):
    __gsignals__ = {
        "call": (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self):
        super().__init__()
        self.connect("call", lambda _self, func: func())


class GtkLoop(BaseLoop):
    _app: Gtk.Application | None = None
    _we_run_the_loop: bool = False
    _caller: CallerHelper

    def _rc_init(self):
        self._app = Gtk.Application.get_default()
        if self._app is None:
            self._app = Gtk.Application.new("org.rendercanvas.gtk", 0)

        loop_ref = weakref.ref(self)
        self._app.connect(
            "shutdown",
            lambda *_args: (loop := loop_ref()) and loop.stop(force=True)
        )

        if self._app.get_is_remote():
            self._mark_as_interactive()

        self._caller = CallerHelper()

    def _rc_run(self):  
        if self._app.get_is_remote():
            return

        self._we_run_the_loop = True
        try:
            self._app.run(None)
        finally:
            self._we_run_the_loop = False

    def _rc_stop(self):
        if self._we_run_the_loop and self._app is not None:
            self._app.quit()

    def _rc_add_task(self, async_func, name):
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay: float, callback):
        ms = int(max(delay * 1000, 1))
        def one_shot():
            callback()
            return False
        GLib.timeout_add(ms, one_shot)

    def _rc_call_soon_threadsafe(self, callback):
        self._caller.emit("call", callback)
        
loop = GtkLoop()

class GtkCanvasGroup(BaseCanvasGroup):
    pass

from .gtk import loop  # global GtkLoop singleton

class GtkRenderCanvas(BaseRenderCanvas, Gtk.DrawingArea):
    _rc_canvas_group = GtkCanvasGroup(loop)

    def __init__(self, *args, present_method='bitmap', **kwargs):
        super().__init__(*args, **kwargs)

        self._surface_ids = None
        self._last_native_handle = None
        self._closed = False
        self._present_to_screen = False
        self.last_image = None
        self.set_draw_func(self.draw)

        self._final_canvas_init()
        self.install_controller()
    
    def _get_surface_ids(self):
        return None

    def draw(self,da: Gtk.DrawingArea, cr: cairo.Context, area_w, area_h):
        logical_width, logical_height = self.get_logical_size()
        
        if logical_width + logical_height != area_w + area_h:
            self.set_logical_size(area_w, area_h)

        self._draw_frame_and_present()
        
        if self.last_image is None: return
        h, w = self.last_image.shape[:2]
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, w)
        image_surface = cairo.ImageSurface.create_for_data(self.last_image, cairo.FORMAT_ARGB32, w, h, stride)
        cr.set_source_surface(image_surface)
        cr.paint()

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_methods(self):
        return { "bitmap": { "formats": ['bgra-u8'], } }

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        self.last_image = data

    def _rc_set_logical_size(self, width, height):
        logical_size = float(width), float(height)
        pixel_ratio = 1.0
        pwidth = max(1, round(logical_size[0] * pixel_ratio + 0.01))
        pheight = max(1, round(logical_size[1] * pixel_ratio + 0.01))
        self._size_info.set_physical_size(pwidth, pheight, pixel_ratio)

    def _rc_request_draw(self):
        self.queue_draw()

    def _rc_force_draw(self):
        self.queue_draw()

    def _rc_close(self):
        self._closed = True

    def _rc_get_closed(self) -> bool:
        return self._closed

    def _rc_set_title(self, title: str):
        pass

    def _rc_set_cursor(self, cursor_name: str):
        pass

    def install_controller(self):
        zoom_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags(Gtk.EventControllerScrollFlags.VERTICAL))
        zoom_controller.connect("scroll", lambda sender,dx,dy: self.submit_event(dict(event_type='wheel',dx=0.0,dy=dy*100,x=0,y=0)))
        self.add_controller(zoom_controller)

        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", lambda sender,x,y: self.submit_event(dict(event_type='pointer_move',x=x ,y=y)))
        self.add_controller(motion_controller)

        click_controller = Gtk.GestureClick.new()
        click_controller.set_button(1)
        click_controller.connect("pressed", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_down',x=x ,y=y,button=3,buttons=(3,))))
        click_controller.connect("released", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_up',x=x ,y=y,button=3,buttons=(3,))))
        self.add_controller(click_controller)

        rotation_controller = Gtk.GestureClick.new()
        rotation_controller.set_button(2)
        rotation_controller.connect("pressed", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_down',x=x ,y=y,button=1,buttons=(1,))))
        rotation_controller.connect("released", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_up',x=x ,y=y,button=1,buttons=(1,))))
        self.add_controller(rotation_controller)

        pan_controller = Gtk.GestureClick.new()
        pan_controller.set_button(3)
        pan_controller.connect("pressed", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_down',x=x,y=y,button=2,buttons=(2,))))
        pan_controller.connect("released", lambda sender,n_press,x,y: self.submit_event(dict(event_type='pointer_up',x=x,y=y,button=2,buttons=(2,))))
        self.add_controller(pan_controller)     
RenderCanvas = GtkRenderCanvas