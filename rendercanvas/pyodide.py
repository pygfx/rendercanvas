"""
Support to run rendercanvas in a webbrowser via Pyodide.

User code must provide a canvas that is in the dom, by passing the canvas
element or its id. By default it selects an element with id "canvas". It
is not required to set the default sdl2 canvas as the Pyodide docs describe.
"""

__all__ = ["PyodideRenderCanvas", "RenderCanvas", "loop"]

import re
import sys
import time
import ctypes
from importlib.resources import files as resource_files

from .base import BaseRenderCanvas, BaseCanvasGroup
from .asyncio import loop

if "pyodide" not in sys.modules:
    raise ImportError("This module is only for use with Pyodide in the browser.")

from pyodide.ffi import create_proxy, to_js
from pyodide.ffi.wrappers import add_event_listener, remove_event_listener
from js import (
    document,
    ImageData,
    Uint8ClampedArray,
    window,
    ResizeObserver,
    OffscreenCanvas,
    navigator,
    eval as eval_js,
)


def _load_javascript():
    for fname in ["rendercanvas_events.js"]:
        js_path = resource_files("rendercanvas.core").joinpath(fname)
        js = js_path.read_text()
        js = "(function () {\n{JS}\n})();".replace("JS", js)  # wrap in IIFE module
        script = document.createElement("script")
        script.text = js
        document.head.appendChild(script)


_load_javascript()


KEYMAP = {
    "Ctrl": "Control",
    "Del": "Delete",
    "Esc": "Escape",
}

KEY_MOD_MAP = {
    "altKey": "Alt",
    "ctrlKey": "Control",
    "metaKey": "Meta",
    "shiftKey": "Shift",
}

MOUSE_BUTTON_MAP = {
    -1: 0,  # no button
    0: 1,  # left
    1: 3,  # middle/wheel
    2: 2,  # right
    3: 4,  # backwards
    4: 5,  # forwards
}


def buttons_mask_to_tuple(mask) -> tuple[int, ...]:
    bin(mask)
    res = ()
    for i, v in enumerate(bin(mask)[:1:-1]):
        if v == "1":
            res += (MOUSE_BUTTON_MAP.get(i, i),)
    return res


looks_like_mobile = bool(
    re.search(r"mobi|android|iphone|ipad|ipod|tablet", str(navigator.userAgent).lower())
)


# The canvas group manages canvases of the type we define below. In general we don't have to implement anything here.
class PyodideCanvasGroup(BaseCanvasGroup):
    pass


class PyodideRenderCanvas(BaseRenderCanvas):
    """An HTMLCanvasElement providing a render canvas."""

    _rc_canvas_group = PyodideCanvasGroup(loop)

    def __init__(
        self,
        canvas_element: str = "canvas",
        *args,
        **kwargs,
    ):
        # Resolve and check the canvas element
        canvas_id = None
        if isinstance(canvas_element, str):
            canvas_id = canvas_element
            canvas_element = document.getElementById(canvas_id)
        if not (
            hasattr(canvas_element, "tagName") and canvas_element.tagName == "CANVAS"
        ):
            repr = f"{canvas_element!r}"
            if canvas_id:
                repr = f"{canvas_id!r} -> " + repr
            raise TypeError(
                f"Given canvas element does not look like a <canvas>: {repr}"
            )
        self._canvas_element = canvas_element

        # We need a buffer to store pixel data, until we figure out how we can map a Python memoryview to a JS ArrayBuffer without making a copy.
        # TODO: if its any easier for a numpy array, we could go that route!
        self._js_array = Uint8ClampedArray.new(0)

        # We use an offscreen canvas when the bitmap texture does not match the physical pixels. You should see it as a GPU texture.
        self._offscreen_canvas = None

        # If size or title are not given, set them to None, so they are left as-is. This is usually preferred in html docs.
        kwargs["size"] = kwargs.get("size", None)
        kwargs["title"] = kwargs.get("title", None)

        # Finalize init
        super().__init__(*args, **kwargs)

        self._event_manager = window.rendercanvas_events.RCEventManager_or_RCView.new(
            el=canvas_element,
            sizeCallback=create_proxy(self._size_info.set_physical_size),
            eventCallback=create_proxy(
                lambda js_obj: self.submit_event(js_obj.to_py())
            ),
            wheelThrottle=0,
            moveThrottle=0,
        )

        self._final_canvas_init()

    def _rc_gui_poll(self):
        pass  # Nothing to be done; the JS loop is always running (and Pyodide wraps that in a global asyncio loop)

    def _rc_get_present_info(self, present_methods):
        # Select method
        the_method = present_methods[0]

        # Apply
        if the_method == "screen":
            # wgpu-specific presentation. The wgpu.backends.pyodide.GPUCanvasContext must be able to consume this.
            return {
                "method": "screen",
                "platform": "browser",
                "window": self._canvas_element,  # Just provide the canvas object
            }
        elif the_method == "bitmap":
            # Generic presentation
            return {
                "method": "bitmap",
                "formats": ["rgba-u8"],
            }
        else:
            return None  # raises error

    def _rc_request_draw(self):
        # No need to wait
        self._time_to_draw()

    def _rc_request_paint(self):
        window.requestAnimationFrame(create_proxy(lambda _: self._time_to_paint()))

    def _rc_force_paint(self):
        # Not very clean to do this, and not sure if it works in a browser;
        # you can draw all you want, but the browser compositer only uses the last frame, I expect.
        # But that's ok, since force-drawing is not recommended in general.
        self._time_to_paint()

    def _rc_present_bitmap(self, **kwargs):
        data = kwargs.get("data")

        # Convert to memoryview (from a numpy array)
        m = memoryview(data)
        h, w = m.shape[:2]

        # Convert to a JS ImageData object
        if True:
            # Make sure that the array matches the number of pixels
            if self._js_array.length != m.nbytes:
                self._js_array = Uint8ClampedArray.new(m.nbytes)
            # Copy pixels into the array.
            self._js_array.assign(m)
            array_uint8_clamped = self._js_array
        else:
            # Convert memoryview to a JS array without making a copy. Does not work yet.
            # Pyodide does not support memoryview very well, so we convert to a ctypes array first.
            # Some options:
            # * Use pyodide.ffi.PyBuffer, but this name cannot be imported. See https://github.com/pyodide/pyodide/issues/5972
            # * Use ``ptr = ctypes.addressof(ctypes.c_char.from_buffer(buf))`` and then ``Uint8ClampedArray.new(full_wasm_buffer, ptr, nbytes)``,
            #   but for now we don't seem to be able to get access to the raw wasm data.
            # * Use to_js(). For now this makes a copy (maybe that changes someday?).
            c = (ctypes.c_uint8 * m.nbytes).from_buffer(data)  # No copy
            array_uint8 = to_js(c)  # Makes a copy, and somehow mangles the data??
            array_uint8_clamped = Uint8ClampedArray.new(array_uint8.buffer)  # no-copy
        # Create image data
        image_data = ImageData.new(array_uint8_clamped, w, h)

        # Idea: use wgpu or webgl to upload to a texture and then render that.
        # I'm pretty sure the below does essentially the same thing, but I am not sure about the amount of overhead.

        # Now present the image data.
        # For this we can blit the image into the canvas (i.e. no scaling). We can only use this is the image size matches
        # the canvas size (in physical pixels). Otherwise we have to scale the image. For that we can use an ImageBitmap and
        # draw that with CanvasRenderingContext2D.drawImage() or ImageBitmapRenderingContext.transferFromImageBitmap(),
        # but creating an ImageBitmap is async, which complicates things. So we use an offscreen canvas as an in-between step.
        cw, ch = self._canvas_element.width, self._canvas_element.height
        if w == cw and h == ch:
            # Quick blit
            self._canvas_element.getContext("2d").putImageData(image_data, 0, 0)
        else:
            # Make sure that the offscreen canvas matches the data size
            if self._offscreen_canvas is None:
                self._offscreen_canvas = OffscreenCanvas.new(w, h)
            if self._offscreen_canvas.width != w or self._offscreen_canvas.height != h:
                self._offscreen_canvas.width = w
                self._offscreen_canvas.height = h
            # Blit to the offscreen canvas.
            # This effectively uploads the image to a GPU texture (represented by the offscreen canvas).
            self._offscreen_canvas.getContext("2d").putImageData(image_data, 0, 0)
            # Then we draw the offscreen texture into the real texture, scaling is applied.
            # Do we want a smooth image or nearest-neighbour? Depends on the situation.
            # We should decide what we want backends to do, and maybe have a way for users to chose.
            ctx = self._canvas_element.getContext("2d")
            ctx.imageSmoothingEnabled = False
            ctx.drawImage(self._offscreen_canvas, 0, 0, cw, ch)

    def _rc_set_logical_size(self, width: float, height: float):
        self._canvas_element.style.width = f"{width}px"
        self._canvas_element.style.height = f"{height}px"

    def _rc_close(self):
        # Closing is a bit weird in the browser ...

        # Mark as closed
        canvas_element = self._canvas_element
        if canvas_element is None:
            return  # already closed
        self._canvas_element = None

        # Disconnect events
        if self._event_manager:
            self._event_manager.close()
            self._event_manager = None

        # Removing the element from the page. One can argue whether you want this or not.
        canvas_element.remove()

    def _rc_get_closed(self):
        return self._canvas_element is None

    def _rc_set_title(self, title: str):
        # A canvas element doesn't have a title directly.
        # We assume that when the canvas sets a title it's the only one, and we set the title of the document.
        # Maybe we want a mechanism to prevent this at some point, we'll see.
        document.title = title

    def _rc_set_cursor(self, cursor: str):
        self._canvas_element.style.cursor = cursor


# Make available under a name that is the same for all backends
loop = loop  # must set loop variable to pass meta tests
RenderCanvas = PyodideRenderCanvas
