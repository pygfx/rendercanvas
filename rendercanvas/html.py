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
from pyodide.ffi import run_sync
from js import document, ImageData, Uint8ClampedArray, window
# import sys
# assert sys.platform == "emscripten" # use in the future to direct the auto backend?

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

# needed for the _canvas_context lookup in _draw_frame_and_present
# mostly based on BitmapRenderingContext
class HTMLBitmapContext:
    def __init__(self, canvas, present_methods):
        self._canvas_ref = weakref.ref(canvas)
        self._present_methods = present_methods
        assert "bitmap" in present_methods # for now just this?

        self._format = "rgba-u8" # hardcoded for now

        self._bitmap = None

    @property
    def canvas(self):
        return self._canvas_ref()

    def set_bitmap(self, bitmap):
        # this needs to stay a python object I guess...
        # as it breaks when we pass the js objects to the other class...
        # so the interesting part is actually happening in the _rc_present_bitmap method of the canvas class
        self._bitmap = bitmap

    def present(self):
        if self._bitmap is None:
            return {"method": "skip"}
        elif self._present_methods == "bitmap":
            # TODO: reshape the bitmap to fit canvas size...
            # copy pasted from ref:
            bitmap = self._bitmap
            flat_bitmap = bitmap.cast("B", (bitmap.nbytes,))
            new_bitmap = memoryview(bytearray(bitmap.nbytes * 4)).cast("B")
            new_bitmap[::4] = flat_bitmap
            new_bitmap[1::4] = flat_bitmap
            new_bitmap[2::4] = flat_bitmap
            new_bitmap[3::4] = b"\xff" * flat_bitmap.nbytes
            bitmap = new_bitmap.cast("B", (*bitmap.shape, 4))
            self._bitmap = bitmap
            return {
                "method": "bitmap",
                "data": self._bitmap,
                "format": self._format,
            }

        else:
            return {"method": "fail", "message": "wut?"}

# needed for completeness? somehow is required for other examples - hmm?
class HtmlCanvasGroup(BaseCanvasGroup):
    pass

# https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubRenderCanvas
class HtmlRenderCanvas(BaseRenderCanvas):
    _rc_canvas_group = HtmlCanvasGroup(pyodide_loop) # todo do we need the group?
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        element_id = kwargs.get("element_id", "canvas") # should we allow this for multiple canvas?
        canvas_element = document.getElementById(element_id)
        self.canvas_element = canvas_element
        self.html_context = canvas_element.getContext("bitmaprenderer") # this is part of the canvas, not the context???

        self._js_array = Uint8ClampedArray.new(0)
        self._final_canvas_init()

    # override the base method to also register the js event and proxy
    # TODO: maybe split up into multiple methods like other backends
    def add_event_handler(self, *args, order=0):
        # https://pyodide.org/en/stable/usage/faq.html#how-can-i-use-a-python-function-as-an-event-handler maybe?
        # https://pyodide.org/en/stable/usage/api/python-api/ffi.html#pyodide.ffi.wrappers.add_event_listener
        from pyodide.ffi import create_proxy # maybe import further up?
        def f(*proxy_args):
            # print(proxy_args[0].type)
            # print(proxy_args[0].key)
            # print(repr(self._events))
            event = {
                "event_type": "key_down",
                "key": proxy_args[0].key,
                "timestamp": proxy_args[0].timeStamp,
            }
            # print("event to submit:", event)
            self.submit_event(event)

        # TODO: store multiple proxies for more events... maybe a dict? maybe attach it to the event?
        self._proxy_f = create_proxy(f)
        # TODO: map event types from rendercanvas back to js event types example: key_down -> keydown
        document.addEventListener('keydown', self._proxy_f)

        return self._events.add_handler(*args, order=order) # this returns the python callback of the user defined function

    # TODO: remove handler like this?
    # document.body.removeEventListener('keydown', self._proxy_f)
    # self._proxy_f.destroy()

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
        data = kwargs.get("data")
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
