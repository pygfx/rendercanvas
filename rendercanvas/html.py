"""
Support to run rendercanvas on the webbrowser via Pyodide.

We expect to have a HTMLCanvas element with the id "canvas".
It is not required to set the default sdl2 canvas as the Pyodide docs describe.
"""

__all__ = ["HtmlRenderCanvas", "RenderCanvas", "loop"]

from rendercanvas.base import BaseRenderCanvas, BaseCanvasGroup, BaseLoop
import weakref

import sys
if "pyodide" not in sys.modules:
    raise ImportError("This module is only for use with Pyodide in the browser.")

# packages available inside pyodide
from pyodide.ffi import run_sync, create_proxy
from js import document, ImageData, Uint8ClampedArray, window

# TODO event loop for js? https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubLoop
# https://pyodide.org/en/stable/usage/sdl.html#working-with-infinite-loop
# https://pyodide.org/en/stable/usage/api/python-api/webloop.html
# https://github.com/pyodide/pyodide/blob/0.28.2/src/py/pyodide/webloop.py
# also the asyncio.py implementation
class PyodideLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._webloop = None
        self.__pending_tasks = []
        self._stop_event = None

    def _rc_init(self):
        from pyodide.webloop import WebLoop
        self._webloop = WebLoop()

        # TODO later try this
        # try:
        #     self._interactive_loop = self._webloop.get_running_loop()
        #     self._stop_event = PyodideFuture()
        #     self._mark_as_interactive()
        # except Exception:
        #     self._interactive_loop = None
        self._interactive_loop = None

    def _rc_run(self):
        import asyncio #so the .run method is now overwritten I guess
        if self._interactive_loop is not None:
            return
        # self._webloop.run_forever() # or untill stop event?
        asyncio.run(self._rc_run_async())

    async def _rc_run_async(self):
        import asyncio
        self._run_loop = self._webloop

        while self.__pending_tasks:
            self._rc_add_task(*self.__pending_tasks.pop(-1))

        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    # untested maybe...
    def _rc_stop_(self):
        while self.__tasks:
            task = self.__tasks.pop()
            task.cancel()

        self._stop_event.set()
        self._stop_event = None
        self._run_loop = None

    def _rc_call_later(self, delay, callback, *args):
        self._webloop.call_later(delay, callback, *args)

pyodide_loop = PyodideLoop()

# needed for completeness? somehow is required for other examples - hmm?
class HtmlCanvasGroup(BaseCanvasGroup):
    pass

# https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubRenderCanvas
class HtmlRenderCanvas(BaseRenderCanvas):
    _rc_canvas_group = HtmlCanvasGroup(pyodide_loop) # todo do we need the group?
    def __init__(self, *args, **kwargs):
        canvas_selector = kwargs.pop("canvas_selector", "canvas")
        super().__init__(*args, **kwargs)
        self.canvas_element = document.querySelector(canvas_selector)
        self.html_context = self.canvas_element.getContext("bitmaprenderer") # this is part of the canvas, not the context???
        self._setup_events()
        self._js_array = Uint8ClampedArray.new(0)
        self._final_canvas_init()


    def _setup_events(self):
        # following list from: https://jupyter-rfb.readthedocs.io/en/stable/events.html
        # better: https://rendercanvas.readthedocs.io/stable/api.html#rendercanvas.EventType
        KEY_MOD_MAP = {
            "altKey": "Alt",
            "ctrlKey": "Control",
            "metaKey": "Meta",
            "shiftKey": "Shift",
        }
        # resize ? maybe composition?

        # close ? perhaps https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent

        # pointer_down
        def _html_pointer_down(proxy_args):
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "pointer_down",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "pointer_up",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "pointer_move",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "pointer_enter",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "pointer_leave",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "double_click",
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "button": proxy_args.button,
                "buttons": proxy_args.buttons,
                "modifiers": modifiers,
                # no touches here
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)
        self._double_click_proxy = create_proxy(_html_double_click)
        self.canvas_element.addEventListener("dblclick", self._double_click_proxy)

        # wheel
        def _html_wheel(proxy_args):
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "wheel",
                "dx": proxy_args.deltaX,
                "dy": proxy_args.deltaY,
                "x": proxy_args.offsetX,
                "y": proxy_args.offsetY,
                "buttons": proxy_args.buttons,
                "modifiers": modifiers,
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)
        self._wheel_proxy = create_proxy(_html_wheel)
        self.canvas_element.addEventListener("wheel", self._wheel_proxy)

        # key_down
        def _html_key_down(proxy_args):
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "key_down",
                "modifiers": modifiers,
                "key": proxy_args.key,
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)

        self._key_down_proxy = create_proxy(_html_key_down)
        document.addEventListener("keydown", self._key_down_proxy) # key events happen on document scope?

        # key_up
        def _html_key_up(proxy_args):
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
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
            modifiers = tuple([v for k,v in KEY_MOD_MAP.items() if getattr(proxy_args, k)])
            event = {
                "event_type": "char",
                "modifiers": modifiers,
                "char_str": proxy_args.key, # unsure if this works, it's experimental anyway: https://github.com/pygfx/rendercanvas/issues/28
                "time_stamp": proxy_args.timeStamp,
            }
            self.submit_event(event)
        self._char_proxy = create_proxy(_html_char)
        document.addEventListener("input", self._char_proxy) # maybe just another keydown? (seems to include unicode chars)

        # animate event doesn't seem to be actually implemented, and it's by the loop not the gui.

    def _rc_gui_poll(self):
        # not sure if anything has to be done
        pass

    def _rc_get_present_methods(self):
        # in the future maybe we can get the webgpu context (as JsProxy) or something... future stuff!
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_request_draw(self):
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._draw_frame_and_present)

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, **kwargs):
        data = kwargs.get("data") # data is a memoryview
        shape = data.shape # use data shape instead of canvas size
        if self._js_array.length != shape[0] * shape[1] * 4:  # #assumes rgba-u8 -> 4 bytes per pixel
            # resize step here? or on first use.
            self._js_array = Uint8ClampedArray.new(shape[0] * shape[1] * 4)
        self._js_array.assign(data)
        image_data = ImageData.new(self._js_array, shape[1], shape[0]) # width, height !
        size = self.get_logical_size()
        image_bitmap = run_sync(window.createImageBitmap(image_data, {"resizeQuality": "pixelated", "resizeWidth": int(size[0]), "resizeHeight": int(size[1])}))
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
        shape = data.shape # use data shape instead of canvas size
        if self._js_array.length != shape[0] * shape[1] * 4:  # #assumes rgba-u8 -> 4 bytes per pixel
            # resize step here? or on first use.
            self._js_array = Uint8ClampedArray.new(shape[0] * shape[1] * 4)
        self._js_array.assign(data)
        image_data = ImageData.new(self._js_array, shape[1], shape[0]) # width, height !
        #######
        # TODO: is not resized because we writing bytes to pixels directly.
        self._2d_context.putImageData(image_data, 0, 0) # x,y


    def _rc_get_physical_size(self):
        return self.canvas_element.style.width, self.canvas_element.style.height

    def _rc_get_logical_size(self):
        return float(self.canvas_element.width), float(self.canvas_element.height)

    def _rc_get_pixel_ratio(self) -> float:
        ratio = window.devicePixelRatio
        return ratio

    def _rc_set_logical_size(self, width: float, height: float):
        ratio = self._rc_get_pixel_ratio()
        self.canvas_element.width = int(width * ratio) # only positive, int() -> floor()
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

# provide for the auto namespace:
loop = pyodide_loop
RenderCanvas = HtmlRenderCanvas
