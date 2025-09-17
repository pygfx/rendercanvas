import rendercanvas
print("rendercanvas version:", rendercanvas.__version__)
from rendercanvas.base import BaseRenderCanvas, BaseCanvasGroup, BaseLoop

import numpy as np

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
class HTMLLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._webloop = None
        self.__pending_tasks = []
        self._stop_event = None

    def _rc_init(self):
        from pyodide.webloop import WebLoop
        import asyncio
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

pyodide_loop = HTMLLoop()

# needed for completeness? somehow is required for other examples - hmm?
class HTMLCanvasGroup(BaseCanvasGroup):
    pass

# TODO: make this a proper RenderCanvas, just a poc for now
# https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubRenderCanvas
class HTMLBitmapCanvas(BaseRenderCanvas):
    _rc_canvas_group = HTMLCanvasGroup(pyodide_loop) # todo do we need the group?
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        canvas_element = document.getElementById("canvas")
        self.canvas_element = canvas_element
        self.context = canvas_element.getContext("bitmaprenderer")

        size = self.get_logical_size() #seemingly available during init
        # assume 1 byte per pixel and 4 channels right here # TODO parse format bpp?
        self._js_array = Uint8ClampedArray.new(size[0]*size[1]*4)

        self._final_canvas_init()

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
        # loop.call_soon?
        loop = self._rc_canvas_group.get_loop()
        loop.call_soon(self._draw_frame_and_present)
        # window.requestAnimationFrame(self._rc_present_bitmap) #doesn't feel like this is the way... maybe more reading
        # self._rc_force_draw()
        # print("request draw called?")

    def _rc_force_draw(self):
        self._draw_frame_and_present() # returns without calling the present it seems

    def _rc_present_bitmap(self):
        # this actually "writes" the data to the canvas I guess.
        self.context.transferFromImageBitmap(self._image_bitmap)

    # reimplement so we might understand what's going on
    def _draw_frame_and_present(self):
        self._draw_frame()
        self._rc_present_bitmap()

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

    def set_bitmap(self, bitmap):
        # method doesn't really exist? as it's part of the context? maybe we move it into the draw function...
        # TODO: improve performance https://pyodide.org/en/stable/usage/type-conversions.html#buffers
        self._js_array.assign(bitmap)
        image_data = ImageData.new(self._js_array, bitmap.shape[1], bitmap.shape[0])
        # now this is the fake async call so it should be blocking: https://blog.pyodide.org/posts/jspi/
        self._image_bitmap = run_sync(window.createImageBitmap(image_data))
        # better yet using a 2d context: https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/putImageData ?

    def _rc_close(self):
        # self.canvas_element.remove() # shouldn't really be needed?
        pass

    def _rc_get_closed(self):
        # TODO: like check if the element still exists?
        return False

    def _rc_set_title(self, title: str):
        # canvas element doens't have a title directly... but maybe the whole page?
        document.title = title

    # TODO: events


canvas = HTMLBitmapCanvas(title="RenderCanvas in Pyodide", max_fps=30.0)

def animate():
    # based on the noise.py example
    w, h = canvas._rc_get_logical_size()
    shape = (int(h), int(w), 4) # third dimension sounds like it's needed
    bitmap = np.random.uniform(0, 255, shape).astype(np.uint8)
    canvas.set_bitmap(bitmap)

# animate()
# canvas._rc_present_bitmap()
canvas.request_draw(animate)
pyodide_loop.run()
