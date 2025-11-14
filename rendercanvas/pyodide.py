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
)

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
        self._js_array = Uint8ClampedArray.new(0)

        # We use an offscreen canvas when the bitmap texture does not match the physical pixels. You should see it as a GPU texture.
        self._offscreen_canvas = None

        # If size or title are not given, set them to None, so they are left as-is. This is usually preferred in html docs.
        kwargs["size"] = kwargs.get("size", None)
        kwargs["title"] = kwargs.get("title", None)

        # Finalize init
        super().__init__(*args, **kwargs)
        self._setup_events()
        self._final_canvas_init()

    def _setup_events(self):
        # Idea: Implement this event logic in JavaScript, so we can re-use it across all backends that render in the browser.

        el = self._canvas_element
        el.tabIndex = -1

        # Obtain container to put our hidden focus element.
        # Putting the focus_element as a child of the canvas prevents chrome from emitting input events.
        focus_element_container_id = "rendercanvas-focus-element-container"
        focus_element_container = document.getElementById(focus_element_container_id)
        if not focus_element_container:
            focus_element_container = document.createElement("div")
            focus_element_container.setAttribute("id", focus_element_container_id)
            focus_element_container.style.position = "absolute"
            focus_element_container.style.top = "0"
            focus_element_container.style.left = "-9999px"
            document.body.appendChild(focus_element_container)

        # Create an element to which we transfer focus, so we can capture key events and prevent global shortcuts
        self._focus_element = focus_element = document.createElement("input")
        focus_element.type = "text"
        focus_element.tabIndex = -1
        focus_element.autocomplete = "off"
        focus_element.autocorrect = "off"
        focus_element.autocapitalize = "off"
        focus_element.spellcheck = False
        focus_element.style.width = "1px"
        focus_element.style.height = "1px"
        focus_element.style.padding = "0"
        focus_element.style.opacity = 0
        focus_element.style.pointerEvents = "none"
        focus_element_container.appendChild(focus_element)

        pointers = {}
        last_buttons = ()

        # Prevent context menu
        def _on_context_menu(ev):
            if not ev.shiftKey:
                ev.preventDefault()
                ev.stopPropagation()
                return False

        el.oncontextmenu = create_proxy(_on_context_menu)

        def _resize_callback(entries, _=None):
            # The physical size is easy. The logical size can be much more tricky
            # to obtain due to all the CSS stuff. But the base class will just calculate that
            # from the physical size and the pixel ratio.

            # Select entry
            our_entries = [entry for entry in entries if entry.target.js_id == el.js_id]
            if not our_entries:
                return
            entry = entries[0]

            ratio = window.devicePixelRatio

            if entry.devicePixelContentBoxSize:
                psize = (
                    entry.devicePixelContentBoxSize[0].inlineSize,
                    entry.devicePixelContentBoxSize[0].blockSize,
                )
            else:  # some browsers don't support the above
                if entry.contentBoxSize:
                    lsize = (
                        entry.contentBoxSize[0].inlineSize,
                        entry.contentBoxSize[0].blockSize,
                    )
                else:
                    lsize = (entry.contentRect.width, entry.contentRect.height)
                psize = (int(lsize[0] * ratio), int(lsize[1] * ratio))

            # If the element does not set the size with its style, the canvas' width and height are used.
            # On hidpi screens this'd cause the canvas size to quickly increase with factors of 2 :)
            # Therefore we want to make sure that the style.width and style.height are set.
            lsize = psize[0] / ratio, psize[1] / ratio
            if not el.style.width:
                el.style.width = f"{lsize[0]}px"
            if not el.style.height:
                el.style.height = f"{lsize[1]}px"

            # Set the canvas to the match its physical size on screen
            el.width = psize[0]
            el.height = psize[1]

            # Notify the base class, so it knows our new size
            pwidth, pheight = psize
            self._size_info.set_physical_size(pwidth, pheight, window.devicePixelRatio)

        self._resize_callback_proxy = create_proxy(_resize_callback)
        self._resize_observer = ResizeObserver.new(self._resize_callback_proxy)
        self._resize_observer.observe(el)

        # Note: there is no concept of an element being 'closed' in the DOM.

        def _js_pointer_down(ev):
            # When points is down, set focus to the focus-element, and capture the pointing device.
            # Because we capture the event, there will be no other events when buttons are pressed down,
            # although they will end up in the 'buttons'. The lost/release will only get fired when all buttons
            # are released/lost. Which is why we look up the original button in our `pointers` list.
            nonlocal last_buttons
            if not looks_like_mobile:
                focus_element.focus({"preventScroll": True, "focusVisible": False})
            el.setPointerCapture(ev.pointerId)
            button = MOUSE_BUTTON_MAP.get(ev.button, ev.button)
            pointers[ev.pointerId] = (button,)
            last_buttons = buttons = tuple(pointer[0] for pointer in pointers.values())
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            event = {
                "event_type": "pointer_down",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,  # TODO later: maybe via https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent
                "touches": {},
                "time_stamp": time.time(),
            }
            if not ev.altKey:
                ev.preventDefault()
            self.submit_event(event)

        def _js_pointer_lost(ev):
            # This happens on pointer-up or pointer-cancel. We treat them the same.
            # According to the spec, the .button is -1, so we retrieve the button from the stored pointer.
            nonlocal last_buttons
            last_buttons = ()
            down_tuple = pointers.pop(ev.pointerId, None)
            button = MOUSE_BUTTON_MAP.get(ev.button, ev.button)
            if down_tuple is not None:
                button = down_tuple[0]
            buttons = buttons_mask_to_tuple(ev.buttons)
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            event = {
                "event_type": "pointer_up",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": button,
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": time.time(),
            }
            self.submit_event(event)

        def _js_pointer_move(ev):
            # If this pointer is not down, but other pointers are, don't emit an event.
            nonlocal last_buttons
            if pointers and ev.pointerId not in pointers:
                return
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            last_buttons = buttons = buttons_mask_to_tuple(ev.buttons)
            event = {
                "event_type": "pointer_move",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": MOUSE_BUTTON_MAP.get(ev.button, ev.button),
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": time.time(),
            }
            self.submit_event(event)

        def _js_pointer_enter(ev):
            # If this pointer is not down, but other pointers are, don't emit an event.
            if pointers and ev.pointerId not in pointers:
                return
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            buttons = buttons_mask_to_tuple(ev.buttons)
            event = {
                "event_type": "pointer_enter",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": MOUSE_BUTTON_MAP.get(ev.button, ev.button),
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": time.time(),
            }
            self.submit_event(event)

        def _js_pointer_leave(ev):
            # If this pointer is not down, but other pointers are, don't emit an event.
            if pointers and ev.pointerId not in pointers:
                return
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            buttons = buttons_mask_to_tuple(ev.buttons)
            event = {
                "event_type": "pointer_leave",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": MOUSE_BUTTON_MAP.get(ev.button, ev.button),
                "buttons": buttons,
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": time.time(),
            }
            self.submit_event(event)

        def _js_double_click(ev):
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            buttons = buttons_mask_to_tuple(ev.buttons)
            event = {
                "event_type": "double_click",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "button": MOUSE_BUTTON_MAP.get(ev.button, ev.button),
                "buttons": buttons,
                "modifiers": modifiers,
                # no touches here
                "time_stamp": time.time(),
            }
            if not ev.altKey:
                ev.preventDefault()
            self.submit_event(event)

        def _js_wheel(ev):
            if window.document.activeElement.js_id != focus_element.js_id:
                return
            scales = [1 / window.devicePixelRatio, 16, 600]  # pixel, line, page
            scale = scales[ev.deltaMode]
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            event = {
                "event_type": "wheel",
                "x": ev.offsetX,
                "y": ev.offsetY,
                "dx": ev.deltaX * scale,
                "dy": ev.deltaY * scale,
                "buttons": last_buttons,
                "modifiers": modifiers,
                "time_stamp": time.time(),
            }
            if not ev.altKey:
                ev.preventDefault()
            self.submit_event(event)

        def _js_key_down(ev):
            if ev.repeat:
                return  # don't repeat keys
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            event = {
                "event_type": "key_down",
                "modifiers": modifiers,
                "key": KEYMAP.get(ev.key, ev.key),
                "time_stamp": time.time(),
            }
            # No need for stopPropagation or preventDefault because we are in a text-input.
            self.submit_event(event)

            # NOTE: to allow text-editing functionality *inside* a framebuffer, e.g. via imgui or something similar,
            # we need events like arrow keys, backspace, and delete, with modifiers, and with repeat.
            # Also see comment in jupyter_rfb

        def _js_key_up(ev):
            modifiers = tuple([v for k, v in KEY_MOD_MAP.items() if getattr(ev, k)])
            event = {
                "event_type": "key_up",
                "modifiers": modifiers,
                "key": KEYMAP.get(ev.key, ev.key),
                "time_stamp": time.time(),
            }
            self.submit_event(event)

        def _js_char(ev):
            event = {
                "event_type": "char",
                "data": ev.data,
                "is_composing": ev.isComposing,
                "input_type": ev.inputType,
                # "repeat": getattr(ev, "repeat", False),  # n.a.
                "time_stamp": time.time(),
            }
            self.submit_event(event)
            if not ev.isComposing:
                focus_element.value = ""  # Prevent the text box from growing

        add_event_listener(el, "pointerdown", _js_pointer_down)
        add_event_listener(el, "lostpointercapture", _js_pointer_lost)
        add_event_listener(el, "pointermove", _js_pointer_move)
        add_event_listener(el, "pointerenter", _js_pointer_enter)
        add_event_listener(el, "pointerleave", _js_pointer_leave)
        add_event_listener(el, "dblclick", _js_double_click)
        add_event_listener(el, "wheel", _js_wheel)
        add_event_listener(focus_element, "keydown", _js_key_down)  # or document?
        add_event_listener(focus_element, "keyup", _js_key_up)
        add_event_listener(focus_element, "input", _js_char)

        def unregister_events():
            self._resize_observer.disconnect()
            remove_event_listener(el, "pointerdown", _js_pointer_down)
            remove_event_listener(el, "lostpointercapture", _js_pointer_lost)
            remove_event_listener(el, "pointermove", _js_pointer_move)
            remove_event_listener(el, "pointerenter", _js_pointer_enter)
            remove_event_listener(el, "pointerleave", _js_pointer_leave)
            remove_event_listener(el, "dblclick", _js_double_click)
            remove_event_listener(el, "wheel", _js_wheel)
            remove_event_listener(focus_element, "keydown", _js_key_down)
            remove_event_listener(focus_element, "keyup", _js_key_up)
            remove_event_listener(focus_element, "input", _js_char)

        self._unregister_events = unregister_events

    def _rc_gui_poll(self):
        pass  # Nothing to be done; the JS loop is always running (and Pyodide wraps that in a global asyncio loop)

    def _rc_get_present_methods(self):
        return {
            # Generic presentation
            "bitmap": {
                "formats": ["rgba-u8"],
            },
            # wgpu-specific presentation. The wgpu.backends.pyodide.GPUCanvasContext must be able to consume this.
            "screen": {
                "platform": "browser",
                "window": self._canvas_element,  # Just provide the canvas object
            },
        }

    def _rc_request_draw(self):
        window.requestAnimationFrame(
            create_proxy(lambda _: self._draw_frame_and_present())
        )

    def _rc_force_draw(self):
        # Not very clean to do this, and not sure if it works in a browser;
        # you can draw all you want, but the browser compositer only uses the last frame, I expect.
        # But that's ok, since force-drawing is not recommended in general.
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, **kwargs):
        data = kwargs.get("data")

        # Convert to memoryview. It probably already is.
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
        if self._unregister_events:
            self._unregister_events()
            self._unregister_events = None

        # Remove the focus element from the dom.
        self._focus_element.remove()

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
