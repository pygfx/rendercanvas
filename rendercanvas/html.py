"""
Support to run rendercanvas on the webbrowser via Pyodide.

We expect to have a HTMLCanvas element with the id "canvas".
It is not required to set the default sdl2 canvas as the Pyodide docs describe.
"""

__all__ = ["HtmlRenderCanvas", "RenderCanvas", "loop"]

from rendercanvas.base import BaseRenderCanvas, BaseCanvasGroup
from rendercanvas.asyncio import loop

import sys

if "pyodide" not in sys.modules:
    raise ImportError("This module is only for use with Pyodide in the browser.")

# packages available inside pyodide
from pyodide.ffi import run_sync, create_proxy
from js import document, ImageData, Uint8ClampedArray, window, HTMLCanvasElement, ResizeObserver


# needed for completeness? somehow is required for other examples - hmm?
class HtmlCanvasGroup(BaseCanvasGroup):
    pass


# https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubRenderCanvas
class HtmlRenderCanvas(BaseRenderCanvas):
    _rc_canvas_group = HtmlCanvasGroup(loop)  # todo do we need the group?

    def __init__(
        self,
        canvas_el: str = "canvas",
        *args,
        **kwargs,
    ):
        if isinstance(canvas_el, str):
            self.canvas_element = document.querySelector(canvas_el)
        else:
            self.canvas_element = canvas_el
        if "size" not in kwargs:
            # if size isn't given, we use the existing size.
            # otherwise the final init will set it to the default (480,640)
            kwargs["size"] = self.get_logical_size()
        super().__init__(*args, **kwargs)
        self._setup_events()
        self._js_array = Uint8ClampedArray.new(0)
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
            -1:0, # no button
            0: 1, # left
            1: 3, # middle/wheel
            2: 2, # right
            3: 4, # backwards
            4: 5, # forwards
        }

        # https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent/buttons
        def buttons_mask_to_tuple(mask) -> tuple[int, ...]:
            bin(mask)
            res = ()
            for i, v in enumerate(bin(mask)[:1:-1]):
                if v == "1":
                    res += (mouse_button_map.get(i, i),)
            return res


        # resize ? maybe composition?
        # perhaps: https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver

        def _resize_callback(entries, observer):
            entry = entries[0] # assume it's just this as we are observing the canvas element only?
            # print(entry)
            new_size = ()
            ratio = self.get_pixel_ratio()
            if entry.devicePixelContentBoxSize: # safari doesn't 
                new_size = (entry.devicePixelContentBoxSize[0].inlineSize, entry.devicePixelContentBoxSize[0].blockSize)
            else:
                lsize = ()
                if entry.contentBoxSize:
                    lsize = (entry.contentBoxSize[0].inlineSize, entry.contentBoxSize[0].blockSize)
                else:
                    lsize = (entry.contentRect.width, entry.contentRect.height)
                new_size = (int(lsize[0]*ratio), int(lsize[1]*ratio))

            event = {
                "width": new_size[0],
                "height": new_size[1],
                "pixel_ratio": ratio,
                "event_type": "resize",
            }
            self.submit_event(event)

        self._resize_callback_proxy = create_proxy(_resize_callback)
        self._resize_observer = ResizeObserver.new(self._resize_callback_proxy)
        self._resize_observer.observe(self.canvas_element)

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
        self.canvas_element.addEventListener("pointerdown", self._pointer_down_proxy)

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
        self.canvas_element.addEventListener("pointerup", self._pointer_up_proxy)

        # pointer_move
        # TODO: track pointer_inside and pointer_down to only trigger this when relevant?
        # also figure out why it doesn't work in the first place...
        def _html_pointer_move(proxy_args):
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

        self._pointer_enter_proxy = create_proxy(_html_pointer_enter)
        self.canvas_element.addEventListener("pointerenter", self._pointer_enter_proxy)

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

        self._pointer_leave_proxy = create_proxy(_html_pointer_leave)
        self.canvas_element.addEventListener("pointerleave", self._pointer_leave_proxy)
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
        self.canvas_element.addEventListener("dblclick", self._double_click_proxy)

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
        self.canvas_element.addEventListener("wheel", self._wheel_proxy)

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

        # char
        def _html_char(proxy_args):
            print(dir(proxy_args))
            modifiers = tuple(
                [v for k, v in key_mod_map.items() if getattr(proxy_args, k)]
            )
            event = {
                "event_type": "char",
                "modifiers": modifiers,
                "char_str": proxy_args.key,  # unsure if this works, it's experimental anyway: https://github.com/pygfx/rendercanvas/issues/28
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._char_proxy = create_proxy(_html_char)
        document.addEventListener(
            "input", self._char_proxy
        )  # maybe just another keydown? (seems to include unicode chars)

        # animate event doesn't seem to be actually implemented, and it's by the loop not the gui.

    def _rc_gui_poll(self):
        # not sure if anything has to be done
        pass

    def _rc_get_present_methods(self):
        # in the future maybe we can get the webgpu context (as JsProxy) or something... future stuff!
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            },
            "screen": {
                "formats": ["rgba-u8"],
                "window": self.canvas_element.js_id, #is a number - doubt it's useful though...
            }
        }

    def _rc_request_draw(self):
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._draw_frame_and_present)

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, **kwargs):
        data = kwargs.get("data")  # data is a memoryview
        shape = data.shape  # use data shape instead of canvas size
        if (
            self._js_array.length != shape[0] * shape[1] * 4
        ):  # #assumes rgba-u8 -> 4 bytes per pixel
            # resize step here? or on first use.
            self._js_array = Uint8ClampedArray.new(shape[0] * shape[1] * 4)
        self._js_array.assign(data)
        image_data = ImageData.new(
            self._js_array, shape[1], shape[0]
        )  # width, height !
        size = self.get_logical_size()
        image_bitmap = run_sync(
            window.createImageBitmap(
                image_data,
                {
                    "resizeQuality": "pixelated",
                    "resizeWidth": int(size[0]),
                    "resizeHeight": int(size[1]),
                },
            )
        )
        # this actually "writes" the data to the canvas I guess.
        self.html_context.transferFromImageBitmap(image_bitmap)
        # handles lower res just fine it seems.

    # maybe if we don't use the existing bitmaprendering context, we could have something like this:
    # _rc_present_js_array?
    # _rc_present_js_image_data?

    # TODO: consider switching:
    def _rc_present_bitmap_2d(self, **kwargs):
        # still takes a bitmap, but uses the 2d context instead which might be faster
        if not hasattr(self, "_2d_context"):
            # will give `null` if other context already exists! so we would need to avoid that above.
            self._2d_context = self.canvas_element.getContext("2d")
            print("got 2d context:", self._2d_context)
        data = kwargs.get("data")

        ## same as above ## (might be extracted to the bitmappresentcontext class one day?)
        shape = data.shape  # use data shape instead of canvas size
        if (
            self._js_array.length != shape[0] * shape[1] * 4
        ):  # #assumes rgba-u8 -> 4 bytes per pixel
            # resize step here? or on first use.
            self._js_array = Uint8ClampedArray.new(shape[0] * shape[1] * 4)
        self._js_array.assign(data)
        image_data = ImageData.new(
            self._js_array, shape[1], shape[0]
        )  # width, height !
        #######
        # TODO: is not resized because we writing bytes to pixels directly.
        self._2d_context.putImageData(image_data, 0, 0)  # x,y

    def _rc_get_physical_size(self):
        return self.canvas_element.style.width, self.canvas_element.style.height

    def _rc_get_logical_size(self):
        return float(self.canvas_element.width), float(self.canvas_element.height)

    def _rc_get_pixel_ratio(self) -> float:
        ratio = window.devicePixelRatio
        return ratio

    def _rc_gical_size(self, width: float, height: float):
        ratio = self._rc_get_pixel_ratio()
        self.canvas_element.width = int(
            width * ratio
        )  # only positive, int() -> floor()
        self.canvas_element.height = int(height * ratio)
        # also set the physical scale here?
        # self.canvas_element.style.width = f"{width}px"
        # self.canvas_element.style.height = f"{height}px"

    def _rc_close(self):
        # self.canvas_element.remove() # shouldn't really be needed?
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
            self._html_context = self.canvas_element.getContext("bitmaprenderer")
        elif context_type in ("wgpu", "webgpu"):
            self._html_context = self.canvas_element.getContext("webgpu")
        else:
            raise ValueError(f"Unsupported context_type for html canvas: {context_type}")
        return res


# provide for the auto namespace:
RenderCanvas = HtmlRenderCanvas
