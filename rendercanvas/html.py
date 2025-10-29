"""
Support to run rendercanvas on the webbrowser via Pyodide.

We expect to have a HTMLCanvas element with the id "canvas".
It is not required to set the default sdl2 canvas as the Pyodide docs describe.
"""

__all__ = ["HtmlRenderCanvas", "RenderCanvas", "loop"]

import sys
import ctypes

from .base import BaseRenderCanvas, BaseCanvasGroup
from .asyncio import loop

if "pyodide" not in sys.modules:
    raise ImportError("This module is only for use with Pyodide in the browser.")

from pyodide.ffi import create_proxy, to_js
from js import (
    document,
    ImageData,
    Uint8ClampedArray,
    window,
    ResizeObserver,
    OffscreenCanvas,
)


# The canvas group manages canvases of the type we define below. In general we don't have to implement anything here.
class HtmlCanvasGroup(BaseCanvasGroup):
    pass


class HtmlRenderCanvas(BaseRenderCanvas):
    """An html canvas providing a render canvas."""

    _rc_canvas_group = HtmlCanvasGroup(loop)

    def __init__(
        self,
        canvas_element: str = "rendercanvas",
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

        # More variables
        self._js_array = Uint8ClampedArray.new(0)  # buffer to store pixel data
        self._offscreen_canvas = None

        # If size or title are not given, set them to None, so they are left as-is. This is usually preferred in html docs.
        kwargs["size"] = kwargs.get("size", None)
        kwargs["title"] = kwargs.get("title", None)

        # Finalize init
        super().__init__(*args, **kwargs)
        self._setup_events()
        self._final_canvas_init()

    @property
    def html_context(self):
        # this should only be accessed canvas.get_context("ctx_type") was called.
        return self._html_context

    def _setup_events(self):
        # following list from: https://jupyter-rfb.readthedocs.io/en/stable/events.html
        # better: https://rendercanvas.readthedocs.io/stable/api.html#rendercanvas.EventType
        key_mod_map = {
            "altKey": "Alt",
            "ctrlKey": "Control",
            "metaKey": "Meta",
            "shiftKey": "Shift",
        }

        # https://jupyter-rfb.readthedocs.io/en/stable/events.html#mouse-buttons
        # https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent/button
        mouse_button_map = {
            -1: 0,  # no button
            0: 1,  # left
            1: 3,  # middle/wheel
            2: 2,  # right
            3: 4,  # backwards
            4: 5,  # forwards
        }

        # https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent/buttons
        def buttons_mask_to_tuple(mask) -> tuple[int, ...]:
            bin(mask)
            res = ()
            for i, v in enumerate(bin(mask)[:1:-1]):
                if v == "1":
                    res += (mouse_button_map.get(i, i),)
            return res

        self._pointer_inside = False  # keep track for the pointer_move event
        # resize ? maybe composition?
        # perhaps: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver

        def _resize_callback(entries, _=None):
            # The physical size is easy. The logical size can be much more tricky
            # to obtain due to all the CSS stuff. But the base class will just calcualte that
            # from the physical size and the pixel ratio.

            # Select entry
            our_entries = [
                entry
                for entry in entries
                if entry.target.js_id == self._canvas_element.js_id
            ]
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
            lsize = ratio * psize[0], ratio * psize[1]
            if not self._canvas_element.style.width:
                self._canvas_element.style.width = f"{lsize[0]}px"
            if not self._canvas_element.style.height:
                self._canvas_element.style.height = f"{lsize[1]}px"

            # Set the canvas to the match its physical size on screen
            self._canvas_element.width = psize[0]
            self._canvas_element.height = psize[1]

            # Notify the base class, so it knows our new size
            self._set_size_info(psize, window.devicePixelRatio)

        self._resize_callback_proxy = create_proxy(_resize_callback)
        self._resize_observer = ResizeObserver.new(self._resize_callback_proxy)
        self._resize_observer.observe(self._canvas_element)

        # close ? perhaps https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent

        # pointer_down
        def _html_pointer_down(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "pointer_down",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "ntouches": 0,  # TODO: maybe via https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent
                "touches": {},
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._pointer_down_proxy = create_proxy(_html_pointer_down)
        self._canvas_element.addEventListener("pointerdown", self._pointer_down_proxy)

        # pointer_up
        def _html_pointer_up(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "pointer_up",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._pointer_up_proxy = create_proxy(_html_pointer_up)
        self._canvas_element.addEventListener("pointerup", self._pointer_up_proxy)

        # pointer_move
        def _html_pointer_move(proxy_args):
            if (not self._pointer_inside) and (
                not proxy_args.buttons
            ):  # only when inside or a button is pressed
                return
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "pointer_move",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._pointer_move_proxy = create_proxy(_html_pointer_move)
        document.addEventListener("pointermove", self._pointer_move_proxy)

        # pointer_enter
        def _html_pointer_enter(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "pointer_enter",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)
            self._pointer_inside = True

        self._pointer_enter_proxy = create_proxy(_html_pointer_enter)
        self._canvas_element.addEventListener("pointerenter", self._pointer_enter_proxy)

        # pointer_leave
        def _html_pointer_leave(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "pointer_leave",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "ntouches": 0,
                "touches": {},
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)
            self._pointer_inside = False

        self._pointer_leave_proxy = create_proxy(_html_pointer_leave)
        self._canvas_element.addEventListener("pointerleave", self._pointer_leave_proxy)
        # TODO: can all the above be refactored into a function consturctor/factory?

        # double_click
        def _html_double_click(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "double_click",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": mouse_button_map.get(proxy_args.button, proxy_args.button),
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                # no touches here
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._double_click_proxy = create_proxy(_html_double_click)
        self._canvas_element.addEventListener("dblclick", self._double_click_proxy)

        # wheel
        def _html_wheel(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "wheel",
                "dx": proxy_args.deltaX,
                "dy": proxy_args.deltaY,
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "buttons": buttons_mask_to_tuple(proxy_args.buttons),
                "modifiers": modifiers,
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._wheel_proxy = create_proxy(_html_wheel)
        self._canvas_element.addEventListener("wheel", self._wheel_proxy)

        # key_down
        def _html_key_down(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "key_down",
                "modifiers": modifiers,
                "key": proxy_args.key,
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._key_down_proxy = create_proxy(_html_key_down)
        document.addEventListener(
            "keydown", self._key_down_proxy
        )  # key events happen on document scope?

        # key_up
        def _html_key_up(proxy_args):
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "key_up",
                "modifiers": modifiers,
                "key": proxy_args.key,
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._key_up_proxy = create_proxy(_html_key_up)
        document.addEventListener("keyup", self._key_up_proxy)

        # char ... it's not this
        # def _html_char(proxy_args):
        #     print(dir(proxy_args))
        #     modifiers = tuple(
        #         [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
        #     )
        #     event = {
        #         "event_type": "char",
        #         "modifiers": modifiers,
        #         "char_str": proxy_args.key,  # unsure if this works, it's experimental anyway: https://github.com/pygfx/rendercanvas/issues/28
        #         "time_stamp": proxy_args.timeStamp,
        #     }
        #     self.submit_event(event)

        # self._char_proxy = create_proxy(_html_char)
        # document.addEventListener(
        #     "input", self._char_proxy
        # )  # maybe just another keydown? (seems to include unicode chars)

        # animate event doesn't seem to be actually implemented, and it's by the loop not the gui.

    def _rc_gui_poll(self):
        pass  # Nothing to be done; the JS loop is always running (and Pyodide wraps that in a global asyncio loop)

    def _rc_get_present_methods(self):
        # TODO: provide access to wgpu context
        # TODO: that window id does not make sense
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            },
            "screen": {
                "platform": "pyodide",
                "window": self._canvas_element.js_id,  # is a number - doubt it's useful though...
            },
        }

    def _rc_request_draw(self):
        window.requestAnimationFrame(
            create_proxy(lambda _: self._draw_frame_and_present())
        )

    def _rc_force_draw(self):
        # Not very clean to do this, and not sure if it works in a browser;
        # you can draw all you want, but the browser compositer only uses the last frame, I expect.
        # But that's ok, since force-drawing is not recomended in general.
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
            self._html_context.drawImage(self._offscreen_canvas, 0, 0, cw, ch)

    def _set_logical_size(self, width: float, height: float):
        self._canvas_element.style.width = f"{width}px"
        self._canvas_element.style.height = f"{height}px"

    def _rc_close(self):
        # self._canvas_element.remove() # shouldn't really be needed?
        pass

    def _rc_get_closed(self):
        # TODO: like check if the element still exists?
        return False

    def _rc_set_title(self, title: str):
        # canvas element doens't have a title directly... but maybe the whole page?
        document.title = title

    def get_context(self, context_type: str):
        # hook onto this function so we get the "html_context" (js proxy) representation available...
        res = super().get_context(context_type)
        if context_type == "bitmap":
            self._html_context = self._canvas_element.getContext("2d")
        elif context_type in ("wgpu", "webgpu"):
            self._html_context = self._canvas_element.getContext("webgpu")
        else:
            raise ValueError(
                f"Unsupported context_type for html canvas: {context_type}"
            )
        return res


# Make available under a name that is the same for all backends
loop = loop  # must set loop variable to pass meta tests
RenderCanvas = HtmlRenderCanvas
